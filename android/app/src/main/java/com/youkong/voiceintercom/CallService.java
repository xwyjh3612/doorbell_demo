package com.youkong.voiceintercom;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Person;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.net.ConnectivityManager;
import android.net.Network;
import android.os.Binder;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.os.Vibrator;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import okhttp3.*;

/** Owns signaling and media independently of any Activity. Main-thread only. */
public final class CallService extends Service implements AudioPeer.Listener {
    static final String ACTION_ANSWER = "com.youkong.voiceintercom.ANSWER";
    static final String ACTION_END = "com.youkong.voiceintercom.END";
    static final String ACTION_STOP = "com.youkong.voiceintercom.STOP";
    static final String EXTRA_TOKEN = "call_token";
    private static final String WAIT_CHANNEL = "voice_waiting";
    private static final String CALL_CHANNEL = "voice_incoming";
    private static final int SERVICE_NOTIFICATION = 10, INCOMING_NOTIFICATION = 11;
    private static CallService current;
    private final Handler main = new Handler(Looper.getMainLooper());
    final CallState call = new CallState();
    final StringBuilder history = new StringBuilder();
    private final List<String> earlyCandidates = new ArrayList<>();
    private final OkHttpClient client = new OkHttpClient.Builder().pingInterval(20, TimeUnit.SECONDS).build();
    private AudioPeer media;
    private AudioManager audio;
    private AudioFocusRequest focusRequest;
    private Vibrator vibrator;
    private Ringtone ringtone;
    private boolean ringing;
    private WebSocket socket;
    JSONArray iceServers;
    private String server, device, localId;
    String message = "准备连接服务", transport = "连接中";
    boolean registered, muted, speaker = true;
    private boolean running, negotiating, audioAcquired, microphoneForeground;
    private int oldAudioMode;
    private boolean oldSpeaker;
    long connectedAt;
    // Monotonic across each instance: stale notification actions cannot affect
    // a later call or a newly recreated service.
    private long callToken = android.os.SystemClock.elapsedRealtimeNanos();
    private long notifiedIncomingToken = -1;
    private final java.util.Set<Runnable> observers = new java.util.HashSet<>();
    private PowerManager.WakeLock cpuLock;
    private final Runnable renewCpuLock = new Runnable() {
        @Override public void run() {
            if (!running) return;
            cpuLock.acquire(10 * 60 * 1000L);
            main.postDelayed(this, 5 * 60 * 1000L);
        }
    };
    private ConnectivityManager connectivity;
    private boolean networkCallbackRegistered;
    private final Runnable reconnect = this::connect;
    private final Runnable timeout = () -> end("对方未接听或连接超时", true);
    private final ConnectivityManager.NetworkCallback networkCallback = new ConnectivityManager.NetworkCallback() {
        @Override public void onAvailable(Network network) { main.post(() -> {
            if (!running) return;
            // Re-register after Wi-Fi/mobile network changes, including a
            // silent dead socket which has not yet reached its ping timeout.
            if (call.phase == CallState.Phase.IDLE) { disconnect(); connect(); }
            else if (socket == null) connect();
        }); }
    };
    final class LocalBinder extends Binder { CallService service() { return CallService.this; } }
    @Override public IBinder onBind(Intent intent) { return new LocalBinder(); }
    @Override public void onCreate() {
        super.onCreate(); current = this; running = true;
        audio = (AudioManager) getSystemService(AUDIO_SERVICE);
        vibrator = (Vibrator) getSystemService(VIBRATOR_SERVICE);
        connectivity = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        readSettings(); createChannels();
        startWaitingForeground();
        PowerManager power = (PowerManager) getSystemService(POWER_SERVICE);
        cpuLock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "voiceintercom:incoming");
        cpuLock.setReferenceCounted(false);
        // A continuously available intercom is user enabled and explicitly
        // stopped through its notification. Battery exemption is also needed
        // for network delivery during Doze; a wake lock alone cannot do that.
        renewCpuLock.run();
        try { connectivity.registerDefaultNetworkCallback(networkCallback); networkCallbackRegistered = true; }
        catch (RuntimeException error) { log("网络变化监测不可用，将通过心跳重连"); }
    }
    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        connect(); return START_STICKY;
    }
    @Override public void onDestroy() {
        running = false;
        end("后台接听已关闭", true); disconnect(); observers.clear();
        if (networkCallbackRegistered) connectivity.unregisterNetworkCallback(networkCallback);
        main.removeCallbacksAndMessages(null);
        if (media != null) media.dispose();
        if (cpuLock != null && cpuLock.isHeld()) cpuLock.release();
        client.dispatcher().executorService().shutdown();
        notifications().cancel(INCOMING_NOTIFICATION);
        stopForeground(STOP_FOREGROUND_REMOVE);
        if (current == this) current = null;
        super.onDestroy();
    }
    void attach(Runnable listener) { observers.add(listener); listener.run(); }
    void detach(Runnable listener) { observers.remove(listener); }
    boolean isCurrentCall(long token) { return token == callToken && call.phase != CallState.Phase.IDLE; }
    void toggleMute() { muted = !muted; if (media != null) media.mute(muted); render(); }
    void toggleSpeaker() { speaker = !speaker; routeAudio(); render(); }
    void reloadSettings() {
        if (call.phase != CallState.Phase.IDLE) return;
        main.removeCallbacks(reconnect); disconnect(); readSettings(); connect();
    }
    private void readSettings() {
        android.content.SharedPreferences preferences = getSharedPreferences("intercom", MODE_PRIVATE);
        server = preferences.getString("server", "https://voice.2811.top");
        device = preferences.getString("device", "189833342344184");
        localId = preferences.getString("local", "web_client_001");
    }
    static void notificationAction(Intent intent) {
        CallService service = current;
        if (service == null || !service.running) return;
        if (ACTION_END.equals(intent.getAction()) && service.isCurrentCall(intent.getLongExtra(EXTRA_TOKEN, -1)))
            service.end(service.call.phase == CallState.Phase.INCOMING ? "已拒接" : "通话已结束", true);
        else if (ACTION_STOP.equals(intent.getAction()) && service.call.phase == CallState.Phase.IDLE) {
            service.end("后台接听已关闭", false); service.stopSelf();
        }
    }
    private NotificationManager notifications() { return (NotificationManager) getSystemService(NOTIFICATION_SERVICE); }
    private void createChannels() {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationChannel waiting = new NotificationChannel(WAIT_CHANNEL, "后台接听状态", NotificationManager.IMPORTANCE_LOW);
        waiting.setDescription("保持与语音终端的来电连接");
        NotificationChannel incoming = new NotificationChannel(CALL_CHANNEL, "设备来电", NotificationManager.IMPORTANCE_HIGH);
        incoming.setDescription("在后台和锁屏时显示接听、拒接");
        // Ringtone/vibration are controlled once by the call state, rather than
        // restarted every time a notification is updated.
        incoming.setSound(null, null); incoming.enableVibration(false);
        incoming.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
        notifications().createNotificationChannel(waiting); notifications().createNotificationChannel(incoming);
    }
    private PendingIntent activityIntent(String action) {
        Intent intent = new Intent(this, MainActivity.class).setAction(action)
                .setData(android.net.Uri.parse("voiceintercom://call/" + callToken + "/" + action))
                .putExtra(EXTRA_TOKEN, callToken)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        // A notification action opens the Activity directly, not a broadcast
        // trampoline: microphone access must begin while the UI is visible.
        android.os.Bundle options = null;
        if (Build.VERSION.SDK_INT >= 35) {
            android.app.ActivityOptions activityOptions = android.app.ActivityOptions.makeBasic();
            activityOptions.setPendingIntentCreatorBackgroundActivityStartMode(android.app.ActivityOptions.MODE_BACKGROUND_ACTIVITY_START_ALLOWED);
            options = activityOptions.toBundle();
        }
        if (ACTION_ANSWER.equals(action) || "incoming".equals(action)) intent.setClass(this, IncomingCallActivity.class);
        return PendingIntent.getActivity(this, 0, intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE, options);
    }
    private PendingIntent actionIntent(String action) {
        Intent intent = new Intent(this, CallActionReceiver.class).setAction(action)
                .setData(android.net.Uri.parse("voiceintercom://action/" + callToken + "/" + action))
                .putExtra(EXTRA_TOKEN, callToken);
        return PendingIntent.getBroadcast(this, 0, intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }
    private Notification.Builder builder(String channel) {
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, channel) : new Notification.Builder(this);
        return builder.setSmallIcon(com.youkong.voiceintercom.R.drawable.ic_intercom)
                .setContentIntent(activityIntent("open"))
                .setVisibility(Notification.VISIBILITY_PUBLIC).setOnlyAlertOnce(true);
    }
    private Notification ongoingNotification() {
        boolean active = call.phase != CallState.Phase.IDLE && call.phase != CallState.Phase.INCOMING;
        Notification.Builder builder = builder(WAIT_CHANNEL).setOngoing(true)
                .setContentTitle(active ? (call.phase == CallState.Phase.CONNECTED ? "语音对讲 · 通话中" : "语音对讲 · 正在接通") : "语音对讲 · 后台接听已开启")
                .setContentText(active ? "点击返回通话" : transport + " · 等待设备来电")
                .setCategory(active ? Notification.CATEGORY_CALL : Notification.CATEGORY_SERVICE);
        if (active) {
            if (Build.VERSION.SDK_INT >= 31) builder.setStyle(Notification.CallStyle.forOngoingCall(
                    new Person.Builder().setName("语音终端").setImportant(true).build(), actionIntent(ACTION_END)));
            else builder.addAction(new Notification.Action.Builder(null, "挂断", actionIntent(ACTION_END)).build());
        } else if (call.phase == CallState.Phase.IDLE)
            builder.addAction(new Notification.Action.Builder(null, "关闭后台接听", actionIntent(ACTION_STOP)).build());
        return builder.build();
    }
    private Notification incomingNotification(boolean fullScreenAllowed, boolean callStyle) {
        PendingIntent answer = activityIntent(ACTION_ANSWER), decline = actionIntent(ACTION_END);
        Notification.Builder builder = builder(CALL_CHANNEL).setOngoing(true)
                .setContentTitle("语音终端来电").setContentText("点击接听，与设备通话")
                .setContentIntent(activityIntent("incoming"))
                .setCategory(Notification.CATEGORY_CALL).setPriority(Notification.PRIORITY_MAX);
        if (fullScreenAllowed) builder.setFullScreenIntent(activityIntent("incoming"), true);
        if (Build.VERSION.SDK_INT >= 31 && fullScreenAllowed && callStyle) builder.setStyle(Notification.CallStyle.forIncomingCall(
                new Person.Builder().setName("语音终端").setImportant(true).build(), decline, answer));
        else {
            builder.addAction(new Notification.Action.Builder(null, "拒接", decline).build());
            builder.addAction(new Notification.Action.Builder(null, "接听", answer).build());
        }
        return builder.build();
    }
    private void postIncomingNotification() {
        boolean fullScreen = Build.VERSION.SDK_INT < 34 || notifications().canUseFullScreenIntent();
        try { notifications().notify(INCOMING_NOTIFICATION, incomingNotification(fullScreen, true)); return; }
        catch (RuntimeException error) { log("全屏来电通知不可用，尝试普通接听通知"); }
        try { notifications().notify(INCOMING_NOTIFICATION, incomingNotification(false, false)); }
        catch (RuntimeException error) { log("来电通知未获准，请在系统设置中允许通知"); }
    }
    private void startWaitingForeground() {
        Notification notification = ongoingNotification();
        if (Build.VERSION.SDK_INT >= 34)
            startForeground(SERVICE_NOTIFICATION, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        else startForeground(SERVICE_NOTIFICATION, notification);
    }
    private void promoteMicrophone() {
        Notification notification = ongoingNotification();
        if (Build.VERSION.SDK_INT >= 34) startForeground(SERVICE_NOTIFICATION, notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE | ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE);
        else if (Build.VERSION.SDK_INT >= 30) startForeground(SERVICE_NOTIFICATION, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE);
        else startForeground(SERVICE_NOTIFICATION, notification);
        microphoneForeground = true;
    }
    private void render() {
        if (running) {
            if (microphoneForeground) promoteMicrophone(); else startWaitingForeground();
            if (call.phase == CallState.Phase.INCOMING) {
                if (notifiedIncomingToken != callToken) {
                    notifiedIncomingToken = callToken;
                    postIncomingNotification();
                }
            } else { notifications().cancel(INCOMING_NOTIFICATION); notifiedIncomingToken = -1; }
        }
        for (Runnable observer : new java.util.ArrayList<>(observers)) observer.run();
    }
    private void log(String value) {
        android.util.Log.i("VoiceIntercom", value);
        history.append(new java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.ROOT).format(new java.util.Date())).append("  ").append(value).append('\n');
        if (history.length() > 1800) history.delete(0, history.indexOf("\n", 500) + 1);
    }

    private void connect() {
        if (!running || socket != null) return;
        registered = false; iceServers = null; transport = "连接中"; render();
        String url = server.replaceFirst("^https://", "wss://") + "/signaling";
        socket = client.newWebSocket(new Request.Builder().url(url).build(), new WebSocketListener() {
            @Override public void onOpen(WebSocket ws, Response response) { main.post(() -> {
                if (socket != ws || !running) return;
                log("安全信令已连接"); send("register", null, null, null); send("ice_request", null, null, null);
            }); }
            @Override public void onMessage(WebSocket ws, String value) { main.post(() -> {
                if (socket != ws || !running) return;
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
        if (running) { main.removeCallbacks(reconnect); main.postDelayed(reconnect, 3000); }
    }
    private void disconnect() {
        WebSocket previous = socket; socket = null; registered = false; iceServers = null;
        if (previous != null) previous.close(1000, "intercom service stopped");
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
        if (!ringing) {
            ringing = true; callToken++;
            ringtone = RingtoneManager.getRingtone(this, RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE));
            if (ringtone != null) {
                ringtone.setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION_RINGTONE).build());
                if (Build.VERSION.SDK_INT >= 28) ringtone.setLooping(true);
                ringtone.play();
            }
            vibrator.vibrate(new long[]{0, 600, 1200}, 0);
            main.removeCallbacks(timeout); main.postDelayed(timeout, 45000);
        }
    }
    private void prepareMedia() throws Exception {
        if (iceServers == null) throw new IllegalStateException("音频中继尚未就绪");
        // Called only after an explicit action in a resumed Activity, so Android
        // 14+ permits promoting the service to microphone foreground service.
        promoteMicrophone();
        acquireAudio();
        if (media == null) media = new AudioPeer(getApplicationContext(), this);
        media.start(iceServers); negotiating = true;
        for (String candidate : earlyCandidates) media.candidate(candidate);
        earlyCandidates.clear();
        main.removeCallbacks(timeout); main.postDelayed(timeout, 60000);
    }
    void dial() {
        if (call.phase != CallState.Phase.IDLE || !registered || iceServers == null) return;
        try {
            callToken++; call.dial(device); message = "等待设备端接听"; prepareMedia(); media.offer(); render();
        } catch (Exception error) { end("呼叫失败：" + error.getMessage(), true); }
    }
    void accept() {
        if (call.phase != CallState.Phase.INCOMING || !registered) return;
        call.accept(); stopRinging(); message = "正在接听设备";
        try {
            // Ring-first calls may deliver the offer after the incoming UI has
            // closed. Acquire microphone foreground access on the user's
            // visible accept action, before sending ACCEPT_CALL.
            promoteMicrophone();
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
            main.removeCallbacks(timeout);
            if (call.phase != CallState.Phase.CONNECTED) connectedAt = System.currentTimeMillis();
            call.phase = CallState.Phase.CONNECTED; message = "双向语音已连接";
        } else if ("FAILED".equals(state)) end("音频连接失败，请重新呼叫", true);
        else if ("DISCONNECTED".equals(state)) {
            // DISCONNECTED is recoverable; keep this peer, audio foreground
            // service and call alive. Sending BYE after eight seconds destroys
            // the session before ICE consent checks can recover it.
            message = "音频暂时中断，正在等待恢复";
        }
        render();
    }
    @Override public void error(String error) { end("音频处理失败：" + error, true); }
    private void stopRinging() { ringing = false; if (ringtone != null) { ringtone.stop(); ringtone = null; } vibrator.cancel(); }
    void end(String reason, boolean notify) {
        if (notify && call.phase != CallState.Phase.IDLE) send(call.phase == CallState.Phase.INCOMING ? "reject" : "bye", call.peer, null, null);
        main.removeCallbacks(timeout); stopRinging();
        call.reset(); earlyCandidates.clear(); negotiating = false; muted = false;
        if (media != null) media.close(); releaseAudio(); microphoneForeground = false;
        message = reason; log(reason); render();
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
}
