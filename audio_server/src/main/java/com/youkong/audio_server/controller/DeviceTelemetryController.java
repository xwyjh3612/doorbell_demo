package com.youkong.audio_server.controller;
import com.alibaba.fastjson.JSONObject;
import com.youkong.audio_server.service.DeviceTelemetryService;
import com.youkong.audio_server.service.RadarHistoryStore;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import java.io.IOException;
import org.springframework.web.bind.annotation.*;

@RestController
public class DeviceTelemetryController {
    private final DeviceTelemetryService service;
    private final RadarHistoryStore history;
    public DeviceTelemetryController(DeviceTelemetryService service, RadarHistoryStore history) { this.service = service; this.history = history; }
    @GetMapping("/api/devices/{device}/telemetry")
    public JSONObject telemetry(@PathVariable String device) { return service.snapshot(device); }
    @GetMapping("/api/devices/{device}/radar-history")
    public JSONObject history(@PathVariable String device, @RequestParam("from_ms") long from,
                              @RequestParam("to_ms") long to) {
        try { return history.query(device,from,to); }
        catch(IllegalArgumentException error) {throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"历史范围限一天");}
        catch(IOException error) {throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"历史记录暂不可读");}
    }
}
