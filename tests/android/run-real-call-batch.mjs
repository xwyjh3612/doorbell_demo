// Physical ESP32/ML307 calls through the native Android App. Connected failures
// count as failed rounds; computer interruptions are excluded and replaced.
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn, execFile} from 'node:child_process';
import {writeState,readState} from './state-file.mjs';
import {summarizeAttempts,nextCallDirection} from './call-batch-counts.mjs';

const args=process.argv.slice(2);
const option=(name,fallback)=>{const i=args.indexOf(name);return i<0?fallback:args[i+1];};
const device=option('--real-device','');
const rounds=Number(option('--rounds','30'));
const hold=Number(option('--hold-seconds','1800'));
const startDirection=option('--start-direction','app-calls-device');
if(!['app-calls-device','device-calls-app'].includes(startDirection))throw Error('Invalid start direction');
if(!/^\d{12,20}$/.test(device)||!Number.isInteger(rounds)||rounds<1||rounds>100||!Number.isInteger(hold)||hold<20||hold>1800)throw Error('Invalid device/rounds/hold');
const root=process.cwd(), output=path.resolve(option('--output','build/real-call-at-recovery-30'));
const bridge=process.env.VOICE_TEST_CONSOLE || 'http://127.0.0.1:18889';
const allowRestart=args.includes('--allow-modem-restart');
const resume=args.includes('--resume');
const imagePath=path.resolve(option('--firmware','outputs/firmware/voice-radar60.json'));
const image=JSON.parse(await fs.readFile(imagePath,'utf8'));
if(!resume)await fs.mkdir(output,{recursive:false});
const state=resume?await readState(path.join(output,'state.json')):{startedAt:new Date().toISOString(),requestedConnectedRounds:rounds,targetSecondsPerRound:hold,
  // Existing ESP32 offers omit target; the deployed service defaults those
  // offers to web_client_001. Preserve that behavior in this transport test.
  localAppId:option('--app-id','web_client_001'),
  firmware:image,transport:'ML307R-DL UART AT; original latest UDP packet strategy',
  endpoint:'native Android App / physical ESP32-S3 over public WSS/MQTT/TURN',
  allowModemRestart:allowRestart,startDirection,excludeSupervisorInterruptions:true,
  completedConnectedRounds:0,passedRounds:0,attempts:[],recoveries:[],phase:'starting',finished:false};
state.excludeSupervisorInterruptions=true;
state.startDirection ||= startDirection;
Object.assign(state,summarizeAttempts(state.attempts));
if(resume){
  if(state.firmware.sha256!==image.sha256||state.targetSecondsPerRound!==hold||state.localAppId!==option('--app-id','web_client_001'))throw Error('Resume cohort configuration mismatch');
  const previousError=state.error;
  state.supervisorInterruptions ||= [];
  state.supervisorInterruptions.push({at:new Date().toISOString(),previousError,previousCompletedAt:state.completedAt});
  // Preserve a connected round whose child finished after its supervisor exited.
  for(let index=state.attempts.length+1;;++index){
    let result;
    try{result=JSON.parse(await fs.readFile(path.join(output,`attempt-${index}`,'results.json'),'utf8'));}catch{break;}
    const samples=result.audioSamples||[],gaps=samples.slice(1).map((s,i)=>(Date.parse(s.at)-Date.parse(samples[i].at))/1000);
    const summary={attempt:index,round:result.connectedAt?state.completedConnectedRounds+1:null,
      direction:nextCallDirection(state.attempts,state.startDirection),
      connectedAt:result.connectedAt||null,completedAt:result.completedAt,passed:false,
      error:result.error||previousError,supervisorError:previousError,failureClassification:'test-supervisor-interruption',
      observedSeconds:result.observedSeconds||null,lastAudioAt:samples.at(-1)?.at||null,
      firstAfeAlert:result.firstAfeAlert||null,failureEvent:result.failureEvent||null,
      audioSamples:samples.length,bidirectionalSamples:samples.filter(s=>s.sentBytes>0&&s.receivedBytes>0).length,
      maxStatisticsGapSeconds:gaps.length?Math.max(...gaps):null,afeAlerts:result.afeAlerts||0};
    state.attempts.push(summary);
    await fs.writeFile(path.join(output,`attempt-${index}`,'supervisor-interruption.json'),JSON.stringify(summary,null,2));
    Object.assign(state,summarizeAttempts(state.attempts));
  }
  if(rounds<state.completedConnectedRounds)throw Error('Target below completed rounds');
  state.requestedConnectedRounds=rounds;state.allowModemRestart=allowRestart;
  state.failedConnectedRounds=state.completedConnectedRounds-state.passedRounds;
  state.finished=false;state.phase='resuming';state.active=null;
  delete state.error;delete state.completedAt;delete state.allPassed;
}
const save=async()=>{
  Object.assign(state,summarizeAttempts(state.attempts));
  state.updatedAt=new Date().toISOString();
  await writeState(path.join(output,'state.json'),state);
};
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const logs=async()=>{const r=await fetch(bridge,{signal:AbortSignal.timeout(5000)});if(!r.ok)throw Error('Console unavailable');return (await r.json()).lines;};
const command=async value=>{const r=await fetch(bridge,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command:value}),signal:AbortSignal.timeout(5000)});if(!r.ok)throw Error('Console rejected '+value);};
const adb=(...values)=>new Promise((resolve,reject)=>execFile(process.env.VOICE_TEST_ADB||'adb',
  ['-s',process.env.VOICE_TEST_SERIAL||'127.0.0.1:5557',...values],{encoding:'utf8',timeout:15000},(e,v)=>e?reject(e):resolve(v)));
let nextHumanProgress=0, restartStreak=0, originalPreferences=null;
async function recover(reason){
  state.phase='waiting_for_recovery';await save();
  const entry={at:new Date().toISOString(),reason,action:'passive-wait-before-explicit-restart',restartRequested:false};
  state.recoveries.push(entry);await save();
  const after=(await logs()).at(-1)||'';
  await command('cmd close');
  // Keep spontaneous recovery distinct from commanded recovery. Repeated close
  // confirms the call worker has returned to idle after media teardown.
  const deadline=Date.now()+75000;let idle=false;
  while(Date.now()<deadline){
    const current=await logs();
    if(current.some(l=>l>after&&/当前已经空闲，忽略挂断请求/.test(l)))idle=true;
    if(idle&&current.some(l=>l>after&&/MQTT signaling restarted, subscribed/.test(l))){entry.result='spontaneous-recovery';await save();return;}
    if(!idle)await command('cmd close');
    await pause(5000);
  }
  if(!idle){entry.result='call-worker-did-not-return-to-idle';await save();throw Error('Call teardown is blocked; no verified hardware modem reset line');}
  if(!allowRestart){entry.result='restart-not-enabled';await save();return;}
  if(restartStreak>=3){entry.result='three-restarts-without-connected-call';await save();throw Error('Three modem restarts did not restore a connected call');}
  const latestRestart=state.recoveries.filter(r=>r.restartRequested).at(-1);
  while(latestRestart&&Date.now()-Date.parse(latestRestart.restartAt)<125000)await pause(5000);
  const anchor=(await logs()).at(-1)||'';
  entry.restartRequested=true;entry.restartAt=new Date().toISOString();entry.action='explicit-idle-AT-MREBOOT';++restartStreak;
  state.phase='restarting_modem';await save();await command('modem restart');
  const limit=Date.now()+180000;let notice=false, ready=false;
  while(Date.now()<limit){
    const current=await logs();
    if(current.some(l=>l>anchor&&/Guru Meditation|Brownout|A stack overflow|abort\(\) was called/.test(l)))throw Error('ESP crash during recovery');
    notice ||=current.some(l=>l>anchor&&/MODEM_EVT MATREADY/.test(l));
    ready ||=current.some(l=>l>anchor&&/MQTT signaling restarted, subscribed/.test(l));
    if(notice&&ready){entry.result='boot-notice-and-signaling-restored';entry.completedAt=new Date().toISOString();await save();return;}
    await pause(5000);
  }
  entry.result=notice?'modem-booted-signaling-not-restored':'no-observed-modem-boot';await save();
  // AT can fail when the module is in a bad input state. Report honestly;
  // GPIO4/EN is not a verified reset and is never toggled speculatively.
}
await save();
try{
  if(!(await adb('shell','pm','list','packages','com.youkong.voiceintercom')).includes('com.youkong.voiceintercom'))throw Error('Native App missing');
  originalPreferences=resume?await fs.readFile(path.join(output,'original-app-preferences.xml'),'utf8').catch(()=>null):
    await adb('shell','run-as','com.youkong.voiceintercom','cat','shared_prefs/intercom.xml').catch(()=>null);
  if(!resume&&originalPreferences!==null)await fs.writeFile(path.join(output,'original-app-preferences.xml'),originalPreferences);
  await logs();
  while(state.completedConnectedRounds<rounds){
    if(state.attempts.length>=rounds*4)throw Error('Setup attempt limit reached');
    const index=state.attempts.length+1, round=state.completedConnectedRounds+1;
    const direction=nextCallDirection(state.attempts,state.startDirection);
    const attemptOutput=path.join(output,`attempt-${index}`);await fs.mkdir(attemptOutput);
    const began=new Date().toISOString();
    const source=path.join(root,'build/esp32-real-call-live.log');
    const offset=(await fs.stat(source)).size;
    state.phase='calling';state.active={attempt:index,round,direction,output:attemptOutput,startedAt:began};await save();
    console.log(`Starting connected round ${round}/${rounds}; ${direction}; target ${hold}s`);
    const stdout=await fs.open(path.join(attemptOutput,'runner.stdout.log'),'w');
    const stderr=await fs.open(path.join(attemptOutput,'runner.stderr.log'),'w');
    const child=spawn(process.execPath,['tests/android/real-esp32-network-recovery.mjs','--real-device',device],{
      cwd:root,windowsHide:true,stdio:['ignore',stdout.fd,stderr.fd],env:{...process.env,
        VOICE_TEST_DIRECTION:direction,VOICE_TEST_HOLD_SECONDS:String(hold),VOICE_TEST_SKIP_ICE_REFRESH:'1',
        VOICE_TEST_LOCAL_ID:state.localAppId,
        VOICE_TEST_SAFE_DIAGNOSTICS:'0',VOICE_TEST_OUTPUT:attemptOutput}});
    let exitCode,done=false,childError=null;
    child.on('error',e=>{childError=e;done=true;});child.on('exit',code=>{exitCode=code;done=true;});
    const hardDeadline=Date.now()+(hold+240)*1000;
    while(!done){
      try{const progress=JSON.parse(await fs.readFile(path.join(attemptOutput,'progress.json'),'utf8'));
        state.active.connectedAt=progress.connectedAt||null;state.active.audioSamples=progress.audioSamples.length;
        state.active.bidirectionalSamples=progress.audioSamples.filter(s=>s.sentBytes>0&&s.receivedBytes>0).length;
        state.active.afeAlerts=progress.afeAlerts;state.active.modemBootObserved=!!progress.modemBootObserved;
      }catch{}
      await save();
      if(Date.now()>=nextHumanProgress){console.log(`Progress: round ${round}, connected=${!!state.active.connectedAt}, audio=${state.active.bidirectionalSamples||0}, AFE=${state.active.afeAlerts||0}`);nextHumanProgress=Date.now()+300000;}
      if(Date.now()>hardDeadline){child.kill();childError=Error('Round exceeded observation/cleanup deadline');break;}
      await pause(5000);
    }
    await stdout.close();await stderr.close();
    let result;
    try{result=JSON.parse(await fs.readFile(path.join(attemptOutput,'results.json'),'utf8'));}catch{
      try{result=JSON.parse(await fs.readFile(path.join(attemptOutput,'progress.json'),'utf8'));}catch{result={};}
      result.passed=false;result.error=childError?.message||'Missing final results';
    }
    const consoleFile=await fs.open(source,'r');
    const size=(await consoleFile.stat()).size-offset;const bytes=Buffer.alloc(Math.max(size,0));
    if(size>0)await consoleFile.read(bytes,0,size,offset);await consoleFile.close();
    const text=bytes.toString('utf8');await fs.writeFile(path.join(attemptOutput,'session-console.log'),text);
    const eventLines=text.split('\n').filter(l=>/AT_DIAG|AT_RX_DIAG|MATREADY|AFE: Ringbuffer|网络状态:|通话状态切换:|MODEM_RECOVERY|Guru Meditation|Brownout|A stack overflow|abort\(\) was called/.test(l));
    const samples=result.audioSamples||[], gaps=samples.slice(1).map((s,i)=>(Date.parse(s.at)-Date.parse(samples[i].at))/1000);
    const summary={attempt:index,round:result.connectedAt?round:null,direction,connectedAt:result.connectedAt||null,
      completedAt:result.completedAt||new Date().toISOString(),passed:result.passed===true,exitCode,
      observedSeconds:result.observedSeconds||null,error:result.error||childError?.message||null,
      firstAfeAlert:result.firstAfeAlert||null,failureEvent:result.failureEvent||null,
      audioSamples:samples.length,bidirectionalSamples:samples.filter(s=>s.sentBytes>0&&s.receivedBytes>0).length,
      maxStatisticsGapSeconds:gaps.length?Math.max(...gaps):null,
      capturedAfeIncludingCleanup:eventLines.filter(l=>/AFE: Ringbuffer/.test(l)).length,
      capturedAtErrorsIncludingCleanup:eventLines.filter(l=>/AT_DIAG/.test(l)).length,
      capturedModemBootIncludingCleanup:eventLines.filter(l=>/MATREADY/.test(l)).length};
    await fs.writeFile(path.join(attemptOutput,'observed-timeline.json'),JSON.stringify({summary,eventLines},null,2));
    state.attempts.push(summary);state.active=null;
    if(summary.connectedAt)restartStreak=0;
    Object.assign(state,summarizeAttempts(state.attempts));
    await save();console.log(`Attempt ${index}: ${summary.connectedAt?'connected':'setup failed'} ${summary.passed?'PASS':'FAIL'}; ${state.completedConnectedRounds}/${rounds}, passed=${state.passedRounds}`);
    if(!summary.passed)await recover(summary.error||'failed call');
    else await pause(5000);
  }
  state.phase='completed';state.allPassed=state.passedRounds===rounds;
}catch(error){state.phase='needs-recovery';state.error=error.message;process.exitCode=1;console.error(error.message);}
finally{
  state.finished=true;state.completedAt=new Date().toISOString();state.active=null;
  await command('cmd close').catch(()=>{});
  await adb('shell','am','force-stop','com.youkong.voiceintercom').catch(()=>{});
  if(originalPreferences!==null){
    try{
      await adb('push',path.join(output,'original-app-preferences.xml'),'/data/local/tmp/voice-batch-original.xml');
      await adb('shell','run-as','com.youkong.voiceintercom','cp','/data/local/tmp/voice-batch-original.xml','shared_prefs/intercom.xml');
      state.appPreferencesRestored=true;
    }catch(e){state.appPreferencesRestoreError=e.message;}
  }
  await save();
}
