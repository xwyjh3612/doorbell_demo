package com.youkong.audio_server.service;
import com.alibaba.fastjson.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

public class DeviceTelemetryServiceTest {
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
