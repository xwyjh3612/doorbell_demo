package com.youkong.audio_server.service;

import com.youkong.audio_server.dto.SignalingMessage;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.Test;
import static org.junit.Assert.*;

public class CallReplyRoutesTest implements CallReplyRoutes.Delivery {
    final AtomicLong now=new AtomicLong(100000), serial=new AtomicLong();
    final CallReplyRoutes routes=new CallReplyRoutes(now::get);
    final List<SignalingMessage> phones=new ArrayList<>(), devices=new ArrayList<>();
    final List<String> alerts=new ArrayList<>(); boolean online=true;
    public boolean phone(String client,SignalingMessage message){phones.add(message);return online;}
    public boolean device(String device,SignalingMessage message){devices.add(message);assertNull(message.getCallId());return true;}
    public void alert(String device,String client,String key,long at){alerts.add(client+":"+device);}
    void signal(boolean up,String device,String client,String type,String tag){
        SignalingMessage value=CallReplyRoutes.notice(type,up?device:client,up?client:device,tag,type,1000*serial.incrementAndGet());
        routes.route(up,device,client,value,this);
    }
    SignalingMessage last(List<SignalingMessage> items){return items.get(items.size()-1);}
    @Test public void twoCountiesCanDialAndSpeakIndependently(){
        signal(false,"d1","c1","offer","1");signal(true,"d2","c2","offer",null);
        String second=last(phones).getCallId();signal(true,"d1","default","answer",null);signal(false,"d2","c2","answer",second);
        assertEquals("c1",last(phones).getTarget());assertEquals("d2",last(devices).getTarget());
        signal(false,"d1","c1","bye","1");signal(true,"d2","default","candidate",null);
        assertEquals(second,last(phones).getCallId());assertEquals(Arrays.asList("c2:d2"),alerts);
    }
    @Test public void secondCallerRejectedBothBeforeAndAfterAnswer(){
        signal(false,"d","A","offer","first");signal(false,"d","B","offer","second");
        assertEquals("busy",last(phones).getData());assertEquals("second",last(phones).getCallId());
        signal(false,"d","B","bye","second");signal(false,"d","B","candidate","second");assertEquals(1,devices.size());
        signal(true,"d","default","answer",null);assertEquals("A",last(phones).getTarget());
        signal(false,"d","B","offer","third");assertEquals("busy",last(phones).getData());
        signal(true,"d","default","bye",null);assertEquals("A",last(phones).getTarget());
    }
    @Test public void busyReceiverStillGetsDeviceAlertAndOriginalSurvives(){
        signal(true,"d1","desk","offer",null);String id=last(phones).getCallId();signal(false,"d1","desk","answer",id);
        signal(true,"d2","desk","offer",null);assertEquals("reject",last(devices).getType());assertEquals("d2",last(devices).getTarget());
        signal(true,"d1","desk","candidate",null);assertEquals(id,last(phones).getCallId());assertEquals(2,alerts.size());
    }
    @Test public void ringingCancelRedialAndOldHangup(){
        signal(false,"d","c","offer","old");signal(false,"d","c","bye","old");
        signal(false,"d","c","offer","early");assertEquals("busy",last(phones).getData());now.addAndGet(2001);
        signal(false,"d","c","offer","new");int count=devices.size();signal(false,"d","c","bye","old");assertEquals(count,devices.size());
        signal(true,"d","default","answer",null);assertEquals("new",last(phones).getCallId());
    }
    @Test public void ringOfferAndMqttRedeliveryProduceOneAlert(){
        SignalingMessage ring=CallReplyRoutes.notice("ring","d","c",null,"RING",1000);
        routes.route(true,"d","c",ring,this);routes.route(true,"d","c",ring,this);
        signal(true,"d","c","offer",null);assertEquals(2,phones.size());assertEquals(1,alerts.size());
        signal(false,"d","c","reject",last(phones).getCallId());assertEquals("reject",last(devices).getType());
    }
    @Test public void crossingBeforeAnswerEndsBothAndAllowsRetry(){
        for(boolean upFirst:new boolean[]{true,false}){
            String dev=upFirst?"d1":"d2";signal(upFirst,dev,"desk","offer",upFirst?null:"id");
            signal(!upFirst,dev,"desk","offer",upFirst?"id":null);
            assertEquals("reject",last(devices).getType());assertEquals("busy",last(phones).getData());assertEquals("id",last(phones).getCallId());
        }
    }
    @Test public void disconnectTimeoutAndOfflineNeverLoseAlert(){
        online=false;signal(true,"lost","c","offer",null);assertEquals("offline",last(devices).getData());assertEquals(1,alerts.size());
        online=true;signal(false,"other","c","offer","new");now.addAndGet(76000);routes.expire(this);assertEquals("timeout",last(phones).getType());
        now.addAndGet(2001);signal(false,"other","c","offer","again");signal(true,"other","default","answer",null);
        now.addAndGet(3600000);int count=devices.size();routes.expire(this);assertEquals(count,devices.size());
        routes.disconnected("c",this);assertEquals("bye",last(devices).getType());
    }
    @Test public void twoThreadsCompetingForSameDriverOnlyOneOfferPasses() throws Exception{
        ExecutorService pool=Executors.newFixedThreadPool(2);
        try{for(int iteration=0;iteration<100;iteration++){
            String device="device"+iteration;CountDownLatch release=new CountDownLatch(1);
            Callable<Void> first=()->{release.await();signal(false,device,"A"+device,"offer","a");return null;};
            Callable<Void> second=()->{release.await();signal(false,device,"B"+device,"offer","b");return null;};
            Future<Void> one=pool.submit(first),two=pool.submit(second);release.countDown();one.get();two.get();
            assertEquals(iteration+1,devices.size());assertEquals(iteration+1,phones.size());assertEquals("busy",last(phones).getData());
        }}finally{pool.shutdownNow();}
    }
    @Test public void delayedUntaggedDeviceHangupCannotCloseNewerAnsweredCall(){
        signal(false,"d","desk","offer","new");signal(true,"d","desk","answer",null);int count=phones.size();
        routes.route(true,"d","desk",CallReplyRoutes.notice("bye","d","desk",null,null,1000),this);
        assertEquals(count,phones.size());signal(true,"d","desk","candidate",null);assertEquals("new",last(phones).getCallId());
    }
    @Test public void stalledDeliveryOnOneLineDoesNotBlockAnotherCounty() throws Exception{
        CountDownLatch blocked=new CountDownLatch(1),unblock=new CountDownLatch(1);
        CallReplyRoutes.Delivery sink=new CallReplyRoutes.Delivery(){
            public boolean phone(String id,SignalingMessage m){return true;}
            public boolean device(String id,SignalingMessage m){if("east".equals(id)){blocked.countDown();try{unblock.await();}catch(InterruptedException e){throw new AssertionError(e);}}return true;}
            public void alert(String dev,String client,String key,long at){}
        };
        ExecutorService pool=Executors.newFixedThreadPool(2);
        try{pool.submit(()->routes.route(false,"east","alice",CallReplyRoutes.notice("offer","alice","east","1","sdp",1000),sink));
            assertTrue(blocked.await(3,TimeUnit.SECONDS));
            pool.submit(()->routes.route(false,"west","bob",CallReplyRoutes.notice("offer","bob","west","2","sdp",1000),sink)).get(3,TimeUnit.SECONDS);
        }finally{unblock.countDown();pool.shutdownNow();}
    }
}
