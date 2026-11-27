// Explicitly classified test infrastructure interruptions retain their evidence
// and are replaced by another call. Connected device/media failures still count.
export function summarizeAttempts(attempts, {
  excludeSupervisorInterruptions=true, excludeServerInterruptions=true
}={}) {
  let completedConnectedRounds=0, passedRounds=0, rawCompletedConnectedRounds=0;
  const excludedAttempts=[];
  const annotated=attempts.map(attempt=>{
    const connected=!!attempt.connectedAt;
    if(connected)++rawCompletedConnectedRounds;
    const supervisorInterruption=excludeSupervisorInterruptions&&
      attempt.failureClassification==='test-supervisor-interruption';
    const serverInterruption=excludeServerInterruptions&&
      attempt.failureClassification==='test-server-interruption';
    const firmwareTransition=attempt.failureClassification==='test-firmware-transition';
    const userPowerInterruption=attempt.failureClassification==='test-user-power-interruption';
    const excluded=connected&&(supervisorInterruption||serverInterruption||firmwareTransition||userPowerInterruption);
    if(excluded)excludedAttempts.push({...attempt,exclusionReason:firmwareTransition?
      'planned-firmware-transition':userPowerInterruption?'user-reported-power-interruption':serverInterruption?
      'server-test-infrastructure-interruption':'computer-test-supervisor-interruption'});
    if(connected&&!excluded){++completedConnectedRounds;if(attempt.passed)++passedRounds;}
    return {...attempt,countedRound:connected&&!excluded?completedConnectedRounds:null,
      excludedFromRequestedRounds:excluded};
  });
  return {completedConnectedRounds,passedRounds,failedConnectedRounds:completedConnectedRounds-passedRounds,
    rawCompletedConnectedRounds,excludedConnectedRounds:excludedAttempts.length,excludedAttempts,attempts:annotated};
}

// Operator annotations are separate from immutable call evidence. Match both
// attempt number and connection timestamp so annotations cannot affect a
// different call after copying or resuming a batch.
export function applyAttemptAnnotations(attempts, annotations={}) {
  const entries=Array.isArray(annotations.attempts)?annotations.attempts:[];
  return attempts.map(attempt=>{
    const annotation=entries.find(entry=>Number.isInteger(entry.attempt)&&
      entry.attempt===attempt.attempt&&entry.connectedAt===attempt.connectedAt&&
      entry.failureClassification==='test-user-power-interruption'&&
      entry.classificationEvidence?.source==='user-report');
    return annotation?{...attempt,failureClassification:annotation.failureClassification,
      classificationEvidence:annotation.classificationEvidence}:attempt;
  });
}

export function nextCallDirection(attempts, startDirection='app-calls-device') {
  const last=attempts.findLast(attempt=>attempt.connectedAt);
  return last?(last.direction==='app-calls-device'?'device-calls-app':'app-calls-device'):startDirection;
}
