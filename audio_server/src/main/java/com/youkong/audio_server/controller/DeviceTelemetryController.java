package com.youkong.audio_server.controller;
import com.alibaba.fastjson.JSONObject;
import com.youkong.audio_server.service.DeviceTelemetryService;
import org.springframework.web.bind.annotation.*;

@RestController
public class DeviceTelemetryController {
    private final DeviceTelemetryService service;
    public DeviceTelemetryController(DeviceTelemetryService service) { this.service = service; }
    @GetMapping("/api/devices/{device}/telemetry")
    public JSONObject telemetry(@PathVariable String device) { return service.snapshot(device); }
}
