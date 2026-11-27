const fs=require('node:fs/promises'),path=require('node:path'),net=require('node:net');
const {spawn,execFile}=require('node:child_process'),{promisify}=require('node:util'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),deps=path.join(root,'build/intercom-edge-test-runtime');
const dependency=name=>require(require.resolve(name,{paths:[deps]}));
const WS=dependency('ws'),broker=dependency('aedes')(),mqtt=dependency('mqtt');
const physical=process.argv[process.argv.indexOf('--real-device')+1];
const published=process.argv.includes('--public-smoke');
if(!process.argv.includes('--real-device')||physical!=='189833342344184')throw Error('Explicit demo device required');
const out=path.join(root,'build/call-alert-boundaries-'+Date.now()),pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const pkg=published?'com.youkong.voiceintercom':'com.youkong.voiceintercom.fixture',primary='edge_desk_a',second='edge_desk_b',virtual='county_b_fixture';
const bridge='http://127.0.0.1:18889',local='ws://127.0.0.1:18913/signaling',serial=process.env.VOICE_TEST_SERIAL||'127.0.0.1:5557';
const adb=(...args)=>promisify(execFile)('F:/android/sdk/platform-tools/adb.exe',['-s',serial,...args],{encoding:'utf8',timeout:18000}).then(r=>r.stdout);
const sockets=[],events=[],metrics=[],passed=[];let jar,client,server,live,virtualPhone,control,installed=false,reverse=false,physicalTouched=false;
const report={startedAt:new Date().toISOString(),physical,staging:!published,passed,metrics};
function checkpoint(name){passed.push(name);console.log('PASS',name);}
async function until(probe,description,ms=25000){let last;const stop=Date.now()+ms;do{try{let r=await probe();if(r)return r;}catch(e){last=e.message;}await pause(180);}while(Date.now()<stop);throw Error('Timeout: '+description+(last?' / '+last:''));}
async function connect(url,account){const socket=new WS(url);sockets.push(socket);socket.mail=[];socket.on('error',()=>{});socket.on('message',v=>socket.mail.push(JSON.parse(v)));
    await until(()=>socket.readyState===WS.OPEN,'open '+account);socket.sendMessage=(type,target,data,callId)=>socket.send(JSON.stringify({type,from:account,target,data,callId,timestamp:Math.floor(Date.now()/1000)}));
    socket.sendMessage('register');await until(()=>socket.mail.find(m=>m.type==='register_response'),'register '+account);return socket;}
async function ui(){await adb('shell','uiautomator','dump','/sdcard/voice-boundary.xml');return adb('shell','cat','/sdcard/voice-boundary.xml');}
async function click(name){let xml=await until(async()=>{let x=await ui();return x.includes('text="'+name+'"')?x:null;},'UI '+name);
    let m=xml.match(new RegExp('<node[^>]*text="'+name+'"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"'));assert(m);await adb('shell','input','tap',String((+m[1]+ +m[3])>>1),String((+m[2]+ +m[4])>>1));}
const waitUi=name=>until(async()=>{let s=await ui();return s.includes('text="'+name+'"')?s:null;},'UI '+name);
async function cmd(value){assert(['cmd ring','cmd answer','cmd close','cmd reject'].includes(value));const r=await fetch(bridge,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command:value})});assert(r.ok);}
const logs=async()=>(await(await fetch(bridge)).json()).lines;
const mark=async()=>(await logs()).at(-1)||'';
const newLog=(start,pattern)=>until(async()=>(await logs()).find(s=>s>start&&pattern.test(s)),'TTL '+pattern);
const audio=async(start,name)=>{const sample=await newLog(start,/Send A:\d+ \[[1-9]\d*:[1-9]\d*\] Recv A:\d+ \[[1-9]\d*:[1-9]\d*\]/);metrics.push({name,ttl:sample});};
const signal=(device,type,data)=>client.publishAsync('/voice/project/'+device+'/up',JSON.stringify({type,data,from:device,timestamp:Math.floor(Date.now()/1000)}),{qos:1});
const count=(items,kind)=>items.filter(item=>item.type===kind).length;
async function prefs(){const xml='<?xml version="1.0" encoding="utf-8"?><map><string name="server">http://127.0.0.1:18913</string><string name="device">'+physical+'</string><string name="local">'+primary+'</string></map>';
    const f=path.join(out,'fixture-prefs.xml');await fs.writeFile(f,xml);await adb('push',f,'/data/local/tmp/voice-boundary-prefs.xml');await adb('shell','run-as',pkg,'mkdir','-p','shared_prefs');await adb('shell','run-as',pkg,'cp','/data/local/tmp/voice-boundary-prefs.xml','shared_prefs/intercom.xml');}
async function startApp(){await adb('shell','am','start','-n',pkg+'/com.youkong.voiceintercom.MainActivity');await waitUi('待机');}
async function publicSmoke(){
    const origin='https://voice.2811.top', crypto=require('node:crypto');
    const file=await fetch(origin+'/apks/voice-intercom-demo.apk?v=0.6');assert(file.ok);
    const apk=Buffer.from(await file.arrayBuffer()),sha=value=>crypto.createHash('sha256').update(value).digest('hex');
    assert.equal(sha(apk),sha(await fs.readFile(path.join(root,'outputs/android/voice-intercom-demo.apk'))));
    await fs.writeFile(path.join(out,'demo.apk'),apk);await adb('install','-r',path.join(out,'demo.apk'));
    const configured=await adb('shell','run-as',pkg,'cat','shared_prefs/intercom.xml');assert(configured.includes(physical)&&configured.includes('web_client_001')&&configured.includes(origin));
    await startApp();await until(async()=>(await ui()).includes('服务已连接'),'public phone registered');
    const caller=await connect('wss://voice.2811.top/signaling','demo_boundary_secondary');assert.equal(caller.mail.find(m=>m.type==='register_response').version,2);
    physicalTouched=true;let anchor=await mark();await cmd('cmd ring');await waitUi('设备来电');await click('接听来电');await waitUi('通话中');await audio(anchor,'public physical outgoing');
    const {chromium}=require(process.env.VOICE_TEST_PLAYWRIGHT||'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
    const browser=await chromium.launch({executablePath:process.env.VOICE_TEST_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
    try{const page=await browser.newPage();const sdp=await page.evaluate(async()=>{const peer=new RTCPeerConnection();window.testCall=peer;peer.addTransceiver('audio');const offer=await peer.createOffer();await peer.setLocalDescription(offer);return offer.sdp;});
        const id=crypto.randomUUID();caller.sendMessage('offer',physical,sdp,id);await until(()=>caller.mail.find(m=>m.callId===id&&m.type==='reject'&&m.data==='busy'),'public second caller busy');
        anchor=await mark();await audio(anchor,'public physical RTP after confirmed busy');await waitUi('通话中');
    }finally{await browser.close();}
    checkpoint('published APK: real outbound, second WebRTC caller receives busy and first call keeps two-way audio');
    await click('挂断通话');await waitUi('待机');await click('呼出预警记录');await until(async()=>(await ui()).includes('4G呼叫器发起呼叫'),'public alert visible');
    await adb('shell','screencap','-p','/sdcard/voice-public-alert.png');await adb('pull','/sdcard/voice-public-alert.png',path.join(out,'call-alert.png'));await click('关闭');
    checkpoint('published APK displays new device alert');
    await pause(2100);anchor=await mark();await click('呼叫设备');await newLog(anchor,/Offer cached/);await cmd('cmd reject');await waitUi('待机');
    checkpoint('public App to physical device, operator reject returns phone to idle');report.ok=true;
}
async function main(){await fs.mkdir(out,{recursive:true});console.log('RESULT',out);
    if(published){await publicSmoke();return;}
    server=net.createServer(broker.handle);await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(18914,'127.0.0.1',resolve);});
    client=await mqtt.connectAsync('mqtt://127.0.0.1:18914');await client.subscribeAsync('/voice/project/+/down');
    jar=spawn('F:/android/Java/jdk1.8.0_361/bin/java.exe',['-jar',path.join(root,'audio_server/target/demo-0.0.1-SNAPSHOT.jar'),'--server.address=127.0.0.1','--server.port=18913','--spring.mqtt.broker-url=tcp://127.0.0.1:18914','--spring.mqtt.client-id=edge-stage','--signaling.project=project','--signaling.persistence.enabled=false','--logging.level.root=WARN','--signaling.dispatch='+physical+'='+primary+','+virtual+'='+second],{cwd:out,stdio:'ignore',windowsHide:true});
    await until(async()=>(await fetch('http://127.0.0.1:18913/api/devices/'+physical+'/telemetry')).ok,'start candidate backend',45000);
    virtualPhone=await connect(local,second);control=await connect(local,'edge_other_operator');
    await adb('install','-r',path.join(root,'android/app/build/outputs/apk/loopback/app-loopback.apk'));installed=true;
    await adb('shell','am','force-stop',pkg);await prefs();await adb('reverse','tcp:18913','tcp:18913');reverse=true;
    for(const permission of ['RECORD_AUDIO','POST_NOTIFICATIONS'])await adb('shell','pm','grant',pkg,'android.permission.'+permission).catch(()=>{});
    await startApp();await click('呼出预警记录');await waitUi('暂无设备呼出预警');await click('关闭');
    live=await connect('wss://voice.2811.top/signaling','web_client_001');
    live.on('message',async raw=>{let m=JSON.parse(raw);if(m.from!==physical||!['offer','answer','candidate','ring','customized','bye','reject','timeout'].includes(m.type))return;
        delete m.callId;delete m.target;await client.publishAsync('/voice/project/'+physical+'/up',JSON.stringify(m),{qos:1});});
    client.on('message',(topic,bytes)=>{const device=topic.split('/')[3],m=JSON.parse(bytes);events.push({device,type:m.type,data:m.data==='busy'?'busy':undefined});
        if(device!==physical)return;
        if(m.type==='offer' && !String(m.data).startsWith('v=0'))return;
        live.send(JSON.stringify({...m,from:'web_client_001',target:physical}));});
    physicalTouched=true;await cmd('cmd close');await pause(2400);
    let anchor=await mark();await cmd('cmd ring');await waitUi('设备来电');await click('接听来电');await waitUi('通话中');await audio(anchor,'real outbound');checkpoint('real outgoing call with two-way RTP');
    let cursor=await mark();control.sendMessage('offer',physical,'local-fixture','contest-1');
    await until(()=>control.mail.find(m=>m.callId==='contest-1'&&m.data==='busy'),'second operator busy');
    await signal(virtual,'offer','fixture-b');const other=await until(()=>virtualPhone.mail.find(m=>m.type==='offer'),'independent county B offer');
    virtualPhone.sendMessage('answer',virtual,'fixture-answer',other.callId);await until(()=>events.some(m=>m.device===virtual&&m.type==='answer'),'county B answer');
    virtualPhone.sendMessage('bye',virtual,null,other.callId);await until(()=>events.some(m=>m.device===virtual&&m.type==='bye'),'county B hangup');
    await audio(cursor,'after contention and independent hangup');await waitUi('通话中');checkpoint('same driver busy; other county setup/teardown; original audio survives');
    await click('挂断通话');await waitUi('待机');await pause(2200);
    anchor=await mark();await click('呼叫设备');await newLog(anchor,/Offer cached/);control.sendMessage('offer',physical,'local-fixture','contest-2');
    await until(()=>control.mail.find(m=>m.callId==='contest-2'&&m.data==='busy'),'busy while ringing');await cmd('cmd answer');await waitUi('通话中');await audio(anchor,'real inbound');checkpoint('real incoming call survives second caller during ringing');
    await cmd('cmd close');await waitUi('待机');await pause(2200);
    await click('呼出预警记录');let display=await ui();assert(display.includes('4G呼叫器发起呼叫'));await fs.writeFile(path.join(out,'alerts-ui.xml'),display);
    await adb('shell','screencap','-p','/sdcard/call-alert.png');await adb('pull','/sdcard/call-alert.png',path.join(out,'call-alert.png'));await click('关闭');
    await adb('shell','am','force-stop',pkg);await pause(2200);
    anchor=await mark();await cmd('cmd ring');await newLog(anchor,/Received reject|remote_reject|Call rejected/);await startApp();
    await click('呼出预警记录');await until(async()=>((await ui()).match(/4G呼叫器发起呼叫/g)||[]).length===2,'offline alert restored');checkpoint('real outbound while phone offline is recorded; App reconnect shows exactly two alerts');
    virtualPhone.sendMessage('alert_history',virtual);const history=await until(()=>virtualPhone.mail.find(m=>m.type==='alert_history'),'county B history');assert.equal(history.data.length,1);assert.equal(history.data[0].device,virtual);checkpoint('county-specific inbox');
    report.ok=true;
}
main().catch(e=>{console.error(e.message);report.error=e.message;process.exitCode=1;}).finally(async()=>{
    if(physicalTouched)await cmd('cmd close').catch(()=>{});if(installed)await adb('shell','am','force-stop',pkg).catch(()=>{});
    sockets.forEach(s=>s.terminate());if(reverse)await adb('reverse','--remove','tcp:18913').catch(()=>{});
    if(jar)jar.kill();if(client)await client.endAsync(true);if(server)server.close();broker.close();
    report.endedAt=new Date().toISOString();await fs.writeFile(path.join(out,'results.json'),JSON.stringify(report,null,2));
});
