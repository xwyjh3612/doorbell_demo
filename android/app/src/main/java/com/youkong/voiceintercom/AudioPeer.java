package com.youkong.voiceintercom;

import android.content.Context;
import android.media.AudioAttributes;
import android.os.Handler;
import android.os.Looper;
import org.json.JSONArray;
import org.json.JSONObject;
import org.webrtc.*;
import org.webrtc.audio.JavaAudioDeviceModule;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Native audio only. No video-call signaling, camera or video renderers. */
final class AudioPeer {
    interface Listener {
        void signal(String type, String value);
        void state(String state);
        void error(String message);
    }
    private final Handler main = new Handler(Looper.getMainLooper());
    private final Listener listener;
    private final PeerConnectionFactory factory;
    private final JavaAudioDeviceModule audioModule;
    private final List<String> pendingCandidates = new ArrayList<>();
    private PeerConnection pc;
    private AudioSource source;
    private AudioTrack track;
    private boolean remoteReady;
    private boolean localSent;
    private final List<String> localCandidates = new ArrayList<>();
    private String remoteMid = "0";
    private int generation;

    AudioPeer(Context context, Listener listener) {
        this.listener = listener;
        PeerConnectionFactory.initialize(PeerConnectionFactory.InitializationOptions.builder(context)
                .createInitializationOptions());
        audioModule = JavaAudioDeviceModule.builder(context)
                .setAudioAttributes(new AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                .setUseHardwareAcousticEchoCanceler(true).setUseHardwareNoiseSuppressor(true)
                .setUseLowLatency(true).createAudioDeviceModule();
        factory = PeerConnectionFactory.builder().setAudioDeviceModule(audioModule)
                .createPeerConnectionFactory();
    }

    void start(JSONArray servers) throws Exception {
        close();
        int token = generation;
        List<PeerConnection.IceServer> ice = new ArrayList<>();
        for (int i = 0; i < servers.length(); i++) {
            JSONObject value = servers.getJSONObject(i);
            List<String> urls = new ArrayList<>();
            Object raw = value.get("urls");
            if (raw instanceof JSONArray) {
                JSONArray array = (JSONArray) raw;
                for (int j = 0; j < array.length(); j++) urls.add(array.getString(j));
            } else urls.add(raw.toString());
            ice.add(PeerConnection.IceServer.builder(urls)
                    .setUsername(value.optString("username"))
                    .setPassword(value.optString("credential")).createIceServer());
        }
        PeerConnection.RTCConfiguration config = new PeerConnection.RTCConfiguration(ice);
        config.sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN;
        pc = factory.createPeerConnection(config, new PeerConnection.Observer() {
            public void onSignalingChange(PeerConnection.SignalingState state) { }
            public void onIceConnectionChange(PeerConnection.IceConnectionState state) { }
            public void onIceConnectionReceivingChange(boolean receiving) { }
            public void onIceGatheringChange(PeerConnection.IceGatheringState state) { }
            public void onIceCandidate(IceCandidate candidate) {
                main.post(() -> {
                    if (token != generation) return;
                    if (localSent) listener.signal("candidate", candidate.sdp);
                    else localCandidates.add(candidate.sdp);
                });
            }
            public void onIceCandidatesRemoved(IceCandidate[] candidates) { }
            public void onAddStream(MediaStream stream) { }
            public void onRemoveStream(MediaStream stream) { }
            public void onDataChannel(DataChannel channel) { }
            public void onRenegotiationNeeded() { }
            public void onAddTrack(RtpReceiver receiver, MediaStream[] streams) { }
            public void onConnectionChange(PeerConnection.PeerConnectionState state) {
                main.post(() -> { if (token == generation) listener.state(state.name()); });
            }
        });
        if (pc == null) throw new IllegalStateException("创建音频连接失败");
        MediaConstraints constraints = new MediaConstraints();
        constraints.optional.add(new MediaConstraints.KeyValuePair("googEchoCancellation", "true"));
        constraints.optional.add(new MediaConstraints.KeyValuePair("googNoiseSuppression", "true"));
        source = factory.createAudioSource(constraints);
        track = factory.createAudioTrack("voice-audio", source);
        pc.addTrack(track, Collections.singletonList("voice-intercom"));
    }

    private SdpObserver observer(Runnable set, java.util.function.Consumer<SessionDescription> created) {
        int token = generation;
        return new SdpObserver() {
            public void onCreateSuccess(SessionDescription sdp) { main.post(() -> {
                if (token == generation && created != null) created.accept(sdp);
            }); }
            public void onSetSuccess() { main.post(() -> { if (token == generation && set != null) set.run(); }); }
            public void onCreateFailure(String error) { fail(error); }
            public void onSetFailure(String error) { fail(error); }
            private void fail(String error) { main.post(() -> { if (token == generation) listener.error(error); }); }
        };
    }

    void offer() { create(false); }
    private void create(boolean answer) {
        SdpObserver callback = observer(null, sdp -> pc.setLocalDescription(observer(() -> {
            listener.signal(answer ? "answer" : "offer", sdp.description);
            localSent = true;
            for (String candidate : localCandidates) listener.signal("candidate", candidate);
            localCandidates.clear();
        }, null), sdp));
        if (answer) pc.createAnswer(callback, new MediaConstraints());
        else pc.createOffer(callback, new MediaConstraints());
    }

    void remote(String sdp, boolean offer) {
        if (pc == null) return;
        remoteMid = "0";
        for (String line : sdp.split("\\r?\\n")) {
            if (line.startsWith("a=mid:")) { remoteMid = line.substring(6); break; }
        }
        pc.setRemoteDescription(observer(() -> {
            remoteReady = true;
            for (String candidate : pendingCandidates) addCandidate(candidate);
            pendingCandidates.clear();
            if (offer) create(true);
        }, null), new SessionDescription(offer ? SessionDescription.Type.OFFER : SessionDescription.Type.ANSWER, sdp));
    }

    void candidate(String value) {
        if (value == null || value.isEmpty()) return;
        if (pc == null || !remoteReady) {
            if (pendingCandidates.size() < 128) pendingCandidates.add(value);
        } else addCandidate(value);
    }
    private void addCandidate(String value) {
        if (value.startsWith("a=")) value = value.substring(2);
        if (!value.startsWith("candidate:")) value = "candidate:" + value;
        pc.addIceCandidate(new IceCandidate(remoteMid, 0, value));
    }
    void mute(boolean muted) { if (track != null) track.setEnabled(!muted); }
    void close() {
        generation++;
        remoteReady = false; localSent = false;
        pendingCandidates.clear(); localCandidates.clear();
        if (pc != null) { pc.close(); pc.dispose(); pc = null; }
        if (track != null) { track.dispose(); track = null; }
        if (source != null) { source.dispose(); source = null; }
    }
    void dispose() { close(); factory.dispose(); audioModule.release(); }
}
