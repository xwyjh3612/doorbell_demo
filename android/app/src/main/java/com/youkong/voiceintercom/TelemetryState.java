package com.youkong.voiceintercom;

/** Ages use Android's monotonic clock; zero, unknown and expired are distinct. */
final class TelemetryState {
    String model = "";
    boolean socketOpen;
    long receivedMono, serverAge = -1, rxAge = -1, breathAge = -1, heartAge = -1, distanceAge = -1;
    int presence = -1, activity = -1, motion = -1, breath = -1, heart = -1, distance = -1;
    long reportId;
    long powerReceivedMono, powerAge = -1;
    String powerSource = "unknown";
    int batteryMv = -1, batteryPercent = -1, externalPresent = -1, charging = -1;
    boolean powerLive(long now) {
        return socketOpen && powerAge >= 0 && powerAge + Math.max(0, now-powerReceivedMono) < 60000;
    }
    String powerLabel(long now, boolean active) {
        if (powerAge < 0) return "电源状态待上报";
        boolean live = powerLive(now);
        String source = "battery".equals(powerSource) ? "电池供电" : "external".equals(powerSource) ? "外部供电" : "供电来源待确认";
        String level = batteryPercent >= 0 ? "约 " + batteryPercent + "%" : "电量未知";
        String voltage = batteryMv >= 0 ? String.format(java.util.Locale.ROOT, " · %.2f V", batteryMv / 1000.0) : "";
        String charge = charging == 1 ? " · 充电中" : charging == 2 ? " · 已充满" : charging == 3 ? " · 充电暂停" : "";
        String age = live ? "" : active ? " · 缓存，通话后刷新" : " · 状态已过期";
        return source + " · " + level + voltage + charge + age;
    }
    long elapsed(long now) { return Math.max(0, now - receivedMono); }
    boolean online(long now) { return socketOpen && serverAge >= 0 && serverAge + elapsed(now) < 30000; }
    boolean radarLive(long now) { return online(now) && rxAge >= 0 && rxAge + serverAge + elapsed(now) < 12000; }
    boolean fresh(long fieldAge, long now) {
        return radarLive(now) && fieldAge >= 0 && fieldAge + serverAge + elapsed(now) < 12000;
    }
    boolean vitals() { return "r60abd1".equals(model); }
    String targetState(long now) {
        if (!radarLive(now)) return "unknown";
        if (presence == 0) return "absent";
        if (activity == 2) return "moving";
        if (activity == 1) return "still";
        return presence == 1 ? "present" : "unknown";
    }
}
