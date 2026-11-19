package com.youkong.voiceintercom;

import org.junit.Test;
import static org.junit.Assert.*;

public class CallStateTest {
    @Test public void ringAcceptBeforeOfferDoesNotNeedSecondAnswer() {
        CallState call = new CallState();
        assertTrue(call.incoming("esp32", null));
        call.accept();
        assertTrue(call.incoming("esp32", "sdp"));
        assertTrue(call.accepted);
        assertEquals(CallState.Phase.CONNECTING, call.phase);
        assertEquals("sdp", call.offer);
    }
    @Test public void offerBeforeRingIsNotLost() {
        CallState call = new CallState();
        call.incoming("esp32", "sdp");
        call.incoming("esp32", null);
        assertEquals("sdp", call.offer);
        call.accept();
        assertTrue(call.accepted);
    }
    @Test public void OtherPeerCannotReplaceActiveCall() {
        CallState call = new CallState();
        call.incoming("esp32", "sdp");
        assertFalse(call.incoming("other", "bad"));
        assertFalse(call.matches("other"));
        assertEquals("sdp", call.offer);
    }
    @Test public void staleOfferCannotReplaceOutgoingOrConnectedCall() {
        CallState call = new CallState();
        call.dial("esp32");
        assertFalse(call.incoming("esp32", "sdp"));
        call.phase = CallState.Phase.CONNECTED;
        assertFalse(call.incoming("esp32", "sdp"));
    }
    @Test public void cleanupAllowsNextCallAndClearsAcceptance() {
        CallState call = new CallState();
        call.incoming("esp32", "sdp");
        call.accept();
        call.reset();
        assertFalse(call.accepted);
        assertNull(call.offer);
        assertFalse(call.matches("esp32"));
        call.dial("next");
        assertEquals("next", call.peer);
    }
}
