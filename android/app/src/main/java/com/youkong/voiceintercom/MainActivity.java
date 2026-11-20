package com.youkong.voiceintercom;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.AudioManager;
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
import java.util.concurrent.TimeUnit;
import okhttp3.*;

public final class MainActivity extends Activity {
    private static final int INK = Color.rgb(226, 237, 249);
    private static final int GREEN = Color.rgb(67, 226, 199);
    private static final int PANEL = Color.rgb(17, 34, 55);
    private static final int MUTED = Color.rgb(133, 156, 181);
    private final Handler main = new Handler(Looper.getMainLooper());
    private CallState call = new CallState();
    private CallService calls;
    private boolean bound;
    private android.content.Intent pendingCallIntent;
    private final Runnable callObserver = this::render;
    private final OkHttpClient client = new OkHttpClient.Builder().pingInterval(20, TimeUnit.SECONDS).build();
    private SharedPreferences preferences;
    private WebSocket telemetrySocket;
    private TelemetryState telemetry = new TelemetryState();
    private final Runnable telemetryReconnect = this::connectTelemetry;
    private JSONArray iceServers;
    private String server, device, localId;
    private String message = "准备连接服务";
    private String transport = "连接中";
    private boolean visible, registered, muted, speaker = true;
    private int pendingPermissionAction;
    private long connectedAt;
    private long telemetryRenderedAt;
    private TextView connectionLabel, statusLabel, subtitleLabel, deviceLabel, durationLabel, diagnostics;
    private TextView deviceOnline, radarSummary, breathValue, heartValue, distanceValue, breathNote, heartNote, distanceNote;
    private LinearLayout vitalsPanel;
    private LinearLayout audioControls;
    private RadarVisual radarVisual;
    private TrendView breathTrend, heartTrend;
    private Button callButton, answerButton, rejectButton, hangupButton, muteButton, speakerButton, settingsButton;
    private final Runnable clock = new Runnable() {
        public void run() {
            if (!visible) return;
            if (call.phase == CallState.Phase.CONNECTED) {
                long seconds = (System.currentTimeMillis() - connectedAt) / 1000;
                durationLabel.setText(String.format(java.util.Locale.ROOT, "%02d:%02d", seconds / 60, seconds % 60));
            }
            if(android.os.SystemClock.elapsedRealtime()-telemetryRenderedAt>=5000)renderTelemetry();
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
        setVolumeControlStream(AudioManager.STREAM_VOICE_CALL);
        pendingCallIntent = getIntent();
        prepareIncomingWindow(pendingCallIntent);
        buildUi();
        requestNotificationPermission();
    }

    private final android.content.ServiceConnection serviceConnection = new android.content.ServiceConnection() {
        @Override public void onServiceConnected(android.content.ComponentName name, android.os.IBinder binder) {
            calls = ((CallService.LocalBinder) binder).service();
            calls.attach(callObserver);
            render(); handleCallIntent();
        }
        @Override public void onServiceDisconnected(android.content.ComponentName name) {
            calls = null; call = new CallState(); registered = false; iceServers = null;
            transport = "后台服务已停止，请重新打开 App"; render();
        }
    };
    @Override public void onStart() {
        super.onStart(); visible = true;
        android.content.Intent service = new android.content.Intent(this, CallService.class);
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(service); else startService(service);
        bound = bindService(service, serviceConnection, BIND_AUTO_CREATE);
        connectTelemetry(); main.post(clock);
    }
    @Override public void onResume() { super.onResume(); handleCallIntent(); }
    @Override public void onNewIntent(android.content.Intent intent) {
        super.onNewIntent(intent); setIntent(intent); pendingCallIntent = intent;
        prepareIncomingWindow(intent); handleCallIntent();
    }
    private void prepareIncomingWindow(android.content.Intent intent) {
        if (intent == null || intent.getLongExtra(CallService.EXTRA_TOKEN, -1) < 0) return;
        if (Build.VERSION.SDK_INT >= 27) { setShowWhenLocked(true); setTurnScreenOn(true); }
        else getWindow().addFlags(WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON);
    }
    @Override public void onStop() {
        visible = false; main.removeCallbacks(clock); main.removeCallbacks(telemetryReconnect);
        disconnectTelemetry();
        if (calls != null) calls.detach(callObserver);
        if (bound) { unbindService(serviceConnection); bound = false; }
        calls = null;
        super.onStop();
    }
    @Override public void onDestroy() {
        main.removeCallbacksAndMessages(null);
        client.dispatcher().executorService().shutdown(); super.onDestroy();
    }
    private void handleCallIntent() {
        if (calls == null || pendingCallIntent == null || !hasWindowFocus()) return;
        android.content.Intent intent = pendingCallIntent; pendingCallIntent = null;
        if (!calls.isCurrentCall(intent.getLongExtra(CallService.EXTRA_TOKEN, -1))) return;
        if (CallService.ACTION_ANSWER.equals(intent.getAction())) microphone(2);
    }
    @Override public void onWindowFocusChanged(boolean focused) {
        super.onWindowFocusChanged(focused); if (focused) handleCallIntent();
    }
    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 8);
    }
    private void microphone(int action) {
        if (calls == null) return;
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            if (action == 1) calls.dial(); else calls.accept();
        } else { pendingPermissionAction = action; requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 7); }
    }
    @Override public void onRequestPermissionsResult(int request, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(request, permissions, results);
        if (request == 7) {
            int action = pendingPermissionAction; pendingPermissionAction = 0;
            if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) microphone(action);
            else Toast.makeText(this, "需要麦克风权限才能通话", Toast.LENGTH_LONG).show();
        } else if (request == 8 && (results.length == 0 || results[0] != PackageManager.PERMISSION_GRANTED)) {
            Toast.makeText(this, "请在设置中允许通知，否则后台来电无法显示", Toast.LENGTH_LONG).show();
        }
    }
    private void end(String reason, boolean notify) { if (calls != null) calls.end(reason, notify); }

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
        button.setAllCaps(false); button.setBackground(background(color, 16)); button.setElevation(dp(0));
        LinearLayout.LayoutParams layout = new LinearLayout.LayoutParams(-1, dp(54)); layout.topMargin = dp(10);
        button.setLayoutParams(layout); button.setOnClickListener(v -> action.run()); return button;
    }
    private void buildUi() {
        getWindow().setStatusBarColor(Color.rgb(8,19,35));getWindow().setNavigationBarColor(Color.rgb(8,19,35));
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true); scroll.setBackgroundColor(Color.rgb(8,19,35));
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(20), dp(30), dp(20), dp(28)); scroll.addView(root); setContentView(scroll);
        LinearLayout heading=new LinearLayout(this);heading.setGravity(Gravity.CENTER_VERTICAL);root.addView(heading);
        LinearLayout branding=new LinearLayout(this);branding.setOrientation(LinearLayout.VERTICAL);heading.addView(branding,new LinearLayout.LayoutParams(0,-2,1));
        TextView eyebrow = text("VOICE LINK  /  4G", 11, GREEN); eyebrow.setLetterSpacing(0.16f); branding.addView(eyebrow);
        TextView title=text("声联 · 智能对讲",25,INK);title.setTypeface(null,Typeface.BOLD);title.setPadding(0,dp(8),0,dp(3));branding.addView(title);
        settingsButton=button("设置",PANEL,MUTED,this::settings);heading.addView(settingsButton,new LinearLayout.LayoutParams(dp(64),dp(44)));
        TextView tagline=text("声音互联，让感知触手可及",12,MUTED);root.addView(tagline);
        connectionLabel=text("● 连接中",12,MUTED);connectionLabel.setPadding(0,dp(16),0,dp(12));root.addView(connectionLabel);
        LinearLayout card = new LinearLayout(this); card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(20),dp(17),dp(20),dp(18));
        GradientDrawable hero=new GradientDrawable(GradientDrawable.Orientation.TL_BR,new int[]{Color.rgb(19,45,66),Color.rgb(14,27,46)});hero.setCornerRadius(dp(24));hero.setStroke(dp(1),Color.rgb(34,66,87));card.setBackground(hero);
        LinearLayout.LayoutParams cardLayout = new LinearLayout.LayoutParams(-1, -2);
        root.addView(card, cardLayout);
        LinearLayout deviceRow=new LinearLayout(this);deviceRow.setGravity(Gravity.CENTER_VERTICAL);card.addView(deviceRow);
        deviceRow.addView(text("感知终端 01",14,INK),new LinearLayout.LayoutParams(0,-2,1));deviceOnline=text("● 状态待确认",11,MUTED);deviceRow.addView(deviceOnline);
        deviceLabel=text(device,11,MUTED);deviceLabel.setPadding(0,dp(4),0,0);card.addView(deviceLabel);
        radarVisual=new RadarVisual(this);card.addView(radarVisual,new LinearLayout.LayoutParams(-1,dp(170)));
        LinearLayout statusRow=new LinearLayout(this);statusRow.setGravity(Gravity.CENTER_VERTICAL);card.addView(statusRow);
        statusLabel=text("待机",25,INK);statusLabel.setTypeface(null,Typeface.BOLD);statusRow.addView(statusLabel,new LinearLayout.LayoutParams(0,-2,1));
        durationLabel=text("随时连接",19,GREEN);statusRow.addView(durationLabel);
        subtitleLabel=text(message,12,MUTED);subtitleLabel.setPadding(0,dp(7),0,dp(3));card.addView(subtitleLabel);
        callButton=button("呼叫设备",GREEN,Color.rgb(6,41,45),()->microphone(1));root.addView(callButton);
        answerButton=button("接听来电",GREEN,Color.rgb(6,41,45),()->microphone(2));root.addView(answerButton);
        rejectButton=button("拒接",Color.rgb(75,37,49),Color.rgb(255,153,155),()->end("已拒接",true));root.addView(rejectButton);
        hangupButton=button("挂断通话",Color.rgb(75,37,49),Color.rgb(255,153,155),()->end("通话已结束",true));root.addView(hangupButton);
        LinearLayout controls = new LinearLayout(this); audioControls=controls; root.addView(controls);
        muteButton = button("麦克风开", PANEL, INK, () -> {
            if (calls != null) calls.toggleMute();
        });
        speakerButton = button("扬声器", PANEL, INK, () -> { if (calls != null) calls.toggleSpeaker(); });
        LinearLayout.LayoutParams half = new LinearLayout.LayoutParams(0, dp(52), 1); half.topMargin = dp(10); half.rightMargin = dp(6);
        controls.addView(muteButton, half);
        LinearLayout.LayoutParams half2 = new LinearLayout.LayoutParams(0, dp(52), 1); half2.topMargin = dp(10); half2.leftMargin = dp(6);
        controls.addView(speakerButton, half2);
        TextView sensingTitle=text("空间感知",17,INK);sensingTitle.setTypeface(null,Typeface.BOLD);sensingTitle.setPadding(0,dp(23),0,dp(7));root.addView(sensingTitle);
        radarSummary=text("等待终端上传感知状态",12,MUTED);root.addView(radarSummary);
        vitalsPanel=new LinearLayout(this);vitalsPanel.setOrientation(LinearLayout.VERTICAL);root.addView(vitalsPanel);
        LinearLayout metrics=new LinearLayout(this);vitalsPanel.addView(metrics);
        TextView[] breathing=metric(metrics,"呼吸频率","次 / 分",GREEN);breathValue=breathing[0];breathNote=breathing[1];
        TextView[] heart=metric(metrics,"心率","次 / 分",Color.rgb(255,154,133));heartValue=heart[0];heartNote=heart[1];
        TextView[] distance=metric(metrics,"目标距离","cm",Color.rgb(117,188,255));distanceValue=distance[0];distanceNote=distance[1];
        LinearLayout trends=new LinearLayout(this);vitalsPanel.addView(trends);
        breathTrend=trend(trends,"呼吸趋势",GREEN,40);heartTrend=trend(trends,"心率趋势",Color.rgb(255,154,133),120);
        TextView trendNote=text("近 2 分钟实际上报值 · 静坐并让雷达朝向胸口",11,MUTED);trendNote.setPadding(0,dp(9),0,0);vitalsPanel.addView(trendNote);
        TextView note=text("已支持后台及锁屏来电，请在下方检查来电权限。生命体征读数用于功能展示。",11,MUTED);note.setPadding(0,dp(20),0,dp(8));root.addView(note);
        diagnostics=text("",11,MUTED);diagnostics.setPadding(0,dp(10),0,0);diagnostics.setTextIsSelectable(true);diagnostics.setVisibility(View.GONE);
        Button details=button("运行记录",PANEL,MUTED,()->diagnostics.setVisibility(diagnostics.getVisibility()==View.GONE?View.VISIBLE:View.GONE));root.addView(details);root.addView(diagnostics);
        root.addView(button("后台与锁屏来电设置", PANEL, INK, this::backgroundSettings));
        render();
    }
    private TextView[] metric(LinearLayout row,String label,String unit,int color){
        LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(dp(12),dp(15),dp(10),dp(13));box.setBackground(background(PANEL,16));
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,-2,1);lp.topMargin=dp(12);lp.rightMargin=dp(5);row.addView(box,lp);
        box.addView(text(label,11,MUTED));TextView value=text("—",30,color);value.setTypeface(null,Typeface.BOLD);value.setPadding(0,dp(5),0,0);box.addView(value);box.addView(text(unit,10,MUTED));
        TextView note=text("等待测量",10,MUTED);note.setPadding(0,dp(9),0,0);box.addView(note);return new TextView[]{value,note};
    }
    private TrendView trend(LinearLayout row,String label,int color,int maximum){
        LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(dp(12),dp(13),dp(12),dp(10));box.setBackground(background(PANEL,16));
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,-2,1);lp.topMargin=dp(10);lp.rightMargin=dp(5);row.addView(box,lp);box.addView(text(label,11,MUTED));
        TrendView chart=new TrendView(this,color,maximum);box.addView(chart,new LinearLayout.LayoutParams(-1,dp(58)));return chart;
    }

    private void render() {
        if (calls != null) {
            call = calls.call; registered = calls.registered; iceServers = calls.iceServers;
            message = calls.message; transport = calls.transport; muted = calls.muted;
            speaker = calls.speaker; connectedAt = calls.connectedAt;
        }
        boolean awaitingService = calls == null && pendingCallIntent != null
                && pendingCallIntent.getLongExtra(CallService.EXTRA_TOKEN, -1) >= 0;
        boolean active = call.phase != CallState.Phase.IDLE || awaitingService;
        if (Build.VERSION.SDK_INT >= 27) { setShowWhenLocked(active); setTurnScreenOn(call.phase == CallState.Phase.INCOMING || awaitingService); }
        else if (active) getWindow().addFlags(WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON);
        else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON);
        connectionLabel.setText("● " + transport + "   /   双向语音");
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
        if (call.phase != CallState.Phase.CONNECTED) durationLabel.setText(call.phase==CallState.Phase.IDLE?"随时连接":"正在连接");
        boolean idle = call.phase == CallState.Phase.IDLE;
        boolean incoming = call.phase == CallState.Phase.INCOMING;
        callButton.setVisibility(idle ? View.VISIBLE : View.GONE);
        callButton.setEnabled(registered && iceServers != null);
        callButton.setAlpha(callButton.isEnabled() ? 1f : 0.45f);
        answerButton.setVisibility(incoming ? View.VISIBLE : View.GONE);
        rejectButton.setVisibility(incoming ? View.VISIBLE : View.GONE);
        hangupButton.setVisibility(!idle && !incoming ? View.VISIBLE : View.GONE);
        muteButton.setEnabled(!idle && !incoming); speakerButton.setEnabled(!idle && !incoming);
        audioControls.setVisibility(!idle && !incoming ? View.VISIBLE : View.GONE);
        muteButton.setText(muted ? "麦克风关" : "麦克风开"); speakerButton.setText(speaker ? "扬声器" : "听筒");
        settingsButton.setEnabled(idle); diagnostics.setText(calls == null ? "等待后台服务" : calls.history.toString());
        renderTelemetry();
    }
    private void renderTelemetry() {
        long now=android.os.SystemClock.elapsedRealtime();
        telemetryRenderedAt=now;
        boolean active=call.phase!=CallState.Phase.IDLE, audioLive=call.phase==CallState.Phase.CONNECTED;
        boolean online=audioLive||telemetry.online(now), radarLive=telemetry.radarLive(now);
        deviceOnline.setText(online?"● 终端在线":telemetry.reportId>0?"● 状态暂未更新":"● 状态待确认");
        deviceOnline.setTextColor(online?GREEN:MUTED);
        String target="等待感知数据";
        if(radarLive){
            target="雷达数据在线";
            if(telemetry.presence==1)target="有人 · 感知中";
            else if(telemetry.presence==0)target="无人 · 守候中";
            else if(telemetry.activity==1)target="静止目标";
            else if(telemetry.activity==2)target="活动目标";
            else if(telemetry.activity==0)target="无活动目标";
        }else if(active)target="语音连接优先";
        else if(telemetry.reportId>0)target="等待数据更新";
        radarVisual.state(target,radarLive);
        vitalsPanel.setVisibility("r24d".equals(telemetry.model)?View.GONE:View.VISIBLE);
        String model=telemetry.vitals()?"60GHz 生命体征":"r24d".equals(telemetry.model)?"24GHz 人体感应":"感知模块";
        if(active)radarSummary.setText(model+" · 通话期间本地采集，挂断后更新");
        else if(radarLive)radarSummary.setText(model+" · "+target+" · 体动 "+(telemetry.motion<0?"—":telemetry.motion));
        else radarSummary.setText(model+" · "+(telemetry.reportId>0?"等待终端最新上报":"等待终端上传感知状态"));
        metricValue(breathValue,breathNote,telemetry.breath,telemetry.breathAge,now,active);
        metricValue(heartValue,heartNote,telemetry.heart,telemetry.heartAge,now,active);
        metricValue(distanceValue,distanceNote,telemetry.distance,telemetry.distanceAge,now,active);
        breathTrend.invalidate();heartTrend.invalidate();
    }
    private void metricValue(TextView value,TextView note,int reading,long fieldAge,long now,boolean active){
        boolean fresh=telemetry.fresh(fieldAge,now);
        value.setText(reading>0&&(fresh||active)?String.valueOf(reading):"—");
        value.setAlpha(fresh?1f:0.45f);
        if(reading==0)note.setText("尚无有效测量");
        else if(reading<0)note.setText("等待测量");
        else if(fresh)note.setText("约 "+Math.max(0,(fieldAge+telemetry.serverAge+telemetry.elapsed(now))/1000)+" 秒前上报");
        else note.setText(active?"缓存 · 通话后刷新":"数据已过期");
    }
    private void connectTelemetry(){
        if(!visible||telemetrySocket!=null)return;
        String url=server.replaceFirst("^https://","wss://")+"/telemetry?device="+device;
        telemetrySocket=client.newWebSocket(new Request.Builder().url(url).build(),new WebSocketListener(){
            @Override public void onOpen(WebSocket ws,Response response){main.post(()->{if(telemetrySocket==ws){telemetry.socketOpen=true;renderTelemetry();}});}
            @Override public void onMessage(WebSocket ws,String value){main.post(()->{
                if(telemetrySocket!=ws||!visible)return;
                try{
                    JSONObject envelope=new JSONObject(value);
                    if(!device.equals(envelope.optString("device")))return;
                    JSONObject data=envelope.optJSONObject("radar");if(data==null)return;
                    String model=data.optString("radar");
                    if(!model.equals(telemetry.model)||data.optLong("uptime_ms")<lastRadarUptime){breathTrend.clear();heartTrend.clear();}
                    long nextReport=envelope.optLong("received_at_ms"),now=android.os.SystemClock.elapsedRealtime();
                    telemetry.model=model;telemetry.serverAge=envelope.optLong("age_ms",-1);telemetry.receivedMono=now;
                    telemetry.rxAge=data.optLong("rx_age_ms",-1);telemetry.breathAge=data.optLong("breath_age_ms",-1);telemetry.heartAge=data.optLong("heart_age_ms",-1);telemetry.distanceAge=data.optLong("distance_age_ms",-1);
                    telemetry.presence=data.optInt("presence",-1);telemetry.activity=data.optInt("activity",-1);telemetry.motion=data.optInt("motion",-1);
                    telemetry.breath=data.optInt("breath",-1);telemetry.heart=data.optInt("heart",-1);telemetry.distance=data.optInt("distance_cm",-1);
                    if(nextReport!=telemetry.reportId){
                        if(telemetry.fresh(telemetry.breathAge,now))breathTrend.add(now-telemetry.breathAge-telemetry.serverAge,telemetry.breath);
                        if(telemetry.fresh(telemetry.heartAge,now))heartTrend.add(now-telemetry.heartAge-telemetry.serverAge,telemetry.heart);
                    }
                    telemetry.reportId=nextReport;lastRadarUptime=data.optLong("uptime_ms");renderTelemetry();
                }catch(Exception ignored){/* Observation errors never terminate a call. */}
            });}
            @Override public void onFailure(WebSocket ws,Throwable error,Response response){main.post(()->telemetryLost(ws));}
            @Override public void onClosed(WebSocket ws,int code,String reason){main.post(()->telemetryLost(ws));}
        });
    }
    private long lastRadarUptime;
    private void telemetryLost(WebSocket ws){
        if(telemetrySocket!=ws)return;telemetrySocket=null;telemetry.socketOpen=false;renderTelemetry();
        if(visible){main.removeCallbacks(telemetryReconnect);main.postDelayed(telemetryReconnect,3000);}
    }
    private void disconnectTelemetry(){
        main.removeCallbacks(telemetryReconnect);WebSocket previous=telemetrySocket;telemetrySocket=null;telemetry.socketOpen=false;
        if(previous!=null)previous.close(1000,"page closed");
    }
    // A self-hosted, user-enabled VoIP intercom has no FCM wake-up provider;
    // incoming calls are an acceptable battery-exemption use case in the
    // Android Doze documentation. The user explicitly enables it in Settings.
    @android.annotation.SuppressLint("BatteryLife")
    private void backgroundSettings() {
        android.app.NotificationManager notifications = (android.app.NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        android.os.PowerManager power = (android.os.PowerManager) getSystemService(POWER_SERVICE);
        boolean allowed = notifications.areNotificationsEnabled();
        boolean fullscreen = Build.VERSION.SDK_INT < 34 || notifications.canUseFullScreenIntent();
        boolean battery = power.isIgnoringBatteryOptimizations(getPackageName());
        String summary = "来电通知：" + (allowed ? "已允许" : "未允许")
                + "\n锁屏全屏来电：" + (fullscreen ? "已允许" : "未允许")
                + "\n后台电池限制：" + (battery ? "已解除" : "未解除")
                + "\n\n请允许通知并将电池设置为不受限制。部分手机还需在系统中允许自启动和后台运行。"
                + "\n后台接听开启后有常驻通知；可在通知中关闭。系统强行停止 App 后需重新打开。";
        new AlertDialog.Builder(this).setTitle("后台与锁屏来电").setMessage(summary)
                .setPositiveButton("通知设置", (dialog, which) -> {
                    android.content.Intent settings;
                    if (Build.VERSION.SDK_INT >= 26) settings = new android.content.Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                            .putExtra(android.provider.Settings.EXTRA_APP_PACKAGE, getPackageName());
                    else settings = new android.content.Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                            .setData(android.net.Uri.parse("package:" + getPackageName()));
                    openSystemSetting(settings);
                })
                .setNeutralButton("后台电池设置", (dialog, which) -> openSystemSetting(new android.content.Intent(
                        battery ? android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS : android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
                        .setData(android.net.Uri.parse("package:" + getPackageName()))))
                .setNegativeButton(Build.VERSION.SDK_INT >= 34 ? "锁屏来电设置" : "关闭", (dialog, which) -> {
                    if (Build.VERSION.SDK_INT >= 34) openSystemSetting(new android.content.Intent(
                            android.provider.Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT)
                            .setData(android.net.Uri.parse("package:" + getPackageName())));
                }).show();
    }
    private void openSystemSetting(android.content.Intent intent) {
        try { startActivity(intent); }
        catch (android.content.ActivityNotFoundException error) {
            startActivity(new android.content.Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                    .setData(android.net.Uri.parse("package:" + getPackageName())));
        }
    }
    private void settings() {
        LinearLayout form = new LinearLayout(this); form.setOrientation(LinearLayout.VERTICAL); form.setPadding(dp(24), dp(8), dp(24), 0);
        EditText serverInput = new EditText(this); serverInput.setSingleLine(true); serverInput.setText(server); form.addView(text("服务地址（HTTPS）", 14, Color.DKGRAY)); form.addView(serverInput);
        EditText deviceInput = new EditText(this); deviceInput.setSingleLine(true); deviceInput.setText(device); form.addView(text("ESP32 设备 ID", 14, Color.DKGRAY)); form.addView(deviceInput);
        EditText localInput = new EditText(this); localInput.setSingleLine(true); localInput.setText(localId); form.addView(text("接听端 ID（同一 ID 只开一个客户端）", 14, Color.DKGRAY)); form.addView(localInput);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("连接设置").setView(form).setNegativeButton("取消", null).setPositiveButton("保存并连接", null).create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            try {
                String next = serverInput.getText().toString().trim().replaceAll("/+$", ""); URI uri = URI.create(next);
                String nextDevice = deviceInput.getText().toString().trim(), nextLocal = localInput.getText().toString().trim();
                if (!"https".equals(uri.getScheme()) || uri.getHost() == null || uri.getUserInfo() != null || uri.getQuery() != null
                        || uri.getFragment() != null || !uri.getPath().isEmpty()) throw new IllegalArgumentException("请填写 HTTPS 域名地址");
                if (!nextDevice.matches("[A-Za-z0-9_-]{1,63}") || !nextLocal.matches("[A-Za-z0-9_-]{1,63}")) throw new IllegalArgumentException("ID 仅支持字母、数字、下划线和短横线");
                disconnectTelemetry(); server = next; device = nextDevice; localId = nextLocal;
                telemetry=new TelemetryState();lastRadarUptime=0;breathTrend.clear();heartTrend.clear();
                preferences.edit().putString("server", server).putString("device", device).putString("local", localId).apply();
                if (calls != null) calls.reloadSettings();
                dialog.dismiss(); connectTelemetry();
            } catch (Exception error) { Toast.makeText(this, error.getMessage(), Toast.LENGTH_LONG).show(); }
        })); dialog.show();
    }
}
