// Real WSS + MQTT + TURN audio smoke test, using isolated demo_* IDs only.
// Set VOICE_TEST_ADB, VOICE_TEST_SERIAL, VOICE_TEST_PLAYWRIGHT and VOICE_TEST_BROWSER.
import { createRequire } from 'node:module';
import { execFile } from 'node:child_process';
import fs from 'node:fs/promises';
import { MqttProbe } from './mqtt-probe.mjs';

const device = 'demo_virtual_20261119', local = 'demo_app_20261119';
const require = createRequire(process.env.VOICE_TEST_PLAYWRIGHT + '/package.json');
const { chromium } = require('playwright');
const adb = (...args) => new Promise((resolve, reject) => execFile(
  process.env.VOICE_TEST_ADB || 'adb', ['-s', process.env.VOICE_TEST_SERIAL || 'emulator-5556', ...args],
  { encoding: 'utf8', timeout: 15000 }, (error, output) => error ? reject(error) : resolve(output)));
const output = 'build/android-e2e';
await fs.mkdir(output, { recursive: true });
const ui = async () => {
  await adb('shell', 'uiautomator', 'dump', '/sdcard/voice-ui.xml');
  return adb('shell', 'cat', '/sdcard/voice-ui.xml');
};
const click = async label => {
  const xml = await ui();
  const match = xml.match(new RegExp('<node[^>]*text="' + label + '"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"'));
  if (!match) throw Error('Button not visible: ' + label);
  const [x1, y1, x2, y2] = match.slice(1).map(Number);
  await adb('shell', 'input', 'tap', String(Math.round((x1 + x2) / 2)), String(Math.round((y1 + y2) / 2)));
};
const waitUi = async label => {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    if ((await ui()).includes('text="' + label + '"')) return;
  }
  throw Error('UI state not reached: ' + label);
};
const screenshot = async name => {
  await adb('shell', 'screencap', '-p', '/sdcard/voice-e2e.png');
  await adb('pull', '/sdcard/voice-e2e.png', `${output}/${name}.png`);
};

// Change only this debug app's preferences on the test emulator.
await fs.writeFile(`${output}/preferences.xml`, `<?xml version="1.0" encoding="utf-8"?><map><string name="server">https://voice.2811.top</string><string name="device">${device}</string><string name="local">${local}</string></map>`);
await adb('shell', 'am', 'force-stop', 'com.youkong.voiceintercom');
await adb('push', `${output}/preferences.xml`, '/data/local/tmp/voice-test-preferences.xml');
await adb('shell', 'run-as', 'com.youkong.voiceintercom', 'mkdir', '-p', 'shared_prefs');
await adb('shell', 'run-as', 'com.youkong.voiceintercom', 'cp', '/data/local/tmp/voice-test-preferences.xml', 'shared_prefs/intercom.xml');
await adb('shell', 'am', 'start', '-n', 'com.youkong.voiceintercom/.MainActivity');

const browser = await chromium.launch({ executablePath: process.env.VOICE_TEST_BROWSER, headless: true,
  args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--no-proxy-server'] });
const context = await browser.newContext({ permissions: ['microphone'] });
const page = await context.newPage();
const messages = [], errors = [], results = [];
let route = Promise.resolve();
const mqtt = new MqttProbe('118.31.113.169', device, message => {
  messages.push(message);
  route = route.then(() => page.evaluate(async value => {
    if (window.qaReceive) await qaReceive(value);
  }, message)).catch(error => errors.push(error.message));
});
try {
  await mqtt.ready;
  await page.goto('https://voice.2811.top/index2.html');
  await page.exposeFunction('qaPublish', message => mqtt.publish({ ...message, target: local }));
  await page.evaluate(async () => {
    window.qaIce = await new Promise((resolve, reject) => {
      const ws = new WebSocket('wss://voice.2811.top/signaling');
      const timer = setTimeout(() => { ws.close(); reject(Error('ICE response timeout')); }, 10000);
      ws.onopen = () => ws.send(JSON.stringify({ type: 'ice_request', from: 'demo_ice_probe_20261119', timestamp: Math.floor(Date.now() / 1000) }));
      ws.onmessage = event => {
        const value = JSON.parse(event.data);
        if (value.type === 'ice_response') { clearTimeout(timer); ws.close(); resolve(value.iceServers); }
      };
      ws.onerror = reject;
    });
    window.qaInit = async mode => {
      if (window.qaPc) qaPc.close();
      if (window.qaStream) qaStream.getTracks().forEach(track => track.stop());
      window.qaMode = mode; window.qaPending = []; window.qaStates = [];
      window.qaPc = new RTCPeerConnection({ iceServers: qaIce, iceTransportPolicy: 'relay' });
      window.qaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      qaStream.getTracks().forEach(track => qaPc.addTrack(track, qaStream));
      qaPc.onconnectionstatechange = () => qaStates.push(qaPc.connectionState);
      qaPc.onicecandidate = event => {
        if (event.candidate) qaPublish({ type: 'candidate', data: event.candidate.candidate });
      };
      qaPc.ontrack = event => {
        window.qaAudio = new Audio(); qaAudio.srcObject = event.streams[0]; qaAudio.play().catch(() => {});
      };
    };
    window.qaOffer = async () => {
      const offer = await qaPc.createOffer(); await qaPc.setLocalDescription(offer);
      await qaPublish({ type: 'offer', data: offer.sdp });
    };
    window.qaReceive = async message => {
      if (message.type === 'customized' && message.data === 'ACCEPT_CALL' && qaMode === 'ring') { await qaOffer(); return; }
      if (message.type === 'offer' || message.type === 'answer') {
        await qaPc.setRemoteDescription({ type: message.type, sdp: message.data || message.sdp });
        for (const value of qaPending) await qaPc.addIceCandidate(value);
        qaPending = [];
        if (message.type === 'offer') {
          const answer = await qaPc.createAnswer(); await qaPc.setLocalDescription(answer);
          await qaPublish({ type: 'answer', data: answer.sdp });
        }
      } else if (message.type === 'candidate') {
        const value = { candidate: message.candidate || message.data, sdpMid: '0', sdpMLineIndex: 0 };
        if (qaPc.remoteDescription) await qaPc.addIceCandidate(value); else qaPending.push(value);
      }
    };
  });
  const connected = async name => {
    await page.waitForFunction(() => qaPc.connectionState === 'connected', null, { timeout: 25000 });
    await waitUi('通话中');
    await page.waitForFunction(async () => {
      const stats = [...(await qaPc.getStats()).values()];
      return stats.some(s => s.type === 'inbound-rtp' && s.packetsReceived > 0)
        && stats.some(s => s.type === 'outbound-rtp' && s.packetsSent > 0);
    }, null, { timeout: 10000 });
    const stats = await page.evaluate(async () => {
      const entries = [...(await qaPc.getStats()).values()];
      return { state: qaPc.connectionState,
        relay: entries.some(s => s.type === 'local-candidate' && s.candidateType === 'relay'),
        audio: entries.filter(s => s.type === 'inbound-rtp' || s.type === 'outbound-rtp')
          .map(s => ({ type: s.type, kind: s.kind, packetsReceived: s.packetsReceived, packetsSent: s.packetsSent })) };
    });
    if (!stats.relay) throw Error('TURN relay was not used');
    results.push({ name, ...stats }); await screenshot(name);
    console.log('PASS', name, JSON.stringify(stats));
  };
  await waitUi('待机');
  await page.evaluate(() => qaInit('outgoing'));
  await click('呼叫设备'); await connected('outgoing');
  await click('麦克风开'); await waitUi('麦克风关');
  await click('麦克风关'); await click('扬声器'); await waitUi('听筒'); await click('听筒');
  mqtt.publish({ type: 'bye', target: local }); await waitUi('待机');
  results.push({ name: 'mute-speaker-remote-hangup', passed: true });

  await page.evaluate(() => qaInit('incoming'));
  await page.evaluate(() => qaOffer()); await waitUi('设备来电'); await screenshot('incoming');
  await click('接听来电'); await connected('incoming-offer');
  await click('挂断通话'); await waitUi('待机');
  if (!messages.some(m => m.type === 'bye')) throw Error('Native hangup not forwarded to MQTT');

  await page.evaluate(() => qaInit('ring'));
  const beforeAccept = messages.length;
  mqtt.publish({ type: 'ring', data: 'RING', target: local }); await waitUi('设备来电');
  await click('接听来电'); await connected('ring-accept-offer');
  if (!messages.slice(beforeAccept).some(m => m.type === 'customized' && m.data === 'ACCEPT_CALL')) throw Error('No ACCEPT_CALL received');
  await click('挂断通话'); await waitUi('待机');

  await page.evaluate(() => qaInit('reject'));
  const beforeReject = messages.length;
  mqtt.publish({ type: 'ring', data: 'RING', target: local }); await waitUi('设备来电'); await click('拒接'); await waitUi('待机');
  if (!messages.slice(beforeReject).some(m => m.type === 'reject')) throw Error('Reject not received by device');
  results.push({ name: 'reject-before-offer', passed: true });
  if (errors.length) throw Error(errors.join('; '));
  await fs.writeFile(`${output}/results.json`, JSON.stringify({ passed: true, results }, null, 2));
  console.log('ALL NATIVE DEMO CHECKS PASSED');
} catch (error) {
  await fs.writeFile(`${output}/results.json`, JSON.stringify({ passed: false, error: error.message, results,
    messages: messages.map(m => ({ type: m.type, from: m.from, target: m.target })), errors }, null, 2));
  await screenshot('failure').catch(() => {});
  console.error(error); process.exitCode = 1;
} finally {
  mqtt.close(); await browser.close();
}
