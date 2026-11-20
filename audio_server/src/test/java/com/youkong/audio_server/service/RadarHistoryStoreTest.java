package com.youkong.audio_server.service;

import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import org.junit.Test;
import org.junit.Rule;
import org.junit.rules.TemporaryFolder;
import java.nio.file.*;
import java.time.*;
import static org.junit.Assert.*;

public class RadarHistoryStoreTest {
    @Rule public TemporaryFolder temp=new TemporaryFolder();
    private final long now=Instant.parse("2026-11-20T08:00:00Z").toEpochMilli();
    private RadarHistoryStore store(Path path){return new RadarHistoryStore(path,Clock.fixed(Instant.ofEpochMilli(now),ZoneOffset.UTC));}
    private JSONObject data(int presence,int activity,long rx){JSONObject d=new JSONObject();d.put("presence",presence);d.put("activity",activity);d.put("rx_age_ms",rx);return d;}
    @Test public void recordedStatesSurviveRestartAndGapsStayUnknown() throws Exception {
        Path dir=temp.getRoot().toPath();RadarHistoryStore first=store(dir);
        long start=now-60000;
        first.record("a",data(1,1,0),start);first.record("a",data(1,1,0),start+5000);
        first.record("a",data(1,2,0),start+10000);first.record("a",data(0,2,0),start+40000);first.close();
        RadarHistoryStore restarted=store(dir);
        JSONArray segments=restarted.query("a",start,now).getJSONArray("segments");
        assertEquals(5,segments.size());
        assertEquals("still",segments.getJSONObject(0).getString("state"));assertEquals(start+10000,segments.getJSONObject(0).getLongValue("to_ms"));
        assertEquals("moving",segments.getJSONObject(1).getString("state"));assertEquals(start+22000,segments.getJSONObject(1).getLongValue("to_ms"));
        assertEquals("unknown",segments.getJSONObject(2).getString("state"));assertEquals("absent",segments.getJSONObject(3).getString("state"));
        assertEquals("unknown",restarted.query("b",start,now).getJSONArray("segments").getJSONObject(0).getString("state"));restarted.close();
    }
    @Test public void staleDataAndActivityZeroDoNotBecomeAbsence() {
        assertEquals("unknown",RadarHistoryStore.event(data(-1,0,0),now).getString("state"));
        assertEquals("unknown",RadarHistoryStore.event(data(0,0,12000),now).getString("state"));
        assertEquals("present",RadarHistoryStore.event(data(1,0,0),now).getString("state"));
        assertEquals(now+2000,RadarHistoryStore.event(data(1,2,10000),now).getLongValue("until_ms"));
    }
    @Test public void midnightLookbackAndPartialRecordAreHandled() throws Exception {
        Path dir=temp.getRoot().toPath();RadarHistoryStore s=store(dir);long midnight=Instant.parse("2026-11-20T00:00:00Z").toEpochMilli();
        s.append("a",RadarHistoryStore.event(data(1,1,0),midnight-5000));
        Files.write(dir.resolve("a/2026-11-19.jsonl"),"{broken\n".getBytes("UTF-8"),StandardOpenOption.APPEND);
        JSONArray segments=s.query("a",midnight,midnight+20000).getJSONArray("segments");
        assertEquals("still",segments.getJSONObject(0).getString("state"));assertEquals(midnight,segments.getJSONObject(0).getLongValue("from_ms"));
        assertEquals(midnight+7000,segments.getJSONObject(0).getLongValue("to_ms"));assertEquals("unknown",segments.getJSONObject(1).getString("state"));s.close();
    }
    @Test public void retentionDeletesOnlyOwnedOldDailyFiles() throws Exception {
        Path dir=temp.getRoot().toPath();Files.createDirectories(dir.resolve("a"));Files.write(dir.resolve("a/2026-10-19.jsonl"),new byte[0]);Files.write(dir.resolve("a/keep.txt"),new byte[0]);
        RadarHistoryStore s=store(dir);s.append("a",RadarHistoryStore.event(data(0,0,0),now));
        assertFalse(Files.exists(dir.resolve("a/2026-10-19.jsonl")));assertTrue(Files.exists(dir.resolve("a/keep.txt")));s.close();
    }
    @Test public void invalidDeviceAndOversizedRangeAreRejected() throws Exception {
        RadarHistoryStore s=store(temp.getRoot().toPath());
        try{s.query("../a",now-1000,now);fail();}catch(IllegalArgumentException expected){}
        try{s.query("a",now-27*3600000,now);fail();}catch(IllegalArgumentException expected){}s.close();
    }
}
