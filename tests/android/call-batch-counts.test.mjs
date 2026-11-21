import assert from 'node:assert/strict';
import {summarizeAttempts,nextCallDirection} from './call-batch-counts.mjs';

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
console.log('Call counting and replacement policy passed; device failures retained.');
