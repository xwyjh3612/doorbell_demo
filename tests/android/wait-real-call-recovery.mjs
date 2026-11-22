// Resume the existing real-call cohort only after fresh modem/signaling
// recovery evidence. Never flash, toggle unknown GPIOs, or hide failed rounds.
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {readState,writeState} from './state-file.mjs';
const args=process.argv.slice(2);
const opt=(name,fallback)=>{const i=args.indexOf(name);return i<0?fallback:args[i+1];};
const device=opt('--real-device','');
if(!/^\d{12,20}$/.test(device))throw Error('Explicit real device required');
const initial=path.resolve(opt('--initial','build/real-call-at-recovery-30'));
const output=path.resolve(opt('--output','build/real-call-at-recovery-40'));
const bridge=process.env.VOICE_TEST_CONSOLE||'http://127.0.0.1:18889';
const file=path.join(output,'recovery-watcher.json');
const lines=async()=>{const r=await fetch(bridge,{signal:AbortSignal.timeout(5000)});if(!r.ok)throw Error('Console unavailable');return(await r.json()).lines;};
const pause=ms=>new Promise(r=>setTimeout(r,ms));
let anchor=(await lines()).at(-1)||'';
let nextProgress=0;
// One-time operator option after a separately recorded, verified ESP reset.
// A fresh successful radar publish proves MQTT connectivity and CALL_STATE_IDLE
// in the current firmware. Subscription/call behavior is then tested normally.
let allowIdleTelemetryProof=args.includes('--allow-idle-telemetry-proof-after-esp-reset');
async function start(script,values,label){
  const out=await fs.open(path.join(output,`recovery-${label}.stdout.log`),'a');
  const err=await fs.open(path.join(output,`recovery-${label}.stderr.log`),'a');
  const child=spawn(process.execPath,[script,...values],{cwd:process.cwd(),windowsHide:true,
    stdio:['ignore',out.fd,err.fd],env:{...process.env}});
  const completed=new Promise(resolve=>{
    child.on('error',error=>resolve({error:error.message}));
    child.on('exit',code=>resolve({code}));
  });
  completed.finally(()=>{out.close();err.close();});
  return {pid:child.pid,completed};
}
while(true){
  const full=await readState(path.join(output,'state.json'));
  if(full.phase==='completed'&&full.completedConnectedRounds>=40){
    await writeState(file,{phase:'completed',at:new Date().toISOString(),completed:full.completedConnectedRounds});break;
  }
  let recent=[];
  try{recent=(await lines()).filter(l=>l>anchor);}catch(error){console.error(error.message);}
  // An old MATREADY or an old connected call cannot authorize resumption.
  const freshSubscription=recent.some(l=>/MQTT signaling restarted, subscribed|MQTT signaling started, subscribed/.test(l));
  const freshIdleAfterVerifiedReset=allowIdleTelemetryProof&&recent.some(l=>/RADAR_TELEMETRY: published model=/.test(l));
  if(freshSubscription||freshIdleAfterVerifiedReset){
    const cohort=await readState(path.join(initial,'state.json'));
    if(!cohort.finished)throw Error('Another cohort runner is active');
    if(cohort.phase==='completed')throw Error('Initial completed: use extension supervisor directly');
    await writeState(file,{phase:'resuming_after_observed_recovery',at:new Date().toISOString(),proof:freshSubscription?'fresh-subscription':'fresh-idle-mqtt-publish-after-verified-esp-reset',evidence:recent.filter(l=>/MATREADY|MQTT signaling .*subscribed|RADAR_TELEMETRY: published model=/.test(l)),previousError:cohort.error});
    allowIdleTelemetryProof=false;
    const base=await start('tests/android/run-real-call-batch.mjs',['--real-device',device,'--rounds','40','--hold-seconds','1800','--allow-modem-restart','--resume','--output',initial],'initial');
    let started=false;
    for(let n=0;n<15;++n){await pause(1000);const s=await readState(path.join(initial,'state.json'));if(!s.finished){started=true;break;}}
    if(!started){await base.completed;throw Error('Cohort did not resume');}
    const extension=await start('tests/android/extend-real-call-batch.mjs',['--real-device',device,'--rounds','40','--resume','--initial',initial,'--output',output],'aggregate');
    console.log('Resumed real calls after signaling recovery; runner PID',base.pid,'aggregate PID',extension.pid);
    await Promise.all([base.completed,extension.completed]);
    anchor=(await lines()).at(-1)||anchor;
    nextProgress=0;
  }else{
    if(Date.now()>=nextProgress){
      const status={phase:'waiting_for_fresh_modem_signaling',at:new Date().toISOString(),anchor,
        completed:full.completedConnectedRounds,passed:full.passedRounds,failed:full.failedConnectedRounds,
        note:'AT recovery exhausted; current board has no verified hardware reset line. Await external power recovery. No test call is running.'};
      await writeState(file,status);console.log(status.note);nextProgress=Date.now()+300000;
    }
    await pause(15000);
  }
}
