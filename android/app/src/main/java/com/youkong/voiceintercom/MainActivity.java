package com.youkong.voiceintercom;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.DatePickerDialog;
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
    private TextView deviceOnline, powerSummary, radarSummary, breathValue, heartValue, distanceValue, breathNote, heartNote, distanceNote;
    private LinearLayout vitalsPanel;
    private LinearLayout audioControls;
    private RadarVisual radarVisual;
    private IncomingPulseView incomingPulse;
    private long presentedIncoming=-1;
    private boolean resumed;
    private ScrollView homeScroll;
    private LinearLayout incomingActions;
    private TrendView breathTrend, heartTrend;
    private PresenceTimeline timeline;
    private TextView historyPeriod, historySummary, historySelection;
    private AlertCenter alerts;
    private TextView permissionHint;
    private android.widget.ArrayAdapter<String> permissionRows;

    private LinearLayout historyRows;
    private Button historyHour, historyToday, historyDate;
    private Call historyRequest;
    private int historyGeneration;
    private boolean historyHourly = true;
    private java.util.Calendar historyDay = java.util.Calendar.getInstance();
    private long historyFetchedAt;
    private Button callButton, answerButton, rejectButton, hangupButton, muteButton, speakerButton, settingsButton;
    private final Runnable clock = new Runnable() {
        public void run() {
            if (!visible) return;
            if (call.phase == CallState.Phase.CONNECTED) {
                long seconds = (System.currentTimeMillis() - connectedAt) / 1000;
                durationLabel.setText(String.format(java.util.Locale.ROOT, "%02d:%02d", seconds / 60, seconds % 60));
            }
            if(android.os.SystemClock.elapsedRealtime()-telemetryRenderedAt>=5000)renderTelemetry();
            if(android.os.SystemClock.elapsedRealtime()-historyFetchedAt>=30000 && historyRequest==null && (historyHourly || historyIsToday()))loadHistory();
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
        connectTelemetry(); loadHistory(); main.post(clock);
    }
    @Override public void onResume() { super.onResume(); resumed=true;refreshPermissionHints();handleCallIntent();presentIncoming(); }
    @Override public void onPause(){resumed=false;super.onPause();}
    private void presentIncoming(){
        if(calls==null || !resumed || !hasWindowFocus() || isFinishing())return;
        long token=calls.incomingToken();if(token<0 || token==presentedIncoming)return;
        presentedIncoming=token;
        startActivity(new android.content.Intent(this,IncomingCallActivity.class).setAction("incoming")
                .putExtra(CallService.EXTRA_TOKEN,token).addFlags(android.content.Intent.FLAG_ACTIVITY_SINGLE_TOP));
    }
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
        visible = false; incomingPulse.setRinging(false); main.removeCallbacks(clock); main.removeCallbacks(telemetryReconnect);
        disconnectTelemetry();
        cancelHistory();
        if (calls != null) calls.detach(callObserver);
        if (bound) { unbindService(serviceConnection); bound = false; }
        calls = null;
        super.onStop();
    }
    @Override public void onDestroy() {
        if(alerts!=null)alerts.close();
        main.removeCallbacksAndMessages(null);
        client.dispatcher().executorService().shutdown(); super.onDestroy();
    }
    private void handleCallIntent() {
        if (calls == null || pendingCallIntent == null || !hasWindowFocus()) return;
        android.content.Intent intent = pendingCallIntent; pendingCallIntent = null;
        if(CallService.VIEW_ALERTS.equals(intent.getAction())){showCallAlerts();return;}
        if (!calls.isCurrentCall(intent.getLongExtra(CallService.EXTRA_TOKEN, -1))) return;
        if (CallService.ACTION_ANSWER.equals(intent.getAction())) microphone(2);
    }
    @Override public void onWindowFocusChanged(boolean focused) {
        super.onWindowFocusChanged(focused); if (focused) {handleCallIntent();presentIncoming();}
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
        ScrollView scroll = new ScrollView(this); homeScroll=scroll; scroll.setFillViewport(true); scroll.setBackgroundColor(Color.rgb(8,19,35));
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(20), dp(30), dp(20), dp(28)); scroll.addView(root); setContentView(scroll);
        LinearLayout heading=new LinearLayout(this);heading.setGravity(Gravity.CENTER_VERTICAL);root.addView(heading);
        LinearLayout branding=new LinearLayout(this);branding.setOrientation(LinearLayout.VERTICAL);heading.addView(branding,new LinearLayout.LayoutParams(0,-2,1));
        TextView eyebrow = text("VOICE LINK  /  4G", 11, GREEN); eyebrow.setLetterSpacing(0.16f); branding.addView(eyebrow);
        TextView title=text("语音对讲",25,INK);title.setTypeface(null,Typeface.BOLD);title.setPadding(0,dp(8),0,dp(3));branding.addView(title);
        settingsButton=button("设置",PANEL,MUTED,this::settings);heading.addView(settingsButton,new LinearLayout.LayoutParams(dp(64),dp(44)));
        TextView tagline=text("声音互联，让感知触手可及",12,MUTED);root.addView(tagline);
        connectionLabel=text("● 连接中",12,MUTED);connectionLabel.setPadding(0,dp(16),0,dp(12));root.addView(connectionLabel);
        alerts=new AlertCenter(this);LinearLayout.LayoutParams alertLayout=new LinearLayout.LayoutParams(-1,-2);alertLayout.bottomMargin=dp(12);root.addView(alerts.entry,alertLayout);
        LinearLayout card = new LinearLayout(this); card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(20),dp(17),dp(20),dp(18));
        GradientDrawable hero=new GradientDrawable(GradientDrawable.Orientation.TL_BR,new int[]{Color.rgb(19,45,66),Color.rgb(14,27,46)});hero.setCornerRadius(dp(24));hero.setStroke(dp(1),Color.rgb(34,66,87));card.setBackground(hero);
        LinearLayout.LayoutParams cardLayout = new LinearLayout.LayoutParams(-1, -2);
        root.addView(card, cardLayout);
        LinearLayout deviceRow=new LinearLayout(this);deviceRow.setGravity(Gravity.CENTER_VERTICAL);card.addView(deviceRow);
        deviceRow.addView(text("感知终端 01",14,INK),new LinearLayout.LayoutParams(0,-2,1));deviceOnline=text("● 状态待确认",11,MUTED);deviceRow.addView(deviceOnline);
        deviceLabel=text(device,11,MUTED);deviceLabel.setPadding(0,dp(4),0,0);card.addView(deviceLabel);
        powerSummary=text("电源状态待上报",11,MUTED);powerSummary.setPadding(0,dp(10),0,0);card.addView(powerSummary);
        radarVisual=new RadarVisual(this);card.addView(radarVisual,new LinearLayout.LayoutParams(-1,dp(215)));
        incomingPulse=new IncomingPulseView(this);incomingPulse.setVisibility(View.GONE);card.addView(incomingPulse,new LinearLayout.LayoutParams(-1,dp(215)));
        LinearLayout statusRow=new LinearLayout(this);statusRow.setGravity(Gravity.CENTER_VERTICAL);card.addView(statusRow);
        statusLabel=text("待机",25,INK);statusLabel.setTypeface(null,Typeface.BOLD);statusRow.addView(statusLabel,new LinearLayout.LayoutParams(0,-2,1));
        durationLabel=text("随时连接",19,GREEN);statusRow.addView(durationLabel);
        subtitleLabel=text(message,12,MUTED);subtitleLabel.setPadding(0,dp(7),0,dp(3));card.addView(subtitleLabel);
        callButton=button("呼叫设备",GREEN,Color.rgb(6,41,45),()->microphone(1));root.addView(callButton);
        incomingActions=new LinearLayout(this);root.addView(incomingActions);
        rejectButton=button("拒接",Color.rgb(105,49,63),Color.rgb(255,214,215),()->end("已拒接",true));
        answerButton=button("接听来电",GREEN,Color.rgb(6,41,45),()->microphone(2));
        for(Button action:new Button[]{rejectButton,answerButton}){LinearLayout.LayoutParams slot=new LinearLayout.LayoutParams(0,dp(56),1);slot.topMargin=dp(12);if(action==answerButton)slot.leftMargin=dp(10);incomingActions.addView(action,slot);}
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
        buildHistory(root);
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
    private boolean historyIsToday(){
        java.util.Calendar today=java.util.Calendar.getInstance();
        return today.get(java.util.Calendar.YEAR)==historyDay.get(java.util.Calendar.YEAR) && today.get(java.util.Calendar.DAY_OF_YEAR)==historyDay.get(java.util.Calendar.DAY_OF_YEAR);
    }
    private void showCallAlerts(){alerts.open();}
    private void buildHistory(LinearLayout root){
        LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(dp(14),dp(16),dp(14),dp(14));box.setBackground(background(PANEL,18));
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(16);root.addView(box,lp);
        LinearLayout heading=new LinearLayout(this);heading.setGravity(Gravity.CENTER_VERTICAL);box.addView(heading);
        TextView title=text("感知时间线",16,INK);title.setTypeface(null,Typeface.BOLD);heading.addView(title,new LinearLayout.LayoutParams(0,-2,1));
        heading.addView(text("HISTORY",10,GREEN));
        historyPeriod=text("最近 1 小时",11,MUTED);historyPeriod.setPadding(0,dp(6),0,0);box.addView(historyPeriod);
        LinearLayout filters=new LinearLayout(this);box.addView(filters);
        historyHour=button("近1小时",PANEL,INK,()->{historyHourly=true;historyDay=java.util.Calendar.getInstance();loadHistory();});
        historyToday=button("今天",PANEL,INK,()->{historyHourly=false;historyDay=java.util.Calendar.getInstance();loadHistory();});
        historyDate=button("选日期",PANEL,INK,this::chooseHistoryDate);
        for(Button b:new Button[]{historyHour,historyToday,historyDate}){b.setTextSize(12);LinearLayout.LayoutParams chip=new LinearLayout.LayoutParams(0,dp(44),1);chip.topMargin=dp(9);chip.rightMargin=dp(4);filters.addView(b,chip);}
        timeline=new PresenceTimeline(this);box.addView(timeline,new LinearLayout.LayoutParams(-1,dp(72)));
        LinearLayout legend=new LinearLayout(this);box.addView(legend);
        for(String state:new String[]{"absent","still","moving","present","unknown"}){TextView tag=text("● "+PresenceTimeline.label(state),10,state.equals("unknown")?MUTED:PresenceTimeline.color(state));legend.addView(tag,new LinearLayout.LayoutParams(0,-2,1));}
        historySummary=text("正在读取服务器记录…",11,MUTED);historySummary.setPadding(0,dp(13),0,dp(9));box.addView(historySummary);
        historySelection=text("点击色带查看对应时段",11,MUTED);box.addView(historySelection);
        historyRows=new LinearLayout(this);historyRows.setOrientation(LinearLayout.VERTICAL);box.addView(historyRows);
        TextView note=text("历史保存 30 天 · 通话或上报空档显示为无数据",10,MUTED);note.setPadding(0,dp(12),0,0);box.addView(note);
    }
    private void chooseHistoryDate(){
        DatePickerDialog dialog=new DatePickerDialog(this,(picker,y,m,d)->{
            historyDay=java.util.Calendar.getInstance();historyDay.set(y,m,d,0,0,0);historyDay.set(java.util.Calendar.MILLISECOND,0);historyHourly=false;loadHistory();
        },historyDay.get(java.util.Calendar.YEAR),historyDay.get(java.util.Calendar.MONTH),historyDay.get(java.util.Calendar.DAY_OF_MONTH));
        java.util.Calendar first=java.util.Calendar.getInstance();first.add(java.util.Calendar.DAY_OF_MONTH,-29);
        dialog.getDatePicker().setMinDate(first.getTimeInMillis());dialog.getDatePicker().setMaxDate(System.currentTimeMillis());dialog.show();
    }
    private void cancelHistory(){historyGeneration++;if(historyRequest!=null)historyRequest.cancel();historyRequest=null;}
    private void loadHistory(){
        if(!visible || timeline==null)return;
        cancelHistory();int generation=historyGeneration;historyFetchedAt=android.os.SystemClock.elapsedRealtime();
        long now=System.currentTimeMillis(),from,to;
        if(historyHourly){from=now-3600000;to=now;historyPeriod.setText("最近 1 小时 · "+new java.text.SimpleDateFormat("MM-dd",java.util.Locale.CHINA).format(new java.util.Date(now)));}
        else{java.util.Calendar start=(java.util.Calendar)historyDay.clone();start.set(java.util.Calendar.HOUR_OF_DAY,0);start.set(java.util.Calendar.MINUTE,0);start.set(java.util.Calendar.SECOND,0);start.set(java.util.Calendar.MILLISECOND,0);from=start.getTimeInMillis();start.add(java.util.Calendar.DAY_OF_MONTH,1);to=Math.min(now,start.getTimeInMillis());historyPeriod.setText(new java.text.SimpleDateFormat("yyyy-MM-dd",java.util.Locale.CHINA).format(new java.util.Date(from))+" · 全天记录");}
        historyHour.setBackground(background(historyHourly?Color.rgb(30,75,78):Color.rgb(27,47,66),12));
        historyToday.setBackground(background(!historyHourly && historyIsToday()?Color.rgb(30,75,78):Color.rgb(27,47,66),12));
        historyDate.setBackground(background(!historyHourly && !historyIsToday()?Color.rgb(30,75,78):Color.rgb(27,47,66),12));
        historySummary.setText("正在读取服务器记录…");historyRows.removeAllViews();historySelection.setText("点击色带查看对应时段");timeline.data(new PresenceTimeline.History(),null);
        historyRequest=client.newCall(new Request.Builder().url(server+"/api/devices/"+device+"/radar-history?from_ms="+from+"&to_ms="+to).build());
        historyRequest.enqueue(new Callback(){
            @Override public void onFailure(Call request,java.io.IOException error){main.post(()->historyFailed(generation));}
            @Override public void onResponse(Call request,Response response){
                try(Response close=response){if(!response.isSuccessful() || response.body()==null)throw new java.io.IOException("History unavailable");
                    PresenceTimeline.History data=PresenceTimeline.History.parse(new JSONObject(response.body().string()));
                    main.post(()->{if(!visible || generation!=historyGeneration)return;historyRequest=null;renderHistory(data);});
                }catch(Exception error){main.post(()->historyFailed(generation));}
            }
        });
    }
    private void historyFailed(int generation){if(visible && generation==historyGeneration){historyRequest=null;historySummary.setText("历史暂时无法读取，点击日期按钮重试");}}
    private String historyDetail(PresenceTimeline.Segment s){return PresenceTimeline.label(s.state)+"  ·  "+PresenceTimeline.time(s.from)+" — "+PresenceTimeline.time(s.to)+"  ·  "+PresenceTimeline.duration(s.to-s.from);}
    private void renderHistory(PresenceTimeline.History data){
        timeline.data(data,s->historySelection.setText(historyDetail(s)));historyRows.removeAllViews();
        long absent=0,still=0,moving=0,present=0;
        for(PresenceTimeline.Segment s:data.segments){long duration=s.to-s.from;switch(s.state){case "absent":absent+=duration;break;case "still":still+=duration;break;case "moving":moving+=duration;break;case "present":present+=duration;break;}}
        if(absent+still+moving+present==0)historySummary.setText(data.healthy?"这个时段暂无有效记录，历史从功能上线后开始积累":"记录保存异常，请稍后重试");
        else historySummary.setText("静止 "+PresenceTimeline.duration(still)+"  ·  活动 "+PresenceTimeline.duration(moving)+"\n无人 "+PresenceTimeline.duration(absent)+(present>0?"  ·  有人 "+PresenceTimeline.duration(present):"")+(data.healthy?"":"\n记录保存异常，可能有缺失"));
        int shown=0;
        for(int i=data.segments.size()-1;i>=0 && shown<4;i--){PresenceTimeline.Segment s=data.segments.get(i);if(s.state.equals("unknown"))continue;shown++;
            LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(0,dp(12),0,0);historyRows.addView(row);
            TextView dot=text("●",12,PresenceTimeline.color(s.state));dot.setPadding(0,0,dp(10),0);row.addView(dot);
            LinearLayout lines=new LinearLayout(this);lines.setOrientation(LinearLayout.VERTICAL);row.addView(lines,new LinearLayout.LayoutParams(0,-2,1));
            lines.addView(text(PresenceTimeline.label(s.state),13,INK));lines.addView(text(PresenceTimeline.time(s.from)+" — "+PresenceTimeline.time(s.to),10,MUTED));row.addView(text(PresenceTimeline.duration(s.to-s.from),11,MUTED));
            row.setOnClickListener(v->historySelection.setText(historyDetail(s)));
        }
        if(data.segments.size()>4){Button all=button("查看时段列表",Color.rgb(27,47,66),INK,()->{
            int count=Math.min(500,data.segments.size());String[] items=new String[count];
            for(int i=0;i<count;i++)items[i]=historyDetail(data.segments.get(data.segments.size()-1-i));
            new AlertDialog.Builder(this).setTitle("时间轨迹 · 最近 "+count+" 个时段").setItems(items,(dialog,index)->historySelection.setText(items[index])).setNegativeButton("关闭",null).show();
        });all.setTextSize(12);historyRows.addView(all);}
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
        if(alerts!=null){
            alerts.update(calls==null?null:calls.alertRows(),calls!=null && calls.alertsSynced(),calls!=null && calls.registered,device);
            boolean available=calls==null || calls.call.phase==CallState.Phase.IDLE;
            alerts.entry.setVisibility(available?View.VISIBLE:View.GONE);if(!available)alerts.close();
        }
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
        if(incoming && incomingPulse.getVisibility()!=View.VISIBLE) homeScroll.post(()->homeScroll.smoothScrollTo(0,Math.max(0,((View)incomingPulse.getParent()).getTop()-dp(10))));
        incomingPulse.setVisibility(incoming?View.VISIBLE:View.GONE);incomingPulse.setRinging(visible && incoming);radarVisual.setVisibility(incoming?View.GONE:View.VISIBLE);
        if(incoming)durationLabel.setText("等待接听");
        callButton.setVisibility(idle ? View.VISIBLE : View.GONE);
        callButton.setEnabled(registered && iceServers != null);
        callButton.setAlpha(callButton.isEnabled() ? 1f : 0.45f);
        incomingActions.setVisibility(incoming?View.VISIBLE:View.GONE);
        answerButton.setVisibility(incoming ? View.VISIBLE : View.GONE);
        rejectButton.setVisibility(incoming ? View.VISIBLE : View.GONE);
        hangupButton.setVisibility(!idle && !incoming ? View.VISIBLE : View.GONE);
        muteButton.setEnabled(!idle && !incoming); speakerButton.setEnabled(!idle && !incoming);
        audioControls.setVisibility(!idle && !incoming ? View.VISIBLE : View.GONE);
        muteButton.setText(muted ? "麦克风关" : "麦克风开"); speakerButton.setText(speaker ? "扬声器" : "听筒");
        settingsButton.setEnabled(idle); diagnostics.setText(calls == null ? "等待后台服务" : calls.history.toString());
        renderTelemetry();
        presentIncoming();
    }
    private void renderTelemetry() {
        long now=android.os.SystemClock.elapsedRealtime();
        telemetryRenderedAt=now;
        boolean active=call.phase!=CallState.Phase.IDLE, audioLive=call.phase==CallState.Phase.CONNECTED;
        boolean online=audioLive||telemetry.online(now)||telemetry.powerLive(now), radarLive=telemetry.radarLive(now);
        powerSummary.setText(telemetry.powerLabel(now,active));
        powerSummary.setTextColor(telemetry.powerLive(now)?GREEN:MUTED);
        deviceOnline.setText(online?"● 终端在线":telemetry.reportId>0?"● 状态暂未更新":"● 状态待确认");
        deviceOnline.setTextColor(online?GREEN:MUTED);
        String state=telemetry.targetState(now),target=RadarVisual.label(state);
        String senseNote=radarLive?"感知在线 · 约 "+Math.max(0,(telemetry.serverAge+telemetry.elapsed(now))/1000)+" 秒前更新":active?"通话期间暂停上报":telemetry.reportId>0?"数据已过期 · 等待更新":"等待终端上传";
        if(radarLive && state.equals("unknown"))senseNote="数据在线 · 目标状态未确认";
        radarVisual.state(state,radarLive,senseNote);
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
                    JSONObject power=envelope.optJSONObject("power");
                    if(power!=null){
                        telemetry.powerAge=envelope.optLong("power_age_ms",-1);
                        telemetry.powerReceivedMono=android.os.SystemClock.elapsedRealtime();
                        telemetry.powerSource=power.optString("source","unknown");
                        telemetry.batteryMv=power.optInt("battery_mv",-1);telemetry.batteryPercent=power.optInt("battery_percent",-1);
                        telemetry.externalPresent=power.optInt("external_present",-1);telemetry.charging=power.optInt("charging",-1);
                    }
                    JSONObject data=envelope.optJSONObject("radar");if(data==null){renderTelemetry();return;}
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
    private android.app.NotificationChannel incomingChannel(){
        return Build.VERSION.SDK_INT>=26?getSystemService(android.app.NotificationManager.class).getNotificationChannel(CallService.CALL_CHANNEL):null;
    }
    private void refreshPermissionHints(){
        if(permissionHint==null && permissionRows==null)return;
        android.app.NotificationManager nm=getSystemService(android.app.NotificationManager.class);
        android.app.NotificationChannel ch=Build.VERSION.SDK_INT>=26?incomingChannel():null;
        boolean notifications=nm.areNotificationsEnabled();
        boolean channelMuted=Build.VERSION.SDK_INT>=26 && ch!=null && ch.getImportance()<android.app.NotificationManager.IMPORTANCE_HIGH;
        boolean channelHidden=Build.VERSION.SDK_INT>=26 && ch!=null && ch.getLockscreenVisibility()==android.app.Notification.VISIBILITY_SECRET;
        boolean fullscreen=Build.VERSION.SDK_INT<34 || nm.canUseFullScreenIntent();
        int lockNotifications=-1;
        try{lockNotifications=android.provider.Settings.Secure.getInt(getContentResolver(),"lock_screen_show_notifications",-1);}catch(SecurityException unavailable){/* Some manufacturers hide this setting. */}
        boolean overlay=android.provider.Settings.canDrawOverlays(this);
        boolean mic=checkSelfPermission(Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED;
        boolean battery=getSystemService(android.os.PowerManager.class).isIgnoringBatteryOptimizations(getPackageName());
        java.util.List<String> missing=new java.util.ArrayList<>();
        if(!notifications)missing.add("来电通知");else if(channelMuted || channelHidden)missing.add("设备来电通知类别");
        if(lockNotifications==0)missing.add("锁屏显示通知");
        if(!fullscreen)missing.add("锁屏全屏来电");if(!overlay)missing.add("后台弹窗");if(!mic)missing.add("麦克风");
        if(permissionHint!=null){
            boolean ok=missing.isEmpty();permissionHint.setText(ok?"可检测的来电权限已开启  ›":"来电权限待设置  ›\n"+android.text.TextUtils.join("、",missing));
            permissionHint.setTextColor(ok?0xff176757:0xff754600);permissionHint.setBackground(background(ok?0xffe0f4eb:0xffffeed2,12));
        }
        if(permissionRows!=null){
            permissionRows.setNotifyOnChange(false);permissionRows.clear();permissionRows.addAll(
                "来电通知 · "+(!notifications?"未开启，收不到来电通知":channelHidden?"锁屏通知已隐藏，去设置":channelMuted?"提醒级别过低，去设置":"已开启"),
                "锁屏全屏来电 · "+(Build.VERSION.SDK_INT<34?"本系统无需单独授权":fullscreen?"已开启":"未开启，锁屏可能不弹出"),
                "后台弹窗 · "+(overlay?"已开启":"未开启，使用其他 App 时可能只显示通知"),
                "麦克风 · "+(mic?"已允许":"未允许，接听后无法讲话"),
                "电池优化 · "+(battery?"已解除限制":"后台等待不稳定时可检查"),
                "厂商权限 · 若锁屏仍无提示，检查锁屏显示、后台弹窗和自启动",
                "锁屏显示通知 · "+(lockNotifications==0?"已关闭，锁屏可能看不到来电通知":lockNotifications==1?"已开启":"请在系统设置中核对"));permissionRows.notifyDataSetChanged();
        }
    }
    @android.annotation.SuppressLint("BatteryLife")
    private void permissionSetting(int index){
        android.net.Uri pkg=android.net.Uri.parse("package:"+getPackageName());
        android.content.Intent dest=new android.content.Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,pkg);
        switch(index){
            case 0:
                if(Build.VERSION.SDK_INT>=26){
                    android.app.NotificationManager nm=getSystemService(android.app.NotificationManager.class);
                    if(nm.areNotificationsEnabled() && incomingChannel()!=null)dest=new android.content.Intent(android.provider.Settings.ACTION_CHANNEL_NOTIFICATION_SETTINGS).putExtra(android.provider.Settings.EXTRA_CHANNEL_ID,CallService.CALL_CHANNEL);
                    else dest=new android.content.Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS);
                    dest.putExtra(android.provider.Settings.EXTRA_APP_PACKAGE,getPackageName());
                }break;
            case 1: if(Build.VERSION.SDK_INT>=34)dest=new android.content.Intent(android.provider.Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT,pkg);else {Toast.makeText(this,"此版本没有独立的全屏来电开关。若仍无提示，请检查来电通知和厂商权限。",Toast.LENGTH_LONG).show();return;}break;
            case 2: dest=new android.content.Intent(android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION,pkg);break;
            case 3: Toast.makeText(this,"在应用权限中选择麦克风",Toast.LENGTH_SHORT).show();break;
            case 4: if(!getSystemService(android.os.PowerManager.class).isIgnoringBatteryOptimizations(getPackageName()))dest=new android.content.Intent(android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,pkg);break;
            case 5: Toast.makeText(this,"如有锁屏显示、后台弹出界面或自启动开关，请在系统内核对",Toast.LENGTH_LONG).show();break;
            case 6: dest=new android.content.Intent("android.settings.NOTIFICATION_SETTINGS");
                Toast.makeText(this,"请在系统通知设置中查看锁屏通知",Toast.LENGTH_LONG).show();break;
            default: return;
        }
        openSystemSetting(dest);
    }
    private void backgroundSettings(){
        if(permissionRows!=null)return;
        permissionRows=new android.widget.ArrayAdapter<>(this,android.R.layout.simple_list_item_1);
        refreshPermissionHints();
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("来电权限检查").setAdapter(permissionRows,null).setNegativeButton("完成",null).create();
        dialog.setOnDismissListener(d->{permissionRows=null;refreshPermissionHints();});dialog.show();
        dialog.getListView().setOnItemClickListener((parent,view,index,id)->permissionSetting(index));
    }
    private void openSystemSetting(android.content.Intent intent) {
        try { startActivity(intent); }
        catch (android.content.ActivityNotFoundException | SecurityException error) {
            startActivity(new android.content.Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                    .setData(android.net.Uri.parse("package:" + getPackageName())));
        }
    }
    private void settings() {
        LinearLayout form = new LinearLayout(this); form.setOrientation(LinearLayout.VERTICAL); form.setPadding(dp(24), dp(8), dp(24), 0);
        permissionHint=text("",15,Color.DKGRAY);permissionHint.setPadding(dp(12),dp(9),dp(12),dp(9));permissionHint.setMinimumHeight(dp(48));permissionHint.setGravity(Gravity.CENTER_VERTICAL);permissionHint.setFocusable(true);permissionHint.setOnClickListener(v->backgroundSettings());
        LinearLayout.LayoutParams hintPosition=new LinearLayout.LayoutParams(-1,-2);hintPosition.bottomMargin=dp(8);form.addView(permissionHint,hintPosition);refreshPermissionHints();
        ScrollView settingsScroll=new ScrollView(this);settingsScroll.addView(form);
        EditText serverInput = new EditText(this); serverInput.setSingleLine(true); serverInput.setText(server); form.addView(text("服务地址（HTTPS）", 14, Color.DKGRAY)); form.addView(serverInput);
        EditText deviceInput = new EditText(this); deviceInput.setSingleLine(true); deviceInput.setText(device); form.addView(text("ESP32 设备 ID", 14, Color.DKGRAY)); form.addView(deviceInput);
        EditText localInput = new EditText(this); localInput.setSingleLine(true); localInput.setText(localId); form.addView(text("接听组 ID（同组手机填相同值）", 14, Color.DKGRAY)); form.addView(localInput);
        EditText nameInput=new EditText(this);nameInput.setSingleLine(true);nameInput.setText(CallService.phoneName(preferences));
        form.addView(text("本机名称（接听时显示给其他手机）",14,Color.DKGRAY));form.addView(nameInput);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("连接设置").setView(settingsScroll).setNeutralButton("来电权限",null).setNegativeButton("取消", null).setPositiveButton("保存并连接", null).create();
        dialog.setOnDismissListener(d->permissionHint=null);
        dialog.setOnShowListener(ignored -> {dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(v->backgroundSettings());dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            try {
                String next = serverInput.getText().toString().trim().replaceAll("/+$", ""); URI uri = URI.create(next);
                String nextDevice = deviceInput.getText().toString().trim(), nextLocal = localInput.getText().toString().trim();
                String nextName=nameInput.getText().toString().trim();
                if(nextName.isEmpty() || nextName.length()>40 || nextName.matches("(?s).*\\p{Cntrl}.*"))throw new IllegalArgumentException("请填写 1 至 40 个字符的本机名称");
                if (!"https".equals(uri.getScheme()) || uri.getHost() == null || uri.getUserInfo() != null || uri.getQuery() != null
                        || uri.getFragment() != null || !uri.getPath().isEmpty()) throw new IllegalArgumentException("请填写 HTTPS 域名地址");
                if (!nextDevice.matches("[A-Za-z0-9_-]{1,63}") || !nextLocal.matches("[A-Za-z0-9_-]{1,63}")) throw new IllegalArgumentException("ID 仅支持字母、数字、下划线和短横线");
                disconnectTelemetry(); cancelHistory(); server = next; device = nextDevice; localId = nextLocal;
                telemetry=new TelemetryState();lastRadarUptime=0;breathTrend.clear();heartTrend.clear();
                preferences.edit().putString("server", server).putString("device", device).putString("local", localId).putString("phone_name",nextName).apply();
                if (calls != null) calls.reloadSettings();
                timeline.data(new PresenceTimeline.History(),null);historyRows.removeAllViews();historySelection.setText("");
                dialog.dismiss(); connectTelemetry(); loadHistory();
            } catch (Exception error) { Toast.makeText(this, error.getMessage(), Toast.LENGTH_LONG).show(); }
        });}); dialog.show();
    }
}
