import assert from 'node:assert/strict';
import {summarizeAttempts,nextCallDirection,applyAttemptAnnotations} from './call-batch-counts.mjs';

const attempts=[
  {attempt:1,connectedAt:null,passed:false,direction:'app-calls-device'},
  {attempt:2,connectedAt:'2026-11-21T16:11:45',passed:false,direction:'app-calls-device',failureClassification:'test-supervisor-interruption'},
  {attempt:3,connectedAt:'2026-11-21T16:43:32',passed:true,direction:'device-calls-app'},
  {attempt:4,connectedAt:'2026-11-21T17:13:54',passed:false,direction:'app-calls-device',error:'network/media failure'},
];
const counts=summarizeAttempts(attempts);
assert.equal(counts.completedConnectedRounds,2);
assert.equal(counts.passedRounds,1);
assert.equal(counts.failedConnectedRounds,1);
assert.equal(counts.rawCompletedConnectedRounds,3);
assert.equal(counts.excludedConnectedRounds,1);
assert.equal(counts.excludedAttempts[0].attempt,2);
assert.deepEqual(counts.attempts.map(a=>a.countedRound),[null,null,1,2]);
assert.equal(nextCallDirection(attempts),'device-calls-app');
assert.equal(nextCallDirection(attempts.slice(0,2)),'device-calls-app');
assert.equal(nextCallDirection([], 'device-calls-app'),'device-calls-app');
assert.equal(summarizeAttempts(attempts,{excludeSupervisorInterruptions:false}).failedConnectedRounds,2);
assert.deepEqual(attempts.map(a=>a.countedRound),[undefined,undefined,undefined,undefined]);
const initial=summarizeAttempts(Array.from({length:40},(_,i)=>({attempt:i+1,connectedAt:'time',passed:i!==0,
  failureClassification:i===0?'test-supervisor-interruption':undefined})));
assert.equal(initial.completedConnectedRounds,39);
assert.equal(40-initial.completedConnectedRounds,1);
assert.equal(summarizeAttempts([...initial.attempts,{connectedAt:'time',passed:true}]).completedConnectedRounds,40);
const serverAttempts=[
  {attempt:1,connectedAt:'2026-11-25T18:55:47',passed:true},
  {attempt:2,connectedAt:'2026-11-25T19:26:13',passed:false,
    failureClassification:'test-server-interruption',
    classificationEvidence:{source:'user-report',outageStartedApproximately:'2026-11-25T19:37:00+08:00'}},
  {attempt:3,connectedAt:null,passed:false,error:'Expected device event missing'},
  {attempt:4,connectedAt:'2026-11-25T21:30:00',passed:false,error:'AFE feed buffer overflow'},
];
const serverCounts=summarizeAttempts(serverAttempts);
assert.equal(serverCounts.completedConnectedRounds,2);
assert.equal(serverCounts.passedRounds,1);
assert.equal(serverCounts.failedConnectedRounds,1);
assert.equal(serverCounts.rawCompletedConnectedRounds,3);
assert.equal(serverCounts.excludedConnectedRounds,1);
assert.equal(serverCounts.excludedAttempts[0].attempt,2);
assert.equal(serverCounts.excludedAttempts[0].exclusionReason,'server-test-infrastructure-interruption');
assert.equal(serverCounts.excludedAttempts[0].passed,false);
assert.deepEqual(serverCounts.attempts.map(a=>a.countedRound),[1,null,null,2]);
assert.equal(summarizeAttempts(serverAttempts,{excludeServerInterruptions:false}).failedConnectedRounds,2);
assert.equal(summarizeAttempts(serverAttempts.slice(0,3)).failedConnectedRounds,0);
assert.equal(summarizeAttempts([...serverAttempts.slice(0,3),{connectedAt:'time',passed:true}]).completedConnectedRounds,2);
const switched=summarizeAttempts([...serverAttempts,{attempt:5,connectedAt:'time',passed:false,
  failureClassification:'test-firmware-transition'}]);
assert.equal(switched.completedConnectedRounds,2);
assert.equal(switched.failedConnectedRounds,1);
assert.equal(switched.excludedAttempts.at(-1).exclusionReason,'planned-firmware-transition');
const powerFailure={attempt:1,connectedAt:'2026-11-26T17:11:16.776701',passed:false,
  error:'Bidirectional audio stopped for over 12 seconds'};
const annotation={attempt:1,connectedAt:powerFailure.connectedAt,failureClassification:'test-user-power-interruption',
  classificationEvidence:{source:'user-report',action:'UPS unplugged',causalLinkConfirmed:false}};
const annotated=applyAttemptAnnotations([powerFailure],{attempts:[annotation]});
const powerCounts=summarizeAttempts(annotated);
assert.equal(powerCounts.completedConnectedRounds,0);
assert.equal(powerCounts.failedConnectedRounds,0);
assert.equal(powerCounts.excludedConnectedRounds,1);
assert.equal(powerCounts.excludedAttempts[0].exclusionReason,'user-reported-power-interruption');
assert.equal(powerCounts.excludedAttempts[0].error,powerFailure.error);
assert.equal(powerFailure.failureClassification,undefined);
assert.equal(summarizeAttempts(applyAttemptAnnotations([powerFailure],{attempts:[{...annotation,connectedAt:'other call'}]})).failedConnectedRounds,1);
assert.equal(summarizeAttempts([...annotated,{attempt:2,connectedAt:'next call',passed:true}]).completedConnectedRounds,1);
console.log('Call counting passed; planned firmware transitions and infrastructure interruptions excluded, device failures retained.');
