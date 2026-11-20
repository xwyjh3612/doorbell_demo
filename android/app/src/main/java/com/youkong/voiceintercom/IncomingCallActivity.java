package com.youkong.voiceintercom;

import android.Manifest;
import android.app.Activity;
import android.content.ComponentName;
import android.content.Intent;
import android.content.ServiceConnection;
import android.content.pm.PackageManager;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.os.IBinder;
import android.view.Gravity;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Dedicated locked-screen incoming UI, following video-call's Activity flow. */
public final class IncomingCallActivity extends Activity {
    private CallService calls;
    private boolean bound, resumed, answerRequested, handled;
    private long token;
    private final Runnable observer = this::update;
    private final ServiceConnection connection = new ServiceConnection() {
        @Override public void onServiceConnected(ComponentName name, IBinder binder) {
            calls = ((CallService.LocalBinder) binder).service(); calls.attach(observer); maybeAnswer();
        }
        @Override public void onServiceDisconnected(ComponentName name) { calls = null; finish(); }
    };
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        // Configure before drawing/binding. The home page must not temporarily
        // clear these flags while the asynchronous service binding is pending.
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
                | WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON);
        if (Build.VERSION.SDK_INT >= 27) { setShowWhenLocked(true); setTurnScreenOn(true); }
        readIntent(); buildUi();
    }
    @Override public void onNewIntent(Intent intent) { super.onNewIntent(intent); setIntent(intent); readIntent(); update(); maybeAnswer(); }
    private void readIntent() {
        token = getIntent().getLongExtra(CallService.EXTRA_TOKEN, -1);
        answerRequested = CallService.ACTION_ANSWER.equals(getIntent().getAction());
    }
    @Override public void onStart() {
        super.onStart();
        // Binding must not resurrect an old incoming call after service death.
        bound = bindService(new Intent(this, CallService.class), connection, 0);
        if (!bound) finish();
    }
    @Override public void onResume() { super.onResume(); resumed = true; maybeAnswer(); }
    @Override public void onPause() { resumed = false; super.onPause(); }
    @Override public void onStop() {
        if (calls != null) calls.detach(observer);
        if (bound) { unbindService(connection); bound = false; }
        calls = null; super.onStop();
    }
    private void update() {
        if (calls == null || handled) return;
        if (!calls.isCurrentCall(token)) { handled = true; finish(); }
        else if (calls.call.phase != CallState.Phase.INCOMING) openCall();
    }
    private void maybeAnswer() {
        if (!resumed || calls == null || !answerRequested || handled) return;
        if (!calls.isCurrentCall(token) || calls.call.phase != CallState.Phase.INCOMING) { update(); return; }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            answerRequested = false; requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 7); return;
        }
        answerRequested = false;
        // Promote to microphone service only while this Activity is resumed.
        // The SDP, early candidates, WebSocket and WebRTC remain service-owned.
        calls.accept();
        if (calls.call.phase != CallState.Phase.IDLE) openCall();
    }
    @Override public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(code, permissions, results);
        if (code == 7 && results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) {
            answerRequested = true; maybeAnswer();
        }
    }
    private void openCall() {
        if (handled) return; handled = true;
        startActivity(new Intent(this, MainActivity.class).putExtra(CallService.EXTRA_TOKEN, token)
                .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP));
        finish();
    }
    @Override public void onBackPressed() { decline(); }
    private void decline() {
        if (calls != null && calls.isCurrentCall(token)) calls.end("已拒接", true);
        handled = true; finish();
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(color);
        view.setGravity(Gravity.CENTER); return view;
    }
    private Button action(String label, int color, Runnable action) {
        Button button = new Button(this); button.setText(label); button.setTextColor(0xFFFFFFFF); button.setTextSize(19);
        GradientDrawable bg = new GradientDrawable(); bg.setColor(color); bg.setCornerRadius(dp(30)); button.setBackground(bg);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(66), 1); params.setMargins(dp(8), 0, dp(8), 0);
        button.setLayoutParams(params); button.setOnClickListener(view -> action.run()); return button;
    }
    private void buildUi() {
        getWindow().setStatusBarColor(0xFF081323); getWindow().setNavigationBarColor(0xFF081323);
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setPadding(dp(24), dp(54), dp(24), dp(44));
        root.setBackground(new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{0xFF081323, 0xFF19394C}));
        root.addView(text("VOICE LINK  /  4G", 13, 0xFF43E2C7));
        LinearLayout center = new LinearLayout(this); center.setOrientation(LinearLayout.VERTICAL); center.setGravity(Gravity.CENTER);
        root.addView(center, new LinearLayout.LayoutParams(-1, 0, 1));
        TextView icon = text("声", 52, 0xFF43E2C7); GradientDrawable circle = new GradientDrawable(); circle.setShape(GradientDrawable.OVAL);
        circle.setColor(0xFF183E4C); circle.setStroke(dp(2), 0xFF43E2C7); icon.setBackground(circle);
        center.addView(icon, new LinearLayout.LayoutParams(dp(140), dp(140)));
        TextView name = text("语音终端", 30, 0xFFE2EDF9); name.setTypeface(null, Typeface.BOLD); name.setPadding(0, dp(28), 0, dp(12)); center.addView(name);
        center.addView(text("设备来电", 19, 0xFF43E2C7));
        TextView hint = text("接听后即可与设备双向通话", 14, 0xFF859CB5); hint.setPadding(0, dp(20), 0, 0); center.addView(hint);
        LinearLayout actions = new LinearLayout(this); root.addView(actions, new LinearLayout.LayoutParams(-1, -2));
        actions.addView(action("拒接", 0xFF9B4252, this::decline));
        actions.addView(action("接听来电", 0xFF218F7D, () -> { answerRequested = true; maybeAnswer(); }));
        setContentView(root);
    }
}
