package com.youkong.voiceintercom;

import android.app.Activity;
import android.app.Dialog;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.content.res.ColorStateList;
import android.view.*;
import android.widget.*;
import android.text.TextUtils;
import org.json.JSONArray;
import org.json.JSONObject;
import java.text.SimpleDateFormat;
import java.util.*;

/** Device-originated calls, timestamped by the signaling server. No inference about who answered. */
final class AlertCenter {
    private static final int NIGHT=0xff091524, PANEL=0xff13253a, LINE=0xff2a3e50, INK=0xffedf3fa,
            DIM=0xffa8bbcd, AMBER=0xffffc179, TEAL=0xff62ddc5, WARM=0xff453326;
    private static final JSONArray EMPTY=new JSONArray();
    private final Activity host;
    final LinearLayout entry;
    private final TextView preview,badge;
    private final ArrayList<Event> events=new ArrayList<>();
    private JSONArray source;
    private String device="",day="";
    private boolean ready,online;
    private int filter;
    private Dialog dialog;
    private LinearLayout body,records,filters;
    private TextView sync;
    private final SimpleDateFormat key=fmt("yyyy-MM-dd"),clock=fmt("HH:mm"),seconds=fmt("HH:mm:ss"),date=fmt("MM月dd日"),full=fmt("yyyy年MM月dd日");
    private static SimpleDateFormat fmt(String f){return new SimpleDateFormat(f,Locale.CHINA);}
    private static final class Event {final long at;final String device;Event(long t,String d){at=t;device=d;}}
    AlertCenter(Activity activity){
        host=activity;entry=row();entry.setPadding(dp(14),dp(12),dp(14),dp(12));entry.setMinimumHeight(dp(70));
        entry.setBackground(new RippleDrawable(ColorStateList.valueOf(0x22ffc179),panel(0xff252a32,0xff615044,17),null));
        entry.setOnClickListener(v->open());entry.setFocusable(true);
        entry.addView(bell(38),new LinearLayout.LayoutParams(dp(38),dp(38)));
        LinearLayout labels=col();labels.setPadding(dp(12),0,dp(4),0);entry.addView(labels,weight());
        labels.addView(label("呼出预警记录",16,INK,true));preview=label("等待同步呼出预警",12,DIM,false);labels.addView(preview);
        badge=label("查看  ›",13,AMBER,true);entry.addView(badge);
    }
    private int dp(int x){return Math.round(x*host.getResources().getDisplayMetrics().density);}
    private LinearLayout row(){LinearLayout r=new LinearLayout(host);r.setGravity(Gravity.CENTER_VERTICAL);return r;}
    private LinearLayout col(){LinearLayout c=new LinearLayout(host);c.setOrientation(LinearLayout.VERTICAL);return c;}
    private LinearLayout.LayoutParams weight(){return new LinearLayout.LayoutParams(0,-2,1);}
    private TextView label(String s,int size,int color,boolean bold){TextView v=new TextView(host);v.setText(s);v.setTextSize(size);v.setTextColor(color);if(bold)v.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));return v;}
    private GradientDrawable panel(int color,int stroke,int radius){GradientDrawable g=new GradientDrawable();g.setColor(color);g.setCornerRadius(dp(radius));if(stroke!=0)g.setStroke(dp(1),stroke);return g;}
    private ImageView bell(int size){ImageView v=new ImageView(host);v.setImageResource(R.drawable.ic_call_alert);v.setBackground(panel(WARM,0,12));int p=dp(size/5);v.setPadding(p,p,p,p);v.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);return v;}
    private void add(LinearLayout parent,View v,int top){LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.topMargin=dp(top);parent.addView(v,p);}
    private String time(SimpleDateFormat format,long at){return format.format(new Date(at));}
    private String dayName(long at){String d=time(key,at);if(d.equals(day))return "今天";Calendar c=Calendar.getInstance();c.add(Calendar.DATE,-1);return d.equals(key.format(c.getTime()))?"昨天":time(date,at);}
    private int today(){int n=0;for(Event e:events)if(time(key,e.at).equals(day))n++;return n;}
    void update(JSONArray values,boolean synced,boolean connected,String selected){
        if(values==null)values=EMPTY;String now=key.format(new Date());
        if(values==source && synced==ready && online==connected && device.equals(selected) && now.equals(day))return;
        source=values;ready=synced;online=connected;device=selected;day=now;events.clear();
        for(int i=0;i<values.length();i++){JSONObject o=values.optJSONObject(i);if(o==null)continue;long t=o.optLong("at_ms");if(t>0)events.add(new Event(t,o.optString("device",device)));}
        Collections.sort(events,(a,b)->Long.compare(b.at,a.at));
        preview.setText(events.isEmpty()?(ready?"暂无设备呼出预警":online?"正在同步设备记录…":"等待同步呼出预警"):
                "最近呼出  ·  "+dayName(events.get(0).at)+" "+time(clock,events.get(0).at));
        badge.setText(today()>0?"今日 "+today()+"  ›":"查看  ›");if(dialog!=null)draw();
    }
    void close(){if(dialog!=null)dialog.dismiss();}
    void open(){
        if(dialog!=null)return;filter=0;Dialog d=new Dialog(host,android.R.style.Theme_Material_NoActionBar);dialog=d;
        d.setOnDismissListener(v->{dialog=null;body=null;records=null;filters=null;sync=null;});
        LinearLayout root=col();root.setBackgroundColor(NIGHT);LinearLayout bar=row();bar.setPadding(dp(18),0,dp(18),0);root.addView(bar,new LinearLayout.LayoutParams(-1,dp(56)));
        TextView back=label("关闭",15,INK,true);back.setGravity(Gravity.CENTER_VERTICAL);back.setMinimumHeight(dp(48));back.setMinimumWidth(dp(78));back.setOnClickListener(v->d.dismiss());back.setFocusable(true);bar.addView(back,weight());
        sync=label("",12,TEAL,true);bar.addView(sync);
        ScrollView scroll=new ScrollView(host);scroll.setFillViewport(true);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));body=col();body.setPadding(dp(20),dp(8),dp(20),dp(30));scroll.addView(body);
        d.setContentView(root);Window w=d.getWindow();if(w!=null){w.setStatusBarColor(NIGHT);w.setNavigationBarColor(NIGHT);}draw();d.show();
    }
    private void draw(){
        body.removeAllViews();sync.setText(online?(ready?"●  已同步":"●  同步中"):"○  本机记录");
        add(body,label("呼出预警",31,INK,true),0);add(body,label("设备主动呼叫时，在这里留下一条记录。",14,DIM,false),4);
        LinearLayout hero=col();hero.setPadding(dp(18),dp(17),dp(18),dp(16));GradientDrawable g=new GradientDrawable(GradientDrawable.Orientation.TL_BR,new int[]{0xff34343a,0xff1d2d3f,0xff142939});g.setCornerRadius(dp(21));g.setStroke(dp(1),0xff534a40);hero.setBackground(g);add(body,hero,18);
        LinearLayout head=row();hero.addView(head);head.addView(label("最近一次呼出",14,AMBER,true),weight());head.addView(bell(30),new LinearLayout.LayoutParams(dp(30),dp(30)));
        Event first=events.isEmpty()?null:events.get(0);TextView when=label(first==null?"— —":time(seconds,first.at),34,INK,true);when.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));when.setFontFeatureSettings("tnum");add(hero,when,3);
        add(hero,label(first==null?"暂无时间记录":time(full,first.at)+"  ·  "+new SimpleDateFormat("EEEE",Locale.CHINA).format(new Date(first.at)),12,DIM,false),1);
        View rule=new View(host);rule.setBackgroundColor(LINE);LinearLayout.LayoutParams rp=new LinearLayout.LayoutParams(-1,dp(1));rp.topMargin=dp(14);hero.addView(rule,rp);
        LinearLayout stats=row();add(hero,stats,12);stats.addView(label("今日  "+today()+" 条",14,INK,true),weight());stats.addView(label("最近记录  "+events.size()+" 条",13,DIM,false));
        LinearLayout header=row();add(body,header,23);header.addView(label("呼出时间线",19,INK,true),weight());header.addView(label("最近 100 条",11,DIM,false));
        filters=row();add(body,filters,9);records=col();add(body,records,4);drawList();
    }
    private void drawList(){
        filters.removeAllViews();records.removeAllViews();String[] choices={"全部","今天","近 7 天"};for(int i=0;i<choices.length;i++){final int index=i;FrameLayout hit=new FrameLayout(host);TextView chip=label(choices[i],13,i==filter?INK:DIM,i==filter);chip.setGravity(Gravity.CENTER);chip.setBackground(panel(i==filter?0xff30455a:PANEL,i==filter?0xff58748c:LINE,15));FrameLayout.LayoutParams cp=new FrameLayout.LayoutParams(-1,dp(32),Gravity.CENTER);hit.addView(chip,cp);hit.setOnClickListener(v->{filter=index;drawList();});hit.setFocusable(true);hit.setSelected(i==filter);LinearLayout.LayoutParams hp=new LinearLayout.LayoutParams(dp(i==2?76:62),dp(48));hp.rightMargin=dp(8);filters.addView(hit,hp);}
        Calendar start=Calendar.getInstance();start.set(Calendar.HOUR_OF_DAY,0);start.set(Calendar.MINUTE,0);start.set(Calendar.SECOND,0);start.set(Calendar.MILLISECOND,0);if(filter==2)start.add(Calendar.DATE,-6);
        String section="";LinearLayout group=null;int shown=0;
        for(Event e:events){if(filter!=0 && e.at<start.getTimeInMillis())continue;String k=time(key,e.at);if(!k.equals(section)){section=k;TextView dateLabel=label(dayName(e.at)+"  /  "+time(key,e.at),12,DIM,true);add(records,dateLabel,12);group=col();group.setPadding(dp(14),0,dp(14),0);group.setBackground(panel(PANEL,LINE,16));add(records,group,6);}else{View line=new View(host);line.setBackgroundColor(LINE);group.addView(line,new LinearLayout.LayoutParams(-1,dp(1)));}
            LinearLayout r=row();r.setPadding(0,dp(13),0,dp(13));group.addView(r);TextView ts=label(time(clock,e.at),18,INK,true);ts.setFontFeatureSettings("tnum");r.addView(ts);View dot=new View(host);dot.setBackground(panel(shown==0?AMBER:0xff70869b,0,4));LinearLayout.LayoutParams marker=new LinearLayout.LayoutParams(dp(7),dp(7));marker.leftMargin=dp(12);marker.rightMargin=dp(12);r.addView(dot,marker);
            LinearLayout lines=col();r.addView(lines,weight());lines.addView(label("4G呼叫器发起呼叫",15,INK,true));TextView sub=label("设备  "+e.device,12,DIM,false);sub.setSingleLine();sub.setEllipsize(TextUtils.TruncateAt.MIDDLE);lines.addView(sub);shown++;}
        if(shown==0){LinearLayout empty=col();empty.setGravity(Gravity.CENTER_HORIZONTAL);empty.setBackground(panel(PANEL,LINE,17));empty.setPadding(dp(14),dp(24),dp(14),dp(24));add(records,empty,10);empty.addView(bell(46),new LinearLayout.LayoutParams(dp(46),dp(46)));TextView t=label(!events.isEmpty()?"这个时段没有呼出记录":ready?"暂无设备呼出预警":online?"正在同步呼出记录":"等待同步呼出预警",17,INK,true);t.setPadding(0,dp(12),0,dp(5));empty.addView(t);TextView hint=label(!events.isEmpty()?"切换到「全部」可查看其他日期。":ready?"设备下次主动呼叫时，记录会出现在这里。":"连接服务后会自动更新。",13,DIM,false);hint.setGravity(Gravity.CENTER);empty.addView(hint);}
    }
}
