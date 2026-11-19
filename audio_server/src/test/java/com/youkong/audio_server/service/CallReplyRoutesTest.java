package com.youkong.audio_server.service;
import org.junit.Test;
import static org.junit.Assert.*;
public class CallReplyRoutesTest {
    @Test public void legacyRepliesFollowActualCallerAndClearOnHangup(){
        CallReplyRoutes r=new CallReplyRoutes();assertEquals("default",r.reply("device","default"));
        r.begin("device","client2");assertEquals("client2",r.reply("device","default"));
        assertEquals("default",r.reply("another","default"));
        r.end("device");assertEquals("default",r.reply("device","default"));
    }
    @Test public void newerCallReplacesPreviousRoute(){CallReplyRoutes r=new CallReplyRoutes();r.begin("device","old");r.begin("device","new");assertEquals("new",r.reply("device","default"));}
}
