import { lookup } from 'node:dns/promises';

// Disrupt only the test emulator's UDP media path. TCP WSS stays connected.
// Every exact rule is removed in finally; never flush existing firewall rules.
export async function checkAudioRecovery({ adb, page, ui, messages, screenshot, pause }) {
  if ((await adb('shell', 'getprop', 'ro.kernel.qemu')).trim() !== '1'
      || !(await adb('shell', 'id')).includes('uid=0(')) {
    throw Error('Audio recovery test requires an explicitly rooted emulator');
  }
  const packageLine = await adb('shell', 'cmd', 'package', 'list', 'packages', '-U', 'com.youkong.voiceintercom');
  const uid = packageLine.match(/uid:(\d+)/)?.[1];
  if (!uid) throw Error('App UID unavailable');
  const urls = await page.evaluate(() => qaIce.flatMap(server => Array.isArray(server.urls) ? server.urls : [server.urls]));
  const turn = urls.find(url => /^turn:[^/]/.test(url));
  const host = turn?.match(/^turn:([^:?]+)(?::(\d+))?/)?.[1];
  const port = turn?.match(/^turn:([^:?]+)(?::(\d+))?/)?.[2] || '3478';
  if (!host) throw Error('TURN endpoint unavailable');
  const { address } = await lookup(host, { family: 4 });
  const rules = [
    ['OUTPUT', '-p', 'udp', '-m', 'owner', '--uid-owner', uid, '-m', 'comment', '--comment', 'voice-audio-recovery-test', '-j', 'DROP'],
    ['INPUT', '-p', 'udp', '-s', address, '--sport', port, '-m', 'comment', '--comment', 'voice-audio-recovery-test', '-j', 'DROP']
  ];
  const installed = [];
  await adb('logcat', '-c');
  const anchor = messages.length;
  const original = await page.evaluate(async () => {
    const stats = [...(await qaPc.getStats()).values()];
    return stats.filter(s => ['inbound-rtp', 'outbound-rtp'].includes(s.type))
      .map(s => ({ type: s.type, packets: s.packetsReceived ?? s.packetsSent ?? 0 }));
  });
  let disconnectedAt = 0;
  try {
    for (const rule of rules) {
      await adb('shell', 'iptables', '-I', rule[0], '1', ...rule.slice(1));
      installed.push(rule);
    }
    const deadline = Date.now() + 40000;
    while (Date.now() < deadline) {
      const diagnostics = await adb('logcat', '-d', '-s', 'VoiceIntercom:I', '*:S');
      if (diagnostics.includes('音频连接：DISCONNECTED')) { disconnectedAt = Date.now(); break; }
      if (messages.slice(anchor).some(message => message.type === 'bye')) throw Error('App sent BYE before media recovery');
      await pause(100);
    }
    if (!disconnectedAt) throw Error('Native DISCONNECTED state was not observed');
    console.log('Observed native DISCONNECTED; keeping media blocked for >8 seconds');
    // libwebrtc escalates this complete outage to FAILED roughly ten seconds
    // after DISCONNECTED. Exercise the removed 8s app timer while the peer is
    // still recoverable; FAILED remains a terminal condition in the product.
    while (Date.now() - disconnectedAt < 8500) {
      if (messages.slice(anchor).some(message => message.type === 'bye')) {
        const diagnostics = await adb('logcat', '-d', '-s', 'VoiceIntercom:I', '*:S');
        throw Error('App sent BYE during a recoverable interruption: ' + diagnostics.slice(-1600));
      }
      await pause(300);
    }
    // Capture while paused in the connected call before restoring UDP.
    // Screenshots/UI dumps can take seconds: restore immediately at this point.
  } finally {
    for (const rule of installed.reverse()) await adb('shell', 'iptables', '-D', ...rule).catch(() => {});
  }
  const view = await ui();
  if (!view.includes('text="通话中"') || !view.includes('text="挂断通话"')) throw Error('App ended call during interruption');
  const service = await adb('shell', 'dumpsys', 'activity', 'services', 'com.youkong.voiceintercom');
  if (!service.includes('isForeground=true')) throw Error('Audio foreground service was released');
  // Recover the existing peer without sending offers, restarting ICE, or dialing again.
  await page.waitForFunction(async baseline => {
    const stats = [...(await qaPc.getStats()).values()];
    return qaPc.connectionState === 'connected' && baseline.every(before => stats.some(s =>
      s.type === before.type && (s.packetsReceived ?? s.packetsSent ?? 0) > before.packets + 20));
  }, original, { timeout: 35000 });
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline && !(await ui()).includes('双向语音已连接')) await pause(300);
  if (!(await ui()).includes('双向语音已连接')) throw Error('App did not display media recovery');
  if (messages.slice(anchor).some(message => ['bye', 'offer', 'answer'].includes(message.type))) {
    throw Error('Recovery must keep the same signaling session without BYE or renegotiation');
  }
  await screenshot('audio-recovered-same-call');
  return { name: 'udp-interruption-over-eight-seconds', passed: true,
    interruptionAfterDisconnectedSeconds: 8.5, nativeDisconnectedObserved: true,
    byeSent: false, samePeerRecovered: true, bidirectionalAudioResumed: true, foregroundServiceKept: true };
}
