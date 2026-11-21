// A computer/supervisor interruption is retained as evidence and replaced by
// another independent call. Connected device/media failures still count.
export function summarizeAttempts(attempts, {excludeSupervisorInterruptions=true}={}) {
  let completedConnectedRounds=0, passedRounds=0, rawCompletedConnectedRounds=0;
  const excludedAttempts=[];
  const annotated=attempts.map(attempt=>{
    const connected=!!attempt.connectedAt;
    if(connected)++rawCompletedConnectedRounds;
    const excluded=connected&&excludeSupervisorInterruptions&&
      attempt.failureClassification==='test-supervisor-interruption';
    if(excluded)excludedAttempts.push({...attempt,exclusionReason:'computer-test-supervisor-interruption'});
    if(connected&&!excluded){++completedConnectedRounds;if(attempt.passed)++passedRounds;}
    return {...attempt,countedRound:connected&&!excluded?completedConnectedRounds:null,
      excludedFromRequestedRounds:excluded};
  });
  return {completedConnectedRounds,passedRounds,failedConnectedRounds:completedConnectedRounds-passedRounds,
    rawCompletedConnectedRounds,excludedConnectedRounds:excludedAttempts.length,excludedAttempts,attempts:annotated};
}

export function nextCallDirection(attempts, startDirection='app-calls-device') {
  const last=attempts.findLast(attempt=>attempt.connectedAt);
  return last?(last.direction==='app-calls-device'?'device-calls-app':'app-calls-device'):startDirection;
}
