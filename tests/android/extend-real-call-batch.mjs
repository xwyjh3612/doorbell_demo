// Extend an already running cohort without interrupting its current call.
// Each connected failure remains a failed round; setup attempts never count.
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {writeState,readState} from './state-file.mjs';

const args=process.argv.slice(2);
const option=(name,fallback)=>{const i=args.indexOf(name);return i<0?fallback:args[i+1];};
const initial=path.resolve(option('--initial','build/real-call-at-recovery-30'));
const output=path.resolve(option('--output','build/real-call-at-recovery-40'));
const device=option('--real-device','');
const target=Number(option('--rounds','40'));
const read=async dir=>readState(path.join(dir,'state.json'));
const first=await read(initial);
if(!/^\d{12,20}$/.test(device)||!Number.isInteger(target)||target<first.requestedConnectedRounds||target>100){
  throw Error('Invalid device/extension target');
}
if(first.requestedConnectedRounds%2)throw Error('First cohort must have an even target to preserve call directions');
if(first.targetSecondsPerRound!==1800||!first.allowModemRestart)throw Error('Expected half-hour cohort with authorized modem recovery');
if(!args.includes('--resume'))await fs.mkdir(output,{recursive:false});
const extra=path.join(output,'additional-rounds');
const state={startedAt:new Date().toISOString(),originalStartedAt:first.startedAt,
  requestedConnectedRounds:target,targetSecondsPerRound:1800,firmware:first.firmware,
  initialCohort:initial,additionalCohort:extra,additionalRequestedRounds:target-first.requestedConnectedRounds,
  phase:'waiting_for_initial_cohort',finished:false,completedConnectedRounds:0,passedRounds:0,
  failedConnectedRounds:0,attempts:[],recoveries:[],active:null,
  note:target===first.requestedConnectedRounds?'Mirrors the resumed main cohort; no additional call process is started.':
    'Same image and rules; initial running calls retained, then a separate appended cohort. No combined timing or discarded failures.'};
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const save=async()=>{state.updatedAt=new Date().toISOString();await writeState(path.join(output,'state.json'),state);};
let nextProgress=0,child,childDone=false,childCode=null,stdout,stderr;
function aggregate(a,b){
  if(b&&a.firmware.sha256!==b.firmware.sha256)throw Error('Firmware changed between cohorts');
  state.completedConnectedRounds=a.completedConnectedRounds+(b?.completedConnectedRounds||0);
  state.passedRounds=a.passedRounds+(b?.passedRounds||0);
  state.failedConnectedRounds=state.completedConnectedRounds-state.passedRounds;
  state.attempts=[...a.attempts.map(v=>({...v,cohort:'initial'})),
    ...(b?.attempts||[]).map(v=>({...v,cohort:'additional',round:v.round===null?null:v.round+a.completedConnectedRounds}))];
  state.recoveries=[...a.recoveries.map(v=>({...v,cohort:'initial'})),...(b?.recoveries||[]).map(v=>({...v,cohort:'additional'}))];
  state.active=b?.active?{...b.active,round:b.active.round+a.completedConnectedRounds,cohort:'additional'}:
    a.active?{...a.active,cohort:'initial'}:null;
}
try{
  await save();
  while(true){
    const a=await read(initial);
    let b=null;
    try{b=await read(extra);}catch{}
    aggregate(a,b);
    if(!a.finished)state.phase='initial_cohort_running';
    else if(a.phase!=='completed'||a.completedConnectedRounds!==a.requestedConnectedRounds){
      state.phase='needs-recovery';state.error=a.error||'Initial cohort stopped before its target';break;
    }else if(state.additionalRequestedRounds===0){state.phase='completed';break;
    }else if(!child){
      const currentImage=JSON.parse(await fs.readFile('outputs/firmware/voice-radar60.json','utf8'));
      if(currentImage.sha256!==first.firmware.sha256)throw Error('Current image differs from initial cohort');
      stdout=await fs.open(path.join(output,'additional-runner.stdout.log'),'w');
      stderr=await fs.open(path.join(output,'additional-runner.stderr.log'),'w');
      child=spawn(process.execPath,['tests/android/run-real-call-batch.mjs','--real-device',device,
        '--rounds',String(state.additionalRequestedRounds),'--hold-seconds','1800','--allow-modem-restart',
        '--app-id',a.localAppId,'--output',extra],{cwd:process.cwd(),windowsHide:true,
        stdio:['ignore',stdout.fd,stderr.fd],env:{...process.env}});
      child.on('error',e=>{state.error=e.message;childDone=true;});
      child.on('exit',code=>{childCode=code;childDone=true;});
      state.phase='starting_additional_cohort';
      console.log(`Initial ${a.completedConnectedRounds} rounds retained; starting ${state.additionalRequestedRounds} additional rounds`);
    }else state.phase='additional_cohort_running';
    if(childDone){
      b=await read(extra).catch(()=>null);aggregate(a,b);
      state.phase=b?.phase==='completed'&&state.completedConnectedRounds===target?'completed':'needs-recovery';
      state.error=b?.error||state.error||(childCode!==0?'Additional runner stopped':null);break;
    }
    await save();
    if(Date.now()>=nextProgress){
      console.log(`Target ${target}: ${state.completedConnectedRounds} completed, ${state.passedRounds} passed, ${state.failedConnectedRounds} failed; active=${state.active?.round||'none'}`);
      nextProgress=Date.now()+300000;
    }
    await pause(5000);
  }
}catch(error){state.phase='needs-recovery';state.error=error.message;process.exitCode=1;}
finally{
  await stdout?.close();await stderr?.close();
  state.finished=true;state.completedAt=new Date().toISOString();
  state.allPassed=state.phase==='completed'&&state.passedRounds===target;
  await save();
  if(state.phase!=='completed')process.exitCode=1;
}
