package com.youkong.voiceintercom;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.net.URI;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import okhttp3.*;

public final class MainActivity extends Activity implements AudioPeer.Listener {
    private static final int INK = Color.rgb(23, 62, 54);
    private static final int GREEN = Color.rgb(213, 241, 173);
    private final Handler main = new Handler(Looper.getMainLooper());
    private final CallState call = new CallState();
    private final List<String> earlyCandidates = new ArrayList<>();
    private final OkHttpClient client = new OkHttpClient.Builder().pingInterval(20, TimeUnit.SECONDS).build();
    private SharedPreferences preferences;
    private AudioPeer media;
    private AudioManager audio;
    private AudioFocusRequest focusRequest;
    private WebSocket socket;
    private JSONArray iceServers;
    private String server, device, localId;
    private String message = "准备连接服务";
    private String transport = "连接中";
    private boolean visible, registered, muted, speaker = true, negotiating;
    private int oldAudioMode;
    private boolean oldSpeaker;
    private boolean audioAcquired;
    private int pendingPermissionAction;
    private long connectedAt;
    private Ringtone ringtone;
    private TextView connectionLabel, statusLabel, subtitleLabel, deviceLabel, durationLabel, diagnostics;
    private Button callButton, answerButton, rejectButton, hangupButton, muteButton, speakerButton, settingsButton;
    private final StringBuilder history = new StringBuilder();
    private final Runnable reconnect = this::connect;
    private final Runnable timeout = () -> end("对方未接听或连接超时", true);
    private final Runnable disconnectedTimeout = () -> end("音频连接已断开", true);
    private final Runnable clock = new Runnable() {
        public void run() {
            if (!visible) return;
            if (call.phase == CallState.Phase.CONNECTED) {
                long seconds = (System.currentTimeMillis() - connectedAt) / 1000;
                durationLabel.setText(String.format(java.util.Locale.ROOT, "%02d:%02d", seconds / 60, seconds % 60));
            }
            main.postDelayed(this, 1000);
        }
    };

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        preferences = getSharedPreferences("intercom", MODE_PRIVATE);
        server = preferences.getString("server", "https://voice.2811.top");
        device = preferences.getString("device", "189833342344184");
        localId = preferences.getString("local", "web_client_001");
        audio = (AudioManager) getSystemService(AUDIO_SERVICE);
        setVolumeControlStream(AudioManager.STREAM_VOICE_CALL);
        buildUi();
    }

    @Override public void onStart() {
        super.onStart(); visible = true; connect(); main.post(clock);
    }
    @Override public void onStop() {
        visible = false;
        main.removeCallbacks(reconnect); main.removeCallbacks(clock);
        if (call.phase != CallState.Phase.IDLE) end("已离开通话页面", true);
        disconnect();
        super.onStop();
    }
    @Override public void onDestroy() {
        main.removeCallbacksAndMessages(null);
        if (media != null) media.dispose();
        client.dispatcher().executorService().shutdown();
        super.onDestroy();
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(color);
        return view;
    }
    private GradientDrawable background(int color, int radius) {
        GradientDrawable drawable = new GradientDrawable(); drawable.setColor(color); drawable.setCornerRadius(dp(radius));
        return drawable;
    }
    private Button button(String label, int color, int textColor, Runnable action) {
        Button button = new Button(this); button.setText(label); button.setTextSize(16); button.setTextColor(textColor);
        button.setAllCaps(false); button.setBackground(background(color, 16));
        LinearLayout.LayoutParams layout = new LinearLayout.LayoutParams(-1, dp(54)); layout.topMargin = dp(10);
        button.setLayoutParams(layout); button.setOnClickListener(v -> action.run()); return button;
    }
    private void buildUi() {
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true); scroll.setBackgroundColor(Color.rgb(245, 247, 240));
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        // Safe padding also keeps this demo clear of Android 15's edge-to-edge system bars.
        root.setPadding(dp(24), dp(36), dp(24), dp(32)); scroll.addView(root); setContentView(scroll);
        TextView eyebrow = text("VOICE / 语音对讲", 13, INK); eyebrow.setLetterSpacing(0.12f); root.addView(eyebrow);
        TextView title = text("让声音，\n即时抵达。", 32, INK); title.setTypeface(null, Typeface.BOLD);
        title.setPadding(0, dp(20), 0, dp(20)); root.addView(title);
        connectionLabel = text("● 连接中", 14, INK); root.addView(connectionLabel);

        LinearLayout card = new LinearLayout(this); card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(22), dp(24), dp(22), dp(24)); card.setBackground(background(INK, 24));
        LinearLayout.LayoutParams cardLayout = new LinearLayout.LayoutParams(-1, -2); cardLayout.topMargin = dp(24);
        root.addView(card, cardLayout);
        TextView cardTitle = text("ESP32 · 4G 语音终端", 14, GREEN); card.addView(cardTitle);
        deviceLabel = text(device, 15, Color.WHITE); deviceLabel.setPadding(0, dp(8), 0, dp(22)); card.addView(deviceLabel);
        statusLabel = text("待机", 30, Color.WHITE); statusLabel.setTypeface(null, Typeface.BOLD); card.addView(statusLabel);
        subtitleLabel = text(message, 14, Color.rgb(202, 218, 208)); subtitleLabel.setPadding(0, dp(10), 0, dp(8)); card.addView(subtitleLabel);
        durationLabel = text("— — : — —", 27, GREEN); card.addView(durationLabel);

        callButton = button("呼叫设备", GREEN, INK, () -> microphone(1)); root.addView(callButton);
        answerButton = button("接听来电", GREEN, INK, () -> microphone(2)); root.addView(answerButton);
        rejectButton = button("拒接", Color.rgb(250, 222, 215), Color.rgb(136, 49, 39), () -> end("已拒接", true)); root.addView(rejectButton);
        hangupButton = button("挂断通话", Color.rgb(250, 222, 215), Color.rgb(136, 49, 39), () -> end("通话已结束", true)); root.addView(hangupButton);
        LinearLayout controls = new LinearLayout(this); root.addView(controls);
        muteButton = button("麦克风开", Color.WHITE, INK, () -> {
            muted = !muted; if (media != null) media.mute(muted); render();
        });
        speakerButton = button("扬声器", Color.WHITE, INK, () -> { speaker = !speaker; routeAudio(); render(); });
        LinearLayout.LayoutParams half = new LinearLayout.LayoutParams(0, dp(52), 1); half.topMargin = dp(10); half.rightMargin = dp(6);
        controls.addView(muteButton, half);
        LinearLayout.LayoutParams half2 = new LinearLayout.LayoutParams(0, dp(52), 1); half2.topMargin = dp(10); half2.leftMargin = dp(6);
        controls.addView(speakerButton, half2);
        TextView note = text("演示时请保持本页打开。呼叫后需在设备端接听；服务已连接不代表设备已在线。", 13, Color.rgb(101, 120, 108));
        note.setPadding(0, dp(18), 0, dp(6)); root.addView(note);
        settingsButton = button("连接设置", Color.WHITE, INK, this::settings); root.addView(settingsButton);
        diagnostics = text("", 12, Color.rgb(101, 120, 108)); diagnostics.setPadding(0, dp(20), 0, 0); diagnostics.setTextIsSelectable(true); root.addView(diagnostics);
        render();
    }

    private void render() {
        connectionLabel.setText("● " + transport + " · " + URI.create(server).getHost());
        deviceLabel.setText(device);
        String status;
        switch (call.phase) {
            case INCOMING: status = "设备来电"; break;
            case DIALING: status = "正在呼叫"; break;
            case CONNECTING: status = "正在接通"; break;
            case CONNECTED: status = "通话中"; break;
            default: status = "待机";
        }
        statusLabel.setText(status); subtitleLabel.setText(message);
        if (call.phase != CallState.Phase.CONNECTED) durationLabel.setText("— — : — —");
        boolean idle = call.phase == CallState.Phase.IDLE;
        boolean incoming = call.phase == CallState.Phase.INCOMING;
        callButton.setVisibility(idle ? View.VISIBLE : View.GONE);
        callButton.setEnabled(registered && iceServers != null);
        callButton.setAlpha(callButton.isEnabled() ? 1f : 0.45f);
        answerButton.setVisibility(incoming ? View.VISIBLE : View.GONE);
        rejectButton.setVisibility(incoming ? View.VISIBLE : View.GONE);
        hangupButton.setVisibility(!idle && !incoming ? View.VISIBLE : View.GONE);
        muteButton.setEnabled(!idle && !incoming); speakerButton.setEnabled(!idle && !incoming);
        muteButton.setText(muted ? "麦克风关" : "麦克风开"); speakerButton.setText(speaker ? "扬声器" : "听筒");
        settingsButton.setEnabled(idle); diagnostics.setText(history.toString());
    }
    private void log(String value) {
        history.append(new java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.ROOT).format(new java.util.Date())).append("  ").append(value).append('\n');
        if (history.length() > 1800) history.delete(0, history.indexOf("\n", 500) + 1);
    }

    private void connect() {
        if (!visible || socket != null) return;
        registered = false; iceServers = null; transport = "连接中"; render();
        String url = server.replaceFirst("^https://", "wss://") + "/signaling";
        socket = client.newWebSocket(new Request.Builder().url(url).build(), new WebSocketListener() {
            @Override public void onOpen(WebSocket ws, Response response) { main.post(() -> {
                if (socket != ws || !visible) return;
                log("安全信令已连接"); send("register", null, null, null); send("ice_request", null, null, null);
            }); }
            @Override public void onMessage(WebSocket ws, String value) { main.post(() -> {
                if (socket != ws || !visible) return;
                try { receive(new JSONObject(value)); } catch (Exception error) { log("信令处理失败：" + error.getMessage()); render(); }
            }); }
            @Override public void onFailure(WebSocket ws, Throwable error, Response response) { main.post(() -> {
                if (socket == ws) log("连接失败：" + error.getClass().getSimpleName());
                lost(ws);
            }); }
            @Override public void onClosed(WebSocket ws, int code, String reason) { main.post(() -> lost(ws)); }
        });
    }
    private void lost(WebSocket ws) {
        if (socket != ws) return;
        socket = null; registered = false; iceServers = null;
        if (call.phase != CallState.Phase.IDLE) end("服务连接中断，请重新呼叫", false);
        transport = "重连中"; log("信令断开，3秒后重连"); render();
        if (visible) { main.removeCallbacks(reconnect); main.postDelayed(reconnect, 3000); }
    }
    private void disconnect() {
        WebSocket previous = socket; socket = null; registered = false; iceServers = null;
        if (previous != null) previous.close(1000, "demo page closed");
    }
    private boolean send(String type, String target, String field, String value) {
        if (socket == null) return false;
        try {
            JSONObject json = new JSONObject().put("type", type).put("from", localId)
                    .put("timestamp", System.currentTimeMillis() / 1000);
            if (target != null) json.put("target", target);
            if (field != null) json.put(field, value);
            return socket.send(json.toString());
        } catch (Exception error) { return false; }
    }

    private void receive(JSONObject json) throws Exception {
        String type = json.optString("type"), from = json.optString("from");
        if ("connected".equals(type)) return;
        if ("register_response".equals(type)) {
            registered = true; transport = "服务已连接"; message = "可以呼叫，或等待设备来电"; log("客户端注册成功"); render(); return;
        }
        if ("ice_response".equals(type)) {
            JSONArray servers = json.optJSONArray("iceServers");
            if (servers != null && servers.length() > 0) { iceServers = servers; log("音频中继配置已就绪"); }
            else { message = "中继配置为空，请检查服务器"; }
            render(); return;
        }
        if ("error".equals(type)) { message = json.optString("data", "服务器错误"); log(message); render(); return; }
        if (!device.equals(from)) return;
        log("设备信令：" + type);
        String data = json.optString("data", json.optString("sdp"));
        if ("ring".equals(type) || ("customized".equals(type) && "RING".equals(data))) {
            if (call.incoming(from, null)) incomingUi();
        } else if ("offer".equals(type)) {
            if (call.incoming(from, data)) {
                if (call.accepted) answerOffer(); else incomingUi();
            }
        } else if ("answer".equals(type) && call.matches(from) && call.phase == CallState.Phase.DIALING) {
            call.phase = CallState.Phase.CONNECTING; message = "对方已接听，建立音频连接"; media.remote(data, false);
        } else if ("candidate".equals(type) && call.matches(from)) {
            String candidate = json.optString("candidate", data);
            if (negotiating) media.candidate(candidate);
            else if (earlyCandidates.size() < 128) earlyCandidates.add(candidate);
        } else if (call.matches(from) && ("bye".equals(type) || "reject".equals(type) || "timeout".equals(type)
                || ("customized".equals(type) && ("REJECT_CALL".equals(data) || "CLOSE".equals(data))))) {
            end("reject".equals(type) || "REJECT_CALL".equals(data) ? "对方已拒接" : "对方已结束通话", false);
        }
        render();
    }
    private void incomingUi() {
        if (call.phase != CallState.Phase.INCOMING) return;
        message = "ESP32 请求通话";
        if (ringtone == null) {
            ringtone = RingtoneManager.getRingtone(this, RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE));
            if (ringtone != null) ringtone.play();
            main.removeCallbacks(timeout); main.postDelayed(timeout, 45000);
        }
    }
    private void microphone(int action) {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            if (action == 1) dial(); else accept();
        } else { pendingPermissionAction = action; requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 7); }
    }
    @Override public void onRequestPermissionsResult(int request, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(request, permissions, results);
        if (request != 7) return;
        int action = pendingPermissionAction; pendingPermissionAction = 0;
        if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) microphone(action);
        else { message = "需要麦克风权限才能通话"; render(); }
    }
    private void prepareMedia() throws Exception {
        if (iceServers == null) throw new IllegalStateException("音频中继尚未就绪");
        acquireAudio();
        if (media == null) media = new AudioPeer(getApplicationContext(), this);
        media.start(iceServers); negotiating = true;
        for (String candidate : earlyCandidates) media.candidate(candidate);
        earlyCandidates.clear();
        main.removeCallbacks(timeout); main.postDelayed(timeout, 60000);
    }
    private void dial() {
        if (call.phase != CallState.Phase.IDLE || !registered || iceServers == null) return;
        try {
            call.dial(device); message = "等待设备端接听"; prepareMedia(); media.offer(); render();
        } catch (Exception error) { end("呼叫失败：" + error.getMessage(), true); }
    }
    private void accept() {
        if (call.phase != CallState.Phase.INCOMING || !registered) return;
        call.accept(); stopRinging(); message = "正在接听设备";
        try {
            if (call.offer == null) {
                // ESP32 can ring first, then send its offer after ACCEPT_CALL.
                if (!send("customized", call.peer, "data", "ACCEPT_CALL")) throw new IllegalStateException("信令发送失败");
                main.removeCallbacks(timeout); main.postDelayed(timeout, 60000);
            } else answerOffer();
        } catch (Exception error) { end("接听失败：" + error.getMessage(), true); }
        render();
    }
    private void answerOffer() {
        if (negotiating || call.offer == null) return;
        try { prepareMedia(); media.remote(call.offer, true); }
        catch (Exception error) { end("接听失败：" + error.getMessage(), true); }
    }
    @Override public void signal(String type, String value) {
        if (call.phase == CallState.Phase.IDLE) return;
        if (!send(type, call.peer, "candidate".equals(type) ? "candidate" : "data", value)) end("信令发送失败", false);
        else { log("已发送：" + type); render(); }
    }
    @Override public void state(String state) {
        if (call.phase == CallState.Phase.IDLE) return;
        log("音频连接：" + state);
        if ("CONNECTED".equals(state)) {
            main.removeCallbacks(timeout); main.removeCallbacks(disconnectedTimeout);
            if (call.phase != CallState.Phase.CONNECTED) connectedAt = System.currentTimeMillis();
            call.phase = CallState.Phase.CONNECTED; message = "双向语音已连接";
        } else if ("FAILED".equals(state)) end("音频连接失败，请重新呼叫", true);
        else if ("DISCONNECTED".equals(state)) {
            message = "网络波动，正在等待恢复";
            main.removeCallbacks(disconnectedTimeout); main.postDelayed(disconnectedTimeout, 8000);
        }
        render();
    }
    @Override public void error(String error) { end("音频处理失败：" + error, true); }
    private void stopRinging() { if (ringtone != null) { ringtone.stop(); ringtone = null; } }
    private void end(String reason, boolean notify) {
        if (notify && call.phase != CallState.Phase.IDLE) send(call.phase == CallState.Phase.INCOMING ? "reject" : "bye", call.peer, null, null);
        main.removeCallbacks(timeout); main.removeCallbacks(disconnectedTimeout); stopRinging();
        call.reset(); earlyCandidates.clear(); negotiating = false; muted = false;
        if (media != null) media.close(); releaseAudio(); message = reason; log(reason); render();
    }

    private void acquireAudio() {
        if (audioAcquired) return;
        oldAudioMode = audio.getMode(); oldSpeaker = audio.isSpeakerphoneOn(); audioAcquired = true;
        AudioManager.OnAudioFocusChangeListener focus = change -> main.post(() -> {
            if (change == AudioManager.AUDIOFOCUS_LOSS && call.phase != CallState.Phase.IDLE) end("通话被其他音频打断", true);
        });
        if (Build.VERSION.SDK_INT >= 26) {
            focusRequest = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
                    .setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION).build())
                    .setOnAudioFocusChangeListener(focus).build();
            audio.requestAudioFocus(focusRequest);
        } else audio.requestAudioFocus(legacyFocus, AudioManager.STREAM_VOICE_CALL, AudioManager.AUDIOFOCUS_GAIN_TRANSIENT);
        audio.setMode(AudioManager.MODE_IN_COMMUNICATION); routeAudio();
    }
    private final AudioManager.OnAudioFocusChangeListener legacyFocus = change -> main.post(() -> {
        if (change == AudioManager.AUDIOFOCUS_LOSS && call.phase != CallState.Phase.IDLE) end("通话被其他音频打断", true);
    });
    private void routeAudio() { if (audioAcquired) audio.setSpeakerphoneOn(speaker); }
    private void releaseAudio() {
        if (!audioAcquired) return;
        audio.setSpeakerphoneOn(oldSpeaker); audio.setMode(oldAudioMode);
        if (Build.VERSION.SDK_INT >= 26 && focusRequest != null) audio.abandonAudioFocusRequest(focusRequest);
        else audio.abandonAudioFocus(legacyFocus);
        audioAcquired = false;
    }
    private void settings() {
        LinearLayout form = new LinearLayout(this); form.setOrientation(LinearLayout.VERTICAL); form.setPadding(dp(24), dp(8), dp(24), 0);
        EditText serverInput = new EditText(this); serverInput.setSingleLine(true); serverInput.setText(server); form.addView(text("服务地址（HTTPS）", 14, INK)); form.addView(serverInput);
        EditText deviceInput = new EditText(this); deviceInput.setSingleLine(true); deviceInput.setText(device); form.addView(text("ESP32 设备 ID", 14, INK)); form.addView(deviceInput);
        EditText localInput = new EditText(this); localInput.setSingleLine(true); localInput.setText(localId); form.addView(text("接听端 ID（同一 ID 只开一个客户端）", 14, INK)); form.addView(localInput);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("连接设置").setView(form).setNegativeButton("取消", null).setPositiveButton("保存并连接", null).create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            try {
                String next = serverInput.getText().toString().trim().replaceAll("/+$", ""); URI uri = URI.create(next);
                String nextDevice = deviceInput.getText().toString().trim(), nextLocal = localInput.getText().toString().trim();
                if (!"https".equals(uri.getScheme()) || uri.getHost() == null || uri.getUserInfo() != null || uri.getQuery() != null
                        || uri.getFragment() != null || !uri.getPath().isEmpty()) throw new IllegalArgumentException("请填写 HTTPS 域名地址");
                if (!nextDevice.matches("[A-Za-z0-9_-]{1,63}") || !nextLocal.matches("[A-Za-z0-9_-]{1,63}")) throw new IllegalArgumentException("ID 仅支持字母、数字、下划线和短横线");
                disconnect(); server = next; device = nextDevice; localId = nextLocal;
                preferences.edit().putString("server", server).putString("device", device).putString("local", localId).apply();
                dialog.dismiss(); connect();
            } catch (Exception error) { Toast.makeText(this, error.getMessage(), Toast.LENGTH_LONG).show(); }
        })); dialog.show();
    }
}
