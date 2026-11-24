package com.youkong.audio_server.service;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;
import org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator;
import org.springframework.web.util.UriComponentsBuilder;
import java.io.IOException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

/** Separate observation channel. It never forwards commands or binds call IDs. */
@Service
public class DeviceTelemetryService extends TextWebSocketHandler {
    private final String prefix;
    private final RadarHistoryStore history;
    private final ConcurrentMap<String, Observation> latest = new ConcurrentHashMap<>();
    private final ConcurrentMap<String, Observation> latestPower = new ConcurrentHashMap<>();
    private final ConcurrentMap<String, Subscription> subscribers = new ConcurrentHashMap<>();
    @Autowired
    public DeviceTelemetryService(@Value("${signaling.project:project}") String project, RadarHistoryStore history) {
        prefix = "/voice/" + project + "/";
        this.history = history;
    }
    public DeviceTelemetryService(String project) { this(project,null); }
    private static final class Observation {
        final JSONObject data; final long at;
        Observation(JSONObject data) { this.data = data; at = System.currentTimeMillis(); }
    }
    private static final class Subscription {
        final String device; final WebSocketSession socket;
        Subscription(String device, WebSocketSession socket) {
            this.device = device; this.socket = new ConcurrentWebSocketSessionDecorator(socket, 1000, 8192);
        }
    }
    public boolean isTelemetryTopic(String topic) {
        return topic != null && topic.startsWith(prefix) && (topic.endsWith("/telemetry") || topic.endsWith("/power"));
    }
    public void handleTelemetry(String topic, String payload) {
        if (!isTelemetryTopic(topic) || payload == null || payload.length() > 2048) return;
        if (topic.endsWith("/power")) { handlePower(topic, payload); return; }
        String device = topic.substring(prefix.length(), topic.length() - "/telemetry".length());
        if (!device.matches("[A-Za-z0-9_-]{1,63}")) return;
        try {
            JSONObject input = JSON.parseObject(payload);
            if (input == null || input.getIntValue("schema") != 1 || !device.equals(input.getString("device"))) return;
            String model = input.getString("radar");
            if (!"r60abd1".equals(model) && !"r24d".equals(model)) return;
            if (!latest.containsKey(device) && latest.size() >= 256) return;
            JSONObject safe = new JSONObject();
            safe.put("schema", 1); safe.put("device", device); safe.put("radar", model);
            for (String key : new String[]{"uptime_ms", "rx_age_ms", "motion_age_ms", "breath_age_ms",
                    "heart_age_ms", "distance_age_ms", "valid_frames", "uart_errors"}) {
                Object value = input.get(key);
                if (!(value instanceof Number) || ((Number)value).longValue() < -1) return;
                safe.put(key, ((Number)value).longValue());
            }
            String[] keys = {"presence", "activity", "motion", "breath", "heart", "distance_cm", "bed", "sleep_raw"};
            int[] max = {1, 2, 100, 35, 120, 65535, 2, 3};
            for (int i = 0; i < keys.length; i++) {
                Object value = input.get(keys[i]);
                if (!(value instanceof Number)) return;
                int n = ((Number)value).intValue();
                if (n < -1 || n > max[i] || ("heart".equals(keys[i]) && n > 0 && n < 60)) return;
                safe.put(keys[i], n);
            }
            Observation observation = new Observation(safe);
            latest.put(device, observation);
            if(history != null) history.record(device, safe, observation.at);
            for (Subscription subscription : subscribers.values()) {
                if (device.equals(subscription.device)) send(subscription);
            }
        } catch (RuntimeException ignored) { /* Malformed telemetry cannot enter call handling. */ }
    }
    private void handlePower(String topic, String payload) {
        String device = topic.substring(prefix.length(), topic.length() - "/power".length());
        if (!device.matches("[A-Za-z0-9_-]{1,63}")) return;
        try {
            JSONObject input = JSON.parseObject(payload);
            if (input == null || input.getIntValue("schema") != 1 || !device.equals(input.getString("device"))) return;
            String source = input.getString("source");
            if (!"external".equals(source) && !"battery".equals(source) && !"unknown".equals(source)) return;
            if (!Boolean.TRUE.equals(input.get("estimate")) || !(input.get("calibrated") instanceof Boolean)
                    || !(input.get("charge_paused") instanceof Boolean)) return;
            JSONObject safe = new JSONObject();
            safe.put("schema", 1); safe.put("device", device); safe.put("source", source);
            safe.put("estimate", true); safe.put("calibrated", input.get("calibrated"));
            safe.put("charge_paused", input.get("charge_paused"));
            String[] keys = {"uptime_ms", "external_present", "battery_mv", "battery_percent", "charging"};
            long[] min = {0, -1, -1, -1, -1}, max = {Long.MAX_VALUE, 1, 4400, 100, 3};
            for (int i = 0; i < keys.length; i++) {
                Object value = input.get(keys[i]);
                if (!(value instanceof Integer) && !(value instanceof Long)) return;
                long n = ((Number)value).longValue();
                if (n < min[i] || n > max[i] || (i == 2 && n != -1 && n < 2500)) return;
                safe.put(keys[i], n);
            }
            if ((!input.getBooleanValue("calibrated") || input.getIntValue("battery_mv") == -1)
                    && input.getIntValue("battery_percent") != -1) return;
            if (!latestPower.containsKey(device) && latestPower.size() >= 256) return;
            latestPower.put(device, new Observation(safe));
            for (Subscription subscription : subscribers.values()) if (device.equals(subscription.device)) send(subscription);
        } catch (RuntimeException ignored) { /* Independent telemetry must never enter call handling. */ }
    }
    public JSONObject snapshot(String device) {
        JSONObject body = new JSONObject();
        body.put("type", "telemetry"); body.put("device", device);
        Observation observation = latest.get(device);
        long age = observation == null ? -1 : Math.max(0, System.currentTimeMillis() - observation.at);
        body.put("age_ms", age); body.put("online", age >= 0 && age < 30000);
        body.put("received_at_ms", observation == null ? 0 : observation.at);
        body.put("radar", observation == null ? null : observation.data);
        Observation power = latestPower.get(device);
        long powerAge = power == null ? -1 : Math.max(0, System.currentTimeMillis() - power.at);
        body.put("power", power == null ? null : power.data);
        body.put("power_age_ms", powerAge);
        body.put("power_received_at_ms", power == null ? 0 : power.at);
        body.put("power_online", powerAge >= 0 && powerAge < 60000);
        return body;
    }
    @Override public void afterConnectionEstablished(WebSocketSession session) throws IOException {
        String device = UriComponentsBuilder.fromUri(session.getUri()).build().getQueryParams().getFirst("device");
        if (device == null || !device.matches("[A-Za-z0-9_-]{1,63}") || subscribers.size() >= 64) {
            session.close(CloseStatus.BAD_DATA); return;
        }
        Subscription subscription = new Subscription(device, session);
        subscribers.put(session.getId(), subscription); send(subscription);
    }
    private void send(Subscription subscription) {
        try {
            if (subscription.socket.isOpen()) subscription.socket.sendMessage(new TextMessage(snapshot(subscription.device).toJSONString()));
        } catch (IOException | RuntimeException error) {
            subscribers.remove(subscription.socket.getId());
            try { subscription.socket.close(); } catch (IOException ignored) { }
        }
    }
    @Override public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        subscribers.remove(session.getId());
    }
}
