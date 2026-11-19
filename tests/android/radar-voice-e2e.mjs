// Actual ESP32 call + separate radar observation. Uses an isolated App caller ID.
import {execFile} from 'node:child_process';
import fs from 'node:fs/promises';
const args=process.argv.slice(2),at=args.indexOf('--real-device');
if(at<0||!/^[0-9]{12,20}$/.test(args[at+1]))throw Error('Specify --real-device DEVICE_ID');
const device=args[at+1],output='build/radar-voice-e2e',startedAt=new Date().toISOString(),results=[];
await fs.mkdir(output,{recursive:true});
const serial=process.env.VOICE_TEST_SERIAL||'emulator-5556';
const adb=(...values)=>new Promise((resolve,reject)=>execFile(process.env.VOICE_TEST_ADB||'adb',['-s',serial,...values],{encoding:'utf8',timeout:20000},(e,s)=>e?reject(e):resolve(s)));
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const ui=async()=>{await adb('shell','uiautomator','dump','/sdcard/radar-voice-test.xml');return adb('shell','cat','/sdcard/radar-voice-test.xml');};
const click=async label=>{
 const xml=await ui(),m=xml.match(new RegExp('<node[^>]*text="'+label+'"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"'));
 if(!m)throw Error('Missing App control '+label);
 const [x1,y1,x2,y2]=m.slice(1).map(Number);await adb('shell','input','tap',String((x1+x2)>>1),String((y1+y2)>>1));
};
const waitUi=async label=>{const deadline=Date.now()+30000;while(Date.now()<deadline){if((await ui()).includes('text="'+label+'"'))return;await delay(500);}throw Error('App state missing '+label);};
const consoleUrl=process.env.VOICE_TEST_CONSOLE||'http://127.0.0.1:18889';
const logs=async()=>(await (await fetch(consoleUrl)).json()).lines;
const command=async command=>{const r=await fetch(consoleUrl,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command})});if(!r.ok)throw Error('Console rejected command');};
const telemetry=async()=>{const r=await fetch(`https://voice.2811.top/api/devices/${device}/telemetry`);if(!r.ok)throw Error('Telemetry endpoint unavailable');return r.json();};
const waitLog=async(pattern,after)=>{const deadline=Date.now()+30000;while(Date.now()<deadline){if((await logs()).some(l=>l>after&&pattern.test(l)))return;await delay(400);}throw Error('ESP32 log missing '+pattern);};
const image=async name=>{await adb('shell','screencap','-p','/sdcard/radar-voice-test.png');await adb('pull','/sdcard/radar-voice-test.png',`${output}/${name}.png`);};
const anchor=async()=>(await logs()).at(-1)||'';
const checkAudio=async(name,after,seconds)=>{
 await waitUi('通话中');await waitLog(/reason=webrtc_connected/,after);await delay(2000);
 const first=await telemetry(),samples=new Map(),radarFrames=[];
 const deadline=Date.now()+seconds*1000;
 while(Date.now()<deadline){
  const state=await telemetry();if(state.received_at_ms!==first.received_at_ms)throw Error('Radar uploaded during active call');
  for(const line of await logs()){
   if(line<=after)continue;
   if(/Guru Meditation|Backtrace:|reason=webrtc_connect_failed/.test(line))throw Error('ESP32 failure');
   const m=line.match(/Send A:\d+ \[(\d+):(\d+)\] Recv A:\d+ \[(\d+):(\d+)\]/);
   if(m&&m.slice(1).every(v=>Number(v)>0))samples.set(line.slice(0,26),m.slice(1).map(Number));
   const radar=line.match(/RADAR_GPIO5: STATUS .* valid=(\d+)/);if(radar)radarFrames.push(Number(radar[1]));
  }
  await delay(1000);
 }
 if(samples.size<Math.floor(seconds/5))throw Error('Insufficient bidirectional audio statistics');
 if(Math.max(...radarFrames)<=Math.min(...radarFrames))throw Error('Radar receiver stopped during call');
 await waitUi('通话中');await image(name);
 results.push({scenario:name,observedSeconds:seconds,bidirectionalAudioSamples:samples.size,radarContinued:true,uploadsPaused:true});
 console.log('PASS',name);
 return first.received_at_ms;
};
try{
 const prefs=await adb('shell','run-as','com.youkong.voiceintercom','cat','shared_prefs/intercom.xml');
 if(!prefs.includes(device)||!prefs.includes('lead_demo_test_20261119'))throw Error('Configure isolated lead_demo_test_20261119 caller first');
 await adb('shell','am','start','-n','com.youkong.voiceintercom/.MainActivity');
 await command('cmd close');await waitUi('待机');
 const initial=await telemetry();if(!initial.online||initial.radar?.radar!=='r60abd1')throw Error('Real radar unavailable');
 await image('radar-ready');
 let after=await anchor();await click('呼叫设备');await waitLog(/Offer cached, waiting for user/,after);
 await waitLog(/Playing tone=incoming duration_ms=4000/,after);
 results.push({scenario:'esp32-incoming-ring-triggered',passed:true});
 await command('cmd answer');
 const previousReport=await checkAudio('call-with-radar',after,35);
 await click('麦克风开');await waitUi('麦克风关');await click('麦克风关');
 await click('挂断通话');await waitUi('待机');
 const deadline=Date.now()+15000;let resumed=false;
 while(Date.now()<deadline){const s=await telemetry();if(s.online&&s.received_at_ms>previousReport){resumed=true;break;}await delay(500);}
 if(!resumed)throw Error('Radar uploads did not resume');
 results.push({scenario:'app-hangup-radar-resumes',passed:true});
 after=await anchor();await click('呼叫设备');await waitLog(/Offer cached, waiting for user/,after);await command('cmd answer');
 await checkAudio('repeat-call-with-radar',after,15);await command('cmd close');await waitUi('待机');
 results.push({scenario:'esp32-hangup',passed:true});
 after=await anchor();await click('呼叫设备');await waitLog(/Offer cached, waiting for user/,after);await command('cmd reject');await waitUi('待机');
 results.push({scenario:'esp32-reject',passed:true});
 await fs.writeFile(`${output}/results.json`,JSON.stringify({passed:true,startedAt,completedAt:new Date().toISOString(),appVersion:'0.3-demo',endpoint:'API29 emulator / real ESP32-S3 + ML307 4G / public WSS MQTT TURN',results},null,2));
}catch(error){
 await fs.writeFile(`${output}/results.json`,JSON.stringify({passed:false,startedAt,error:error.message,results},null,2));await image('failure').catch(()=>{});console.error(error);process.exitCode=1;
}finally{await command('cmd close').catch(()=>{});}
