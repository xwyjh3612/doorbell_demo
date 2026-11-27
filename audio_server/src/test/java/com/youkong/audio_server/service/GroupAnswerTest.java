package com.youkong.audio_server.service;

import com.youkong.audio_server.dto.SignalingMessage;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.Test;
import static org.junit.Assert.*;

public class GroupAnswerTest implements CallReplyRoutes.Delivery {
    final AtomicLong time=new AtomicLong(100000);
    final CallReplyRoutes routes=new CallReplyRoutes(time::get);
    final Map<String,List<SignalingMessage>> mail=new HashMap<>();
    final List<SignalingMessage> device=new ArrayList<>();
    public List<String> recipients(String group,String device){return Arrays.asList("a","b","c");}
    public String account(String phone){return "desk";}
    public String name(String phone){return "值班员"+phone;}
    public boolean phone(String p,SignalingMessage m){mail.computeIfAbsent(p,k->new ArrayList<>()).add(m);return true;}
    public boolean device(String d,SignalingMessage m){assertEquals("desk",m.getFrom());assertNull(m.getCallId());device.add(m);return true;}
    public void alert(String d,String g,String key,long at){}
    void send(boolean up,String p,String type,String id){routes.route(up,"unit",p,CallReplyRoutes.notice(type,null,null,id,type,time.addAndGet(1000)),this);}
    String ring(){send(true,"desk","ring",null);return last("a").getCallId();}
    SignalingMessage last(String p){List<SignalingMessage> m=mail.get(p);return m.get(m.size()-1);}

    @Test public void concurrentTapsOnlyWinnerCanSignal() throws Exception {
        ExecutorService pool=Executors.newFixedThreadPool(2);
        try{for(int i=0;i<100;i++){
            mail.clear();device.clear();String id=ring();assertEquals(id,last("b").getCallId());
            CountDownLatch go=new CountDownLatch(1);List<Future<?>> jobs=new ArrayList<>();
            for(String p:Arrays.asList("a","b"))jobs.add(pool.submit(()->{go.await();send(false,p,"claim",id);return null;}));
            go.countDown();for(Future<?> job:jobs)job.get(3,TimeUnit.SECONDS);
            String winner="claim_granted".equals(last("a").getType())?"a":"b",loser=winner.equals("a")?"b":"a";
            assertEquals("claim_granted",last(winner).getType());
            for(String p:Arrays.asList(loser,"c")){assertEquals("answered_elsewhere",last(p).getData());assertEquals(name(winner),last(p).getAnsweredBy());}
            send(true,"desk","offer",null);assertEquals("offer",last(winner).getType());assertEquals(2,mail.get(loser).size());
            for(String t:Arrays.asList("answer","candidate","reject","bye"))send(false,loser,t,id);
            routes.disconnected(loser,this);assertTrue(device.isEmpty());send(false,winner,"answer",id);send(false,winner,"answer",id);
            assertEquals(1,device.size());assertEquals("answer",device.get(0).getType());
            send(false,winner,"bye",id);time.addAndGet(3000);
        }}finally{pool.shutdownNow();}
    }
    @Test public void declineOrDisconnectOnlyRemovesThatPhone(){
        String id=ring();send(false,"a","reject",id);routes.disconnected("b",this);assertTrue(device.isEmpty());
        send(true,"desk","offer",null);assertEquals("offer",last("c").getType());send(false,"c","answer",id);
        assertEquals(1,device.size());routes.disconnected("c",this);assertEquals("bye",device.get(1).getType());
    }
    @Test public void cancelledCallCannotClaimOrCancelNextOffer(){
        String old=ring();send(true,"desk","bye",null);for(String p:mail.keySet())assertEquals("bye",last(p).getType());
        time.addAndGet(3000);send(true,"desk","offer",null);String next=last("a").getCallId();
        send(false,"a","claim",old);send(false,"b","reject",old);send(false,"c","claim",null);
        assertEquals("offer",last("b").getType());send(false,"b","claim",next);assertEquals("claim_granted",last("b").getType());
    }
    @Test public void lastDeclineTerminatesExactlyOnce(){
        String id=ring();send(false,"b","reject",id);send(false,"b","reject",id);send(false,"c","bye",id);
        assertTrue(device.isEmpty());send(false,"a","reject",id);assertEquals(1,device.size());
        assertEquals("reject",device.get(0).getType());send(false,"a","claim",id);assertEquals(1,device.size());
    }
}
