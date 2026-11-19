package com.youkong.voiceintercom;

/** One call at a time. All events are serialized on Android's main thread. */
final class CallState {
    enum Phase { IDLE, INCOMING, DIALING, CONNECTING, CONNECTED }
    Phase phase = Phase.IDLE;
    String peer = "";
    String offer;
    boolean accepted;

    boolean incoming(String from, String sdp) {
        if (from == null || from.isEmpty()) return false;
        if (phase != Phase.IDLE && !peer.equals(from)) return false;
        if (phase == Phase.DIALING || phase == Phase.CONNECTED) return false;
        if (phase == Phase.IDLE) {
            peer = from;
            phase = Phase.INCOMING;
        }
        if (sdp != null && !sdp.isEmpty()) offer = sdp;
        return true;
    }

    void dial(String to) {
        if (phase != Phase.IDLE) throw new IllegalStateException("当前已有通话");
        peer = to;
        phase = Phase.DIALING;
    }

    void accept() {
        if (phase != Phase.INCOMING) return;
        accepted = true;
        phase = Phase.CONNECTING;
    }

    boolean matches(String from) { return phase != Phase.IDLE && peer.equals(from); }
    void reset() { phase = Phase.IDLE; peer = ""; offer = null; accepted = false; }
}
