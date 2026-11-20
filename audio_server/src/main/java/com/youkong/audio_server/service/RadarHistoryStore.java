package com.youkong.audio_server.service;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import javax.annotation.PreDestroy;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;

/** Bounded observation writer, isolated from call signaling. No firmware messages are added. */
@Service
public class RadarHistoryStore {
    private static final Logger LOG = LoggerFactory.getLogger(RadarHistoryStore.class);
    private static final long FRESH_MS = 12000, RETENTION_MS = 30L*86400000;
    private final Path directory;
    private final Clock clock;
    private final ThreadPoolExecutor writer = new ThreadPoolExecutor(1,1,0,TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(512), r -> { Thread t = new Thread(r,"radar-history"); t.setDaemon(true); return t; });
    private volatile boolean healthy = true;
    private LocalDate cleanedDay;

    @Autowired
    public RadarHistoryStore(@Value("${telemetry.history.directory:./data/radar-history}") String directory) {
        this(Paths.get(directory), Clock.systemUTC());
    }
    RadarHistoryStore(Path directory, Clock clock) { this.directory = directory; this.clock = clock; }
    public void record(String device, JSONObject data, long at) {
        JSONObject event = event(data, at);
        try { writer.execute(() -> {
            try { append(device, event); healthy = true; }
            catch (IOException e) { if (healthy) LOG.error("Radar history write failed",e); healthy = false; }
        }); } catch (RejectedExecutionException e) {
            if (healthy) LOG.warn("Radar history writer full; observation omitted"); healthy = false;
        }
    }
    static JSONObject event(JSONObject data, long at) {
        String state = "unknown";
        long rx = data.getLongValue("rx_age_ms");
        long valid = 0;
        if (rx >= 0 && rx < FRESH_MS) {
            valid = FRESH_MS-rx;
            if(data.getIntValue("presence")==0) state="absent";
            else if(data.getIntValue("activity")==2) state="moving";
            else if(data.getIntValue("activity")==1) state="still";
            else if(data.getIntValue("presence")==1) state="present";
        }
        JSONObject result = new JSONObject(); result.put("at_ms",at);
        result.put("until_ms",at+valid); result.put("state",state); return result;
    }
    // Package-visible synchronous entry point permits real disk/restart tests.
    void append(String device, JSONObject event) throws IOException {
        if(!device.matches("[A-Za-z0-9_-]{1,63}")) throw new IllegalArgumentException("Invalid device");
        LocalDate today=Instant.ofEpochMilli(clock.millis()).atZone(ZoneOffset.UTC).toLocalDate();
        if(!today.equals(cleanedDay)) { cleanup(today); cleanedDay=today; }
        Path folder=directory.resolve(device); Files.createDirectories(folder);
        String day=Instant.ofEpochMilli(event.getLongValue("at_ms")).atZone(ZoneOffset.UTC).toLocalDate().toString();
        Files.write(folder.resolve(day+".jsonl"),(event.toJSONString()+"\n").getBytes(StandardCharsets.UTF_8),StandardOpenOption.CREATE,StandardOpenOption.APPEND);
    }
    private void cleanup(LocalDate today) throws IOException {
        Files.createDirectories(directory);
        try(DirectoryStream<Path> folders=Files.newDirectoryStream(directory)) {
            for(Path folder:folders) {
                if(!Files.isDirectory(folder,LinkOption.NOFOLLOW_LINKS) || !folder.getFileName().toString().matches("[A-Za-z0-9_-]{1,63}"))continue;
                try(DirectoryStream<Path> files=Files.newDirectoryStream(folder,"*.jsonl")) {
                    for(Path file:files) {
                        String name=file.getFileName().toString();
                        if(name.matches("\\d{4}-\\d{2}-\\d{2}\\.jsonl") && LocalDate.parse(name.substring(0,10)).isBefore(today.minusDays(30))) Files.deleteIfExists(file);
                    }
                }
            }
        }
    }
    public JSONObject query(String device,long from,long to) throws IOException {
        if(!device.matches("[A-Za-z0-9_-]{1,63}") || from<0 || to<=from || to-from>26L*3600000) throw new IllegalArgumentException("Invalid history range");
        long now=clock.millis(), retained=Math.max(0,now-RETENTION_MS), end=Math.min(to,now);
        List<JSONObject> events=new ArrayList<>();
        LocalDate first=Instant.ofEpochMilli(Math.max(retained,from-FRESH_MS)).atZone(ZoneOffset.UTC).toLocalDate();
        LocalDate last=Instant.ofEpochMilli(Math.max(from,end)).atZone(ZoneOffset.UTC).toLocalDate();
        for(LocalDate day=first;!day.isAfter(last);day=day.plusDays(1)) {
            Path file=directory.resolve(device).resolve(day+".jsonl");
            if(!Files.exists(file))continue;
            try(BufferedReader reader=Files.newBufferedReader(file,StandardCharsets.UTF_8)) {
                String line;
                while((line=reader.readLine())!=null) {
                    if(line.length()>512)continue;
                    try {
                        JSONObject event=JSON.parseObject(line); long at=event.getLongValue("at_ms");
                        String state=event.getString("state");
                        if(!Arrays.asList("unknown","present","absent","still","moving").contains(state))continue;
                        if(at>=Math.max(retained,from-FRESH_MS) && at<end) events.add(event);
                        if(events.size()>100000)throw new IOException("History range exceeds capacity");
                    }catch(RuntimeException ignored) { /* A torn last record after power loss is skipped. */ }
                }
            }
        }
        events.sort(Comparator.comparingLong(e -> e.getLongValue("at_ms")));
        JSONArray segments=new JSONArray(); long cursor=from;
        for(int i=0;i<events.size();i++) {
            JSONObject event=events.get(i); long at=Math.max(from,event.getLongValue("at_ms"));
            long until=Math.min(end,Math.min(event.getLongValue("until_ms"),event.getLongValue("at_ms")+FRESH_MS));
            if(i+1<events.size())until=Math.min(until,events.get(i+1).getLongValue("at_ms"));
            if(at>cursor)add(segments,cursor,Math.min(at,end),"unknown");
            if(until>at) {add(segments,at,until,event.getString("state"));cursor=until;}
            else cursor=Math.max(cursor,at);
        }
        add(segments,cursor,end,"unknown");
        JSONObject result=new JSONObject();result.put("device",device);result.put("from_ms",from);result.put("to_ms",end);
        result.put("retained_from_ms",retained);result.put("storage_ok",healthy);result.put("segments",segments);
        return result;
    }
    private static void add(JSONArray segments,long from,long to,String state) {
        if(to<=from)return;
        if(!segments.isEmpty()) {JSONObject prev=segments.getJSONObject(segments.size()-1);
            if(state.equals(prev.getString("state")) && prev.getLongValue("to_ms")==from) {prev.put("to_ms",to);return;}}
        JSONObject item=new JSONObject();item.put("from_ms",from);item.put("to_ms",to);item.put("state",state);segments.add(item);
    }
    @PreDestroy public void close() {
        writer.shutdown();try {writer.awaitTermination(5,TimeUnit.SECONDS);}catch(InterruptedException e){Thread.currentThread().interrupt();}
    }
}
