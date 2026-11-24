package com.youkong.voiceintercom;
import org.junit.Test;
import static org.junit.Assert.*;
public class TelemetryStateTest {
    @Test public void batteryStatusWorksWithoutRadarAndExpiresDuringLongCall(){
        TelemetryState s=new TelemetryState();s.socketOpen=true;s.powerAge=0;s.powerReceivedMono=100;
        s.powerSource="battery";s.batteryMv=3800;s.batteryPercent=60;
        assertTrue(s.powerLive(100));assertFalse(s.online(100));
        assertTrue(s.powerLabel(100,false).contains("电池供电"));
        assertTrue(s.powerLabel(100,false).contains("约 60%"));
        assertFalse(s.powerLive(60100));assertTrue(s.powerLabel(60100,true).contains("缓存"));
    }
    @Test public void unknownAndEmptyBatteryAreDistinct(){
        TelemetryState s=new TelemetryState();assertEquals("电源状态待上报",s.powerLabel(0,false));
        s.powerAge=0;assertTrue(s.powerLabel(0,false).contains("电量未知"));
        s.batteryPercent=0;assertTrue(s.powerLabel(0,false).contains("约 0%"));
    }
    @Test public void occupancyAndActivityRemainDistinct(){TelemetryState s=new TelemetryState();s.socketOpen=true;s.receivedMono=100;s.serverAge=0;s.rxAge=0;s.presence=1;s.activity=2;assertEquals("moving",s.targetState(100));s.activity=1;assertEquals("still",s.targetState(100));s.presence=0;assertEquals("absent",s.targetState(100));s.presence=-1;s.activity=0;assertEquals("unknown",s.targetState(100));s.presence=1;assertEquals("present",s.targetState(100));assertEquals("unknown",s.targetState(12100));}
    @Test public void serverConnectionDoesNotMeanDeviceOnline(){TelemetryState s=new TelemetryState();s.socketOpen=true;assertFalse(s.online(100));}
    @Test public void valuesExpireEvenWithConnectedSocket(){TelemetryState s=new TelemetryState();s.socketOpen=true;s.receivedMono=100;s.serverAge=0;s.rxAge=0;s.breathAge=0;assertTrue(s.fresh(s.breathAge,1100));assertFalse(s.fresh(s.breathAge,13100));assertFalse(s.online(30100));}
    @Test public void cachedSnapshotAgeIsIncluded(){TelemetryState s=new TelemetryState();s.socketOpen=true;s.receivedMono=100;s.serverAge=11000;s.rxAge=0;s.heartAge=3000;assertTrue(s.radarLive(100));assertFalse(s.fresh(s.heartAge,100));}
    @Test public void disconnectionAndUnknownAgesStayUnknown(){TelemetryState s=new TelemetryState();s.receivedMono=100;s.serverAge=0;s.rxAge=0;assertFalse(s.online(100));s.socketOpen=true;assertFalse(s.fresh(-1,100));assertFalse(s.vitals());s.model="r60abd1";assertTrue(s.vitals());}
}
