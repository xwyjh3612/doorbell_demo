// Requires explicit --real-device, a running serial console bridge and an App
// already configured for that device and granted microphone permission.
import { execFile } from 'node:child_process';
import fs from 'node:fs/promises';

const args = process.argv.slice(2);
const option = name => args[args.indexOf(name) + 1];
const device = args.includes('--real-device') ? option('--real-device') : '';
if (!device || !/^[0-9]{12,20}$/.test(device)) throw Error('Specify --real-device DEVICE_ID to call physical hardware');
const holdSeconds = args.includes('--hold-seconds') ? Number(option('--hold-seconds')) : 30;
if (!Number.isFinite(holdSeconds) || holdSeconds < 10 || holdSeconds > 600) throw Error('Hold duration must be 10..600 seconds');
const consoleUrl = process.env.VOICE_TEST_CONSOLE || 'http://127.0.0.1:18889';
const output = 'build/real-esp32-e2e';
await fs.mkdir(output, { recursive: true });
const results = [], startedAt = new Date().toISOString();
const adb = (...values) => new Promise((resolve, reject) => execFile(
  process.env.VOICE_TEST_ADB || 'adb', ['-s', process.env.VOICE_TEST_SERIAL || 'emulator-5556', ...values],
  { encoding: 'utf8', timeout: 15000 }, (error, out) => error ? reject(error) : resolve(out)));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const ui = async () => {
  await adb('shell', 'uiautomator', 'dump', '/sdcard/voice-real-test.xml');
  return adb('shell', 'cat', '/sdcard/voice-real-test.xml');
};
const waitUi = async text => {
  const deadline = Date.now() + 25000;
  while (Date.now() < deadline) {
    const value = await ui();
    if (value.includes('text="' + text + '"')) return value;
    await pause(300);
  }
  throw Error('App state not reached: ' + text);
};
const click = async text => {
  const value = await ui();
  const match = value.match(new RegExp('<node[^>]*text="' + text + '"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"'));
  if (!match) throw Error('App button not visible: ' + text);
  const [x1, y1, x2, y2] = match.slice(1).map(Number);
  await adb('shell', 'input', 'tap', String(Math.round((x1 + x2) / 2)), String(Math.round((y1 + y2) / 2)));
};
const logs = async () => {
  const response = await fetch(consoleUrl);
  if (!response.ok) throw Error('ESP32 console unavailable');
  return (await response.json()).lines;
};
const anchor = async () => (await logs()).at(-1) || '';
const command = async command => {
  const response = await fetch(consoleUrl, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command }) });
  if (!response.ok) throw Error('Device command rejected: ' + command);
};
const waitLog = async (pattern, after) => {
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    const match = (await logs()).find(line => line > after && pattern.test(line));
    if (match) return match;
    await pause(300);
  }
  throw Error('Expected ESP32 log missing: ' + pattern);
};
const image = async name => {
  await adb('shell', 'screencap', '-p', '/sdcard/voice-real-test.png');
  await adb('pull', '/sdcard/voice-real-test.png', `${output}/${name}.png`);
};
const audioPattern = /Send A:(\d+) \[(\d+):(\d+)\] Recv A:(\d+) \[(\d+):(\d+)\]/;
const connected = async (name, after, seconds) => {
  await waitUi('通话中');
  await waitLog(/reason=webrtc_connected/, after);
  const samples = new Map(), deadline = Date.now() + seconds * 1000;
  while (Date.now() < deadline) {
    for (const line of await logs()) {
      if (line <= after) continue;
      if (/Guru Meditation|PANIC|PeerConnectionState: 8|reason=webrtc_connect_failed/.test(line)) throw Error('ESP32 failed during ' + name);
      const match = line.match(audioPattern);
      if (match) {
        const values = match.slice(1).map(Number);
        if (values[1] > 0 && values[2] > 0 && values[4] > 0 && values[5] > 0) samples.set(line.slice(0, 26), {
          timestamp: line.slice(0, 26), sentPackets: values[1], sentBytes: values[2], receivedPackets: values[4], receivedBytes: values[5]
        });
      }
    }
    await pause(800);
  }
  if (samples.size < Math.floor(seconds / 4)) throw Error('Insufficient bidirectional audio samples for ' + name);
  await waitUi('通话中');
  await image(name);
  results.push({ scenario: name, connected: true, observedSeconds: seconds, audioSamples: [...samples.values()] });
  console.log('PASS', name, seconds + 's', samples.size + ' audio samples');
};

try {
  await adb('shell', 'am', 'start', '-n', 'com.youkong.voiceintercom/.MainActivity');
  const initial = await ui();
  if (!initial.includes('text="' + device + '"')) throw Error('App target differs from requested physical device');
  if (initial.includes('text="挂断通话"')) await click('挂断通话');
  await command('cmd close'); await waitUi('待机'); await pause(1500);

  let after = await anchor();
  await command('cmd ring'); await waitUi('设备来电'); await click('接听来电');
  await connected('esp32-calls-app', after, holdSeconds);
  const hangupAfter = await anchor();
  await click('挂断通话'); await waitUi('待机');
  await waitLog(/Received bye, closing connection/, hangupAfter);
  results.push({ scenario: 'app-hangup-received-by-esp32', passed: true });
  await pause(1500);

  after = await anchor();
  await click('呼叫设备'); await waitLog(/Offer cached, waiting for user/, after); await command('cmd answer');
  await connected('app-calls-esp32', after, holdSeconds);
  await command('cmd close'); await waitUi('待机');
  results.push({ scenario: 'esp32-hangup-received-by-app', passed: true });
  await pause(1500);

  after = await anchor();
  await command('cmd ring'); await waitUi('设备来电'); await click('拒接'); await waitUi('待机');
  await waitLog(/Received message type: reject|Call rejected by peer/, after);
  results.push({ scenario: 'app-rejects-esp32', passed: true });
  await pause(1500);

  after = await anchor();
  await click('呼叫设备'); await waitLog(/Offer cached, waiting for user/, after); await command('cmd reject');
  await waitUi('待机'); await waitLog(/Rejecting call from/, after);
  results.push({ scenario: 'esp32-rejects-app', passed: true });
  await pause(1500);

  after = await anchor();
  await command('cmd ring'); await waitUi('设备来电'); await click('接听来电');
  await connected('redial-after-hangup-and-reject', after, 15);
  await command('cmd close'); await waitUi('待机');

  await fs.writeFile(`${output}/results.json`, JSON.stringify({ passed: true, device, startedAt, completedAt: new Date().toISOString(),
    appVersion: '0.2-demo', androidEndpoint: 'API 29 emulator', transport: 'real ESP32-S3/ML307 4G, public WSS/MQTT/TURN', results }, null, 2));
  console.log('ALL REAL ESP32 CALL FLOW CHECKS PASSED');
} catch (error) {
  await fs.writeFile(`${output}/results.json`, JSON.stringify({ passed: false, device, startedAt, error: error.message, results }, null, 2));
  await image('failure').catch(() => {});
  console.error(error); process.exitCode = 1;
} finally {
  await command('cmd close').catch(() => {});
}
