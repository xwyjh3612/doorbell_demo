package com.youkong.voiceintercom;

/** Ages use Android's monotonic clock; zero, unknown and expired are distinct. */
final class TelemetryState {
    String model = "";
    boolean socketOpen;
    long receivedMono, serverAge = -1, rxAge = -1, breathAge = -1, heartAge = -1, distanceAge = -1;
    int presence = -1, activity = -1, motion = -1, breath = -1, heart = -1, distance = -1;
    long reportId;
    long elapsed(long now) { return Math.max(0, now - receivedMono); }
    boolean online(long now) { return socketOpen && serverAge >= 0 && serverAge + elapsed(now) < 30000; }
    boolean radarLive(long now) { return online(now) && rxAge >= 0 && rxAge + serverAge + elapsed(now) < 12000; }
    boolean fresh(long fieldAge, long now) {
        return radarLive(now) && fieldAge >= 0 && fieldAge + serverAge + elapsed(now) < 12000;
    }
    boolean vitals() { return "r60abd1".equals(model); }
}
