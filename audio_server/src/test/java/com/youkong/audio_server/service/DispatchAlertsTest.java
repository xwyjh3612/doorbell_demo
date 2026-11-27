package com.youkong.audio_server.service;
import java.nio.file.Path;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import static org.junit.Assert.*;

public class DispatchAlertsTest {
    @Rule public TemporaryFolder folder=new TemporaryFolder();
    @Test public void offlineHistorySurvivesRestartDeduplicatesAndSeparatesCounties() throws Exception{
        Path path=folder.newFolder().toPath();String bindings="east=alice,west=bob";
        DispatchAlerts first=new DispatchAlerts(path.toString(),bindings);
        first.record("east","alice","100",123456);first.record("west","bob","101",123457);
        DispatchAlerts restarted=new DispatchAlerts(path.toString(),bindings);
        assertNull(restarted.record("east","alice","100",123458));
        assertEquals(123456,restarted.history("alice","east").getJSONObject(0).getLongValue("at_ms"));
        assertEquals(0,restarted.history("bob","east").size());assertEquals(1,restarted.history("bob","west").size());
    }
}
