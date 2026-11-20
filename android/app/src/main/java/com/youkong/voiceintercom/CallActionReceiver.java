package com.youkong.voiceintercom;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Explicit, private notification actions; never launches a background UI. */
public final class CallActionReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) { CallService.notificationAction(intent); }
}
