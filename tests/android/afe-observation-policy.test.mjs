import assert from 'node:assert/strict';
import {observeAfeAlert,finishAudioObservation} from './afe-observation-policy.mjs';

const clean={afeAlerts:0};
observeAfeAlert(clean);
assert.equal(finishAudioObservation(clean,1800),true);

const recovered={afeAlerts:1};
assert.doesNotThrow(()=>observeAfeAlert(recovered,'observe','2026-11-26T08:00:00Z'));
observeAfeAlert(recovered,'observe','2026-11-26T08:01:00Z');
assert.equal(recovered.afeFailureDetectedAt,'2026-11-26T08:00:00Z');
assert.equal(finishAudioObservation(recovered,1800),false);
assert.equal(recovered.audioObservationCompleted,true);
assert.equal(recovered.observedSeconds,1800);
assert.match(recovered.error,/AFE/);

assert.throws(()=>observeAfeAlert({afeAlerts:1},'fail-fast'),/AFE feed buffer overflow/);
assert.throws(()=>observeAfeAlert({},'invalid'),/Invalid/);
// A real disconnection is still retained if it follows an AFE warning.
const disconnected={afeAlerts:3,error:'Peer failed during observation'};
observeAfeAlert(disconnected);
assert.equal(finishAudioObservation(disconnected,10),false);
assert.equal(disconnected.error,'Peer failed during observation');
console.log('PASS: AFE observation continues without hiding acceptance failures, first warning or disconnection errors');
