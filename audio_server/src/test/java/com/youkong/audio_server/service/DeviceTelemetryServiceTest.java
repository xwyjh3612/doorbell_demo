package com.youkong.audio_server.service;
import com.alibaba.fastjson.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

public class DeviceTelemetryServiceTest {
    private JSONObject powerReport(String device) {
        JSONObject p = new JSONObject();
        p.put("schema", 1); p.put("device", device); p.put("uptime_ms", 1000);
        p.put("source", "battery"); p.put("external_present", 1);
        p.put("battery_mv", 3800); p.put("battery_percent", 60); p.put("estimate", true);
        p.put("calibrated", true); p.put("charging", 0); p.put("charge_paused", false);
        return p;
    }
    @Test public void batteryCanSupplyDeviceWhileAdapterIsStillPluggedIn() {
        DeviceTelemetryService s = new DeviceTelemetryService("project");
        s.handleTelemetry("/voice/project/a/power", powerReport("a").toJSONString());
        JSONObject envelope = s.snapshot("a"), p = envelope.getJSONObject("power");
        assertEquals("battery", p.getString("source")); assertEquals(1, p.getIntValue("external_present"));
        assertTrue(envelope.getBooleanValue("power_online")); assertNull(envelope.get("radar"));
    }
    @Test public void powerAndRadarSnapshotsRemainIndependent() {
        DeviceTelemetryService s = new DeviceTelemetryService("project");
        s.handleTelemetry("/voice/project/a/telemetry", report("a").toJSONString());
        s.handleTelemetry("/voice/project/a/power", powerReport("a").toJSONString());
        JSONObject p = powerReport("a"); p.put("battery_percent", 101);
        s.handleTelemetry("/voice/project/a/power", p.toJSONString());
        p = powerReport("a"); p.put("battery_mv", 3800.5);
        s.handleTelemetry("/voice/project/a/power", p.toJSONString());
        s.handleTelemetry("/voice/project/a/power", powerReport("b").toJSONString());
        assertEquals(60, s.snapshot("a").getJSONObject("power").getIntValue("battery_percent"));
        assertEquals(76, s.snapshot("a").getJSONObject("radar").getIntValue("heart"));
    }
    @Test public void uncalibratedADCDoesNotBecomeAValidPercentage() {
        DeviceTelemetryService s = new DeviceTelemetryService("project");
        JSONObject p = powerReport("a"); p.put("calibrated", false); p.put("battery_mv", -1);
        s.handleTelemetry("/voice/project/a/power", p.toJSONString());
        assertNull(s.snapshot("a").get("power"));
        p.put("battery_percent", -1);
        s.handleTelemetry("/voice/project/a/power", p.toJSONString());
        assertEquals(-1, s.snapshot("a").getJSONObject("power").getIntValue("battery_percent"));
        assertEquals("battery", s.snapshot("a").getJSONObject("power").getString("source"));
    }
    private JSONObject report(String device) {
        JSONObject data = new JSONObject();
        data.put("schema", 1); data.put("device", device); data.put("radar", "r60abd1");
        for (String key : new String[]{"uptime_ms", "rx_age_ms", "motion_age_ms", "breath_age_ms",
                "heart_age_ms", "distance_age_ms", "valid_frames", "uart_errors"}) data.put(key, 0);
        for (String key : new String[]{"presence", "activity", "motion", "breath", "heart", "distance_cm", "bed", "sleep_raw"}) data.put(key, -1);
        data.put("breath", 16); data.put("heart", 76); return data;
    }
    @Test public void deviceIdentityAndTopicAreChecked() {
        DeviceTelemetryService service = new DeviceTelemetryService("project");
        service.handleTelemetry("/voice/project/a/telemetry", report("b").toJSONString());
        service.handleTelemetry("/voice/other/a/telemetry", report("a").toJSONString());
        assertFalse(service.snapshot("a").getBooleanValue("online"));
        service.handleTelemetry("/voice/project/a/telemetry", report("a").toJSONString());
        assertTrue(service.snapshot("a").getBooleanValue("online"));
        assertFalse(service.snapshot("b").getBooleanValue("online"));
    }
    @Test public void zeroUnknownAndUnconfirmedSleepRemainDistinct() {
        DeviceTelemetryService service = new DeviceTelemetryService("project");
        JSONObject data = report("a"); data.put("heart", 0); data.put("sleep_raw", 0);
        service.handleTelemetry("/voice/project/a/telemetry", data.toJSONString());
        JSONObject result = service.snapshot("a").getJSONObject("radar");
        assertEquals(0, result.getIntValue("heart")); assertEquals(-1, result.getIntValue("presence"));
        assertEquals(0, result.getIntValue("sleep_raw"));
    }
    @Test public void invalidPayloadDoesNotReplaceGoodSnapshot() {
        DeviceTelemetryService service = new DeviceTelemetryService("project");
        JSONObject data = report("a");
        service.handleTelemetry("/voice/project/a/telemetry", data.toJSONString());
        data.put("heart", 255); service.handleTelemetry("/voice/project/a/telemetry", data.toJSONString());
        service.handleTelemetry("/voice/project/a/telemetry", "{broken");
        assertEquals(76, service.snapshot("a").getJSONObject("radar").getIntValue("heart"));
    }
}
