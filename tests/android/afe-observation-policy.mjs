// A warning is still an acceptance failure. Continued observation establishes
// whether media recovers or the device actually disconnects; it is not a pass.
export function observeAfeAlert(result, policy='observe', detectedAt=new Date().toISOString()) {
  if (!['observe','fail-fast'].includes(policy)) throw Error('Invalid AFE observation policy');
  if (!result.afeAlerts) return;
  result.afeAcceptanceFailed = true;
  result.afeFailureDetectedAt ||= detectedAt;
  if (policy === 'fail-fast') throw Error('AFE feed buffer overflow during connected call');
}

export function finishAudioObservation(result, seconds) {
  result.audioObservationCompleted = true;
  result.observedSeconds = seconds;
  result.passed = !result.afeAlerts;
  if (!result.passed) {
    result.error ||= 'AFE feed buffer overflow during connected call; audio observation continued to target duration';
  }
  return result.passed;
}
