// Explicit physical device, isolated App ID; no firmware protocol changes.
// Requires the COM13 bridge. Observes modem boot/registration URCs and RTP.
import {execFile} from 'node:child_process';
import fs from 'node:fs/promises';
import {MqttProbe} from './mqtt-probe.mjs';
const args=process.argv.slice(2),index=args.indexOf('--real-device');
const device=index>=0?args[index+1]:'';
if(!/^\d{12,20}$/.test(device))throw Error('Specify --real-device DEVICE_ID');
const hold=Number(process.env.VOICE_TEST_HOLD_SECONDS || 180);
if(!Number.isFinite(hold) || hold<20 || hold>600)throw Error('Hold range 20..600 seconds');
const output=process.env.VOICE_TEST_OUTPUT || 'build/real-network-recovery';
await fs.mkdir(output,{recursive:true});
const pkg='com.youkong.voiceintercom',local='demo_real_recovery_'+Date.now();
const adb=(...args)=>new Promise((resolve,reject)=>execFile(process.env.VOICE_TEST_ADB || 'adb',['-s',process.env.VOICE_TEST_SERIAL || '127.0.0.1:5557',...args],{encoding:'utf8',timeout:15000},(e,v)=>e?reject(e):resolve(v)));
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const bridge=process.env.VOICE_TEST_CONSOLE || 'http://127.0.0.1:18889';
const logs=async()=>(await (await fetch(bridge)).json()).lines;
const command=async value=>{const r=await fetch(bridge,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command:value})});if(!r.ok)throw Error('Console command rejected');};
const ui=async()=>{await adb('shell','uiautomator','dump','/sdcard/recovery-ui.xml');return adb('shell','cat','/sdcard/recovery-ui.xml');};
const waitUi=async label=>{const deadline=Date.now()+30000;while(Date.now()<deadline){if((await ui()).includes(`text="${label}"`))return;await delay(300);}throw Error('Missing native state '+label);};
const click=async label=>{const m=(await ui()).match(new RegExp('<node[^>]*text="'+label+'"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"'));if(!m)throw Error('Missing control '+label);const [x,y,r,b]=m.slice(1).map(Number);await adb('shell','input','tap',String((x+r)>>1),String((y+b)>>1));};
const waitLog=async(pattern,after)=>{const deadline=Date.now()+30000;while(Date.now()<deadline){if((await logs()).some(l=>l>after && pattern.test(l)))return;await delay(300);}throw Error('Expected device event missing '+pattern);};
const result={device,local,startedAt:new Date().toISOString(),modemEvents:[],audioSamples:[],iceRefreshIgnored:false,passed:false};
let original=null,mqtt=null,anchor='',seen=new Set();
function observe(lines){
    for(const line of lines){if(line<=anchor || seen.has(line))continue;seen.add(line);
        if(/MODEM_EVT|网络状态:|ICE refresh ignored/.test(line))result.modemEvents.push(line);
        if(/ICE refresh ignored during connected call/.test(line))result.iceRefreshIgnored=true;
        const m=line.match(/Send A:\d+ \[(\d+):(\d+)\] Recv A:\d+ \[(\d+):(\d+)\]/);
        if(m)result.audioSamples.push({at:line.slice(0,26),sentPackets:Number(m[1]),sentBytes:Number(m[2]),receivedPackets:Number(m[3]),receivedBytes:Number(m[4])});
        if(/MATREADY/.test(line))result.modemBootObserved=true;
        if(/Fail to new connection|Fail to get local description|Guru Meditation|reason=webrtc_connect_failed/.test(line))result.failureEvent=line;
    }
}
try{
    original=await adb('shell','run-as',pkg,'cat','shared_prefs/intercom.xml').catch(()=>null);
    await adb('shell','am','force-stop',pkg);
    await fs.writeFile(`${output}/preferences.xml`,`<?xml version="1.0" encoding="utf-8"?><map><string name="server">https://voice.2811.top</string><string name="device">${device}</string><string name="local">${local}</string></map>`);
    await adb('push',`${output}/preferences.xml`,'/data/local/tmp/recovery-prefs.xml');await adb('shell','run-as',pkg,'mkdir','-p','shared_prefs');await adb('shell','run-as',pkg,'cp','/data/local/tmp/recovery-prefs.xml','shared_prefs/intercom.xml');
    await adb('shell','am','start','-n',pkg+'/.MainActivity');await waitUi('呼叫设备');await delay(2000);
    anchor=(await logs()).at(-1)||'';await click('呼叫设备');await waitLog(/Offer cached, waiting for user/,anchor);await command('cmd answer');await waitUi('通话中');await waitLog(/reason=webrtc_connected/,anchor);
    // Fetch exactly the App's server-issued ICE info via a separate observation
    // WebSocket; forward a standard duplicate response through the real MQTT.
    // No credentials or full SDP are included in output/results.
    const {createRequire}=await import('node:module');
    const require=createRequire((process.env.VOICE_TEST_PLAYWRIGHT || process.cwd()+'/build/radar-browser-tools')+'/package.json');
    const {chromium}=require('playwright');
    const browser=await chromium.launch({executablePath:process.env.VOICE_TEST_BROWSER,headless:true,args:['--no-proxy-server']});
    let ice;
    try{const page=await browser.newPage();await page.goto('https://voice.2811.top/demo.html');ice=await page.evaluate(id=>new Promise((resolve,reject)=>{
        const ws=new WebSocket('wss://voice.2811.top/signaling');const timeout=setTimeout(()=>{ws.close();reject(Error('ICE timeout'));},10000);
        ws.onopen=()=>ws.send(JSON.stringify({type:'ice_request',from:id,timestamp:Math.floor(Date.now()/1000)}));ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.type==='ice_response'){clearTimeout(timeout);ws.close();resolve(m.iceServers);}else if(m.type==='error'){clearTimeout(timeout);ws.close();reject(Error('ICE request rejected'));}};
    }),local+'_ice');}finally{await browser.close();}
    mqtt=new MqttProbe('118.31.113.169',device,()=>{});await mqtt.ready;
    mqtt.write(0x30,Buffer.concat([mqtt.field('/voice/project/'+device+'/down'),Buffer.from(JSON.stringify({type:'ice_response',iceServers:ice,valid:true,timestamp:Math.floor(Date.now()/1000)}))]));
    await waitLog(/ICE refresh ignored during connected call/,anchor);
    const deadline=Date.now()+hold*1000;
    while(Date.now()<deadline){observe(await logs());if(result.failureEvent)throw Error('Peer failed during observation');
        const valid=result.audioSamples.filter(s=>s.sentBytes>0 && s.receivedBytes>0).at(-1);
        if(valid && Date.now()-Date.parse(valid.at)>12000)throw Error('Bidirectional audio stopped for over 12 seconds');
        await delay(1000);
    }
    observe(await logs());await waitUi('通话中');
    if(!result.iceRefreshIgnored || result.audioSamples.filter(s=>s.receivedBytes>0 && s.sentBytes>0).length<hold/4)throw Error('Insufficient connected audio samples');
    result.passed=true;result.observedSeconds=hold;console.log('PASS real-device ICE refresh / audio observation',hold+'s');
}catch(error){result.error=error.message;observe(await logs().catch(()=>[]));console.error(error.message);process.exitCode=1;}
finally{
    if(mqtt)mqtt.close();await command('cmd close').catch(()=>{});await adb('shell','am','force-stop',pkg).catch(()=>{});
    if(original!==null){await fs.writeFile(`${output}/original-prefs.xml`,original);await adb('push',`${output}/original-prefs.xml`,'/data/local/tmp/recovery-original.xml');await adb('shell','run-as',pkg,'cp','/data/local/tmp/recovery-original.xml','shared_prefs/intercom.xml');}
    else await adb('shell','run-as',pkg,'rm','-f','shared_prefs/intercom.xml').catch(()=>{});
    result.completedAt=new Date().toISOString();await fs.writeFile(`${output}/results.json`,JSON.stringify(result,null,2));
}
