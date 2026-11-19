package com.youkong.voiceintercom;
import org.junit.Test;
import static org.junit.Assert.*;
public class TelemetryStateTest {
    @Test public void serverConnectionDoesNotMeanDeviceOnline(){TelemetryState s=new TelemetryState();s.socketOpen=true;assertFalse(s.online(100));}
    @Test public void valuesExpireEvenWithConnectedSocket(){TelemetryState s=new TelemetryState();s.socketOpen=true;s.receivedMono=100;s.serverAge=0;s.rxAge=0;s.breathAge=0;assertTrue(s.fresh(s.breathAge,1100));assertFalse(s.fresh(s.breathAge,13100));assertFalse(s.online(30100));}
    @Test public void cachedSnapshotAgeIsIncluded(){TelemetryState s=new TelemetryState();s.socketOpen=true;s.receivedMono=100;s.serverAge=11000;s.rxAge=0;s.heartAge=3000;assertTrue(s.radarLive(100));assertFalse(s.fresh(s.heartAge,100));}
    @Test public void disconnectionAndUnknownAgesStayUnknown(){TelemetryState s=new TelemetryState();s.receivedMono=100;s.serverAge=0;s.rxAge=0;assertFalse(s.online(100));s.socketOpen=true;assertFalse(s.fresh(-1,100));assertFalse(s.vitals());s.model="r60abd1";assertTrue(s.vitals());}
}
