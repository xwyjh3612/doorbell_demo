package com.youkong.audio_server.dto;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;
import org.junit.Test;

import static org.junit.Assert.*;

public class SignalingMessageTest {
    private SignalingMessage parse(String payload) {
        SignalingMessage message = JSON.parseObject(payload, SignalingMessage.class);
        message.normalizeMediaFields();
        return message;
    }

    @Test
    public void browserOfferKeepsSdpAndAddsDeviceData() {
        SignalingMessage message = parse("{\"type\":\"offer\",\"target\":\"device\",\"timestamp\":1,\"sdp\":\"v=0\\r\\n\"}");
        assertTrue(message.isValid());
        JSONObject wire = JSON.parseObject(JSON.toJSONString(message));
        assertEquals("v=0\r\n", wire.getString("data"));
        assertEquals(wire.getString("data"), wire.getString("sdp"));
    }

    @Test
    public void deviceAnswerAddsBrowserSdp() {
        SignalingMessage message = parse("{\"type\":\"answer\",\"timestamp\":1,\"data\":\"v=0\\r\\n\"}");
        assertTrue(message.isValid());
        assertEquals("v=0\r\n", message.getSdp());
        assertEquals(message.getSdp(), message.getData());
    }

    @Test
    public void deviceCandidateDataBecomesBrowserCandidate() {
        SignalingMessage message = parse("{\"type\":\"candidate\",\"timestamp\":1,\"data\":\"candidate:1 1 UDP 1 192.0.2.1 9000 typ host\"}");
        assertTrue(message.isValid());
        assertEquals(message.getData(), message.getCandidate());
    }

    @Test
    public void browserCandidateRetainsDeviceCandidateField() {
        SignalingMessage message = parse("{\"type\":\"candidate\",\"target\":\"device\",\"timestamp\":1,\"candidate\":\"candidate:1\"}");
        assertTrue(message.isValid());
        assertEquals("candidate:1", message.getCandidate());
        assertEquals("candidate:1", message.getData());
    }

    @Test
    public void normalizationIsIdempotentForAlternatePage() {
        SignalingMessage message = parse("{\"type\":\"offer\",\"timestamp\":1,\"data\":\"v=0\"}");
        String wire = JSON.toJSONString(message);
        message.normalizeMediaFields();
        assertEquals(wire, JSON.toJSONString(message));
    }

    @Test
    public void nonStringMediaPayloadIsRejected() {
        assertFalse(parse("{\"type\":\"offer\",\"timestamp\":1,\"data\":{\"sdp\":\"v=0\"}}").isValid());
        assertFalse(parse("{\"type\":\"candidate\",\"timestamp\":1,\"data\":123}").isValid());
    }

    @Test
    public void emptyMediaPayloadIsRejected() {
        assertFalse(parse("{\"type\":\"answer\",\"timestamp\":1,\"data\":\"\"}").isValid());
        assertFalse(parse("{\"type\":\"candidate\",\"timestamp\":1}").isValid());
    }

    @Test
    public void customizedPayloadIsPreserved() {
        SignalingMessage message = parse("{\"type\":\"customized\",\"timestamp\":1,\"data\":{\"command\":\"RING\"}}");
        assertTrue(message.isValid());
        assertTrue(message.getData() instanceof JSONObject);
        assertNull(message.getSdp());
        assertNull(message.getCandidate());
    }

    @Test
    public void deviceStringVersionRemainsCompatible() {
        SignalingMessage message = parse("{\"type\":\"version_report\",\"version\":\"2\",\"from\":\"device\"}");
        assertTrue(message.isValid());
        assertEquals(Integer.valueOf(2), message.getVersion());
    }
}
