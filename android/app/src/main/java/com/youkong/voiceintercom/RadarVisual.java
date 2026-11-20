package com.youkong.voiceintercom;

import android.content.Context;
import android.graphics.*;
import android.os.SystemClock;
import android.view.View;

/** Animated illustration of reported occupancy; rings do not represent radar samples. */
final class RadarVisual extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private String state = "unknown", note = "等待终端上传", label = "等待感知";
    private boolean live;
    RadarVisual(Context context) { super(context); }
    static String label(String state) {
        switch (state) {
            case "absent": return "无人";
            case "still": return "静止";
            case "moving": return "活动";
            case "present": return "有人";
            default: return "等待感知";
        }
    }
    void state(String state, boolean live, String note) {
        this.state = state; this.live = live; this.note = note; label = label(state);
        setContentDescription("空间感知：" + label + "，" + note); invalidate();
    }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        float d = getResources().getDisplayMetrics().density;
        float cx = getWidth()/2f, cy = 92*d, r = Math.min(79*d, getWidth()/2f-12*d);
        boolean moving = state.equals("moving"), occupied = moving || state.equals("still") || state.equals("present");
        int color = !live ? 0xff8299ad : moving ? 0xff75bcff : occupied ? 0xff43e2c7 : 0xff8aa7bf;
        boolean animate = android.os.Build.VERSION.SDK_INT < 26 || android.animation.ValueAnimator.areAnimatorsEnabled();
        float phase = animate ? (SystemClock.uptimeMillis()%3600)/3600f : 0.35f;
        float breath = (float)(0.5+0.5*Math.sin(phase*2*Math.PI));
        paint.setStyle(Paint.Style.FILL);
        paint.setShader(new RadialGradient(cx,cy,r,new int[]{Color.argb(occupied ? 35+(int)(breath*15) : 18,Color.red(color),Color.green(color),Color.blue(color)),Color.TRANSPARENT},null,Shader.TileMode.CLAMP));
        canvas.drawCircle(cx,cy,r,paint); paint.setShader(null);
        paint.setStyle(Paint.Style.STROKE); paint.setStrokeWidth(d);
        for(int i=1;i<=3;i++) {
            paint.setColor(Color.argb(25+i*10,Color.red(color),Color.green(color),Color.blue(color)));
            canvas.drawCircle(cx,cy,r*i/3,paint);
        }
        if(live && occupied) {
            paint.setColor(color); paint.setStrokeWidth(2*d);
            canvas.drawArc(cx-r,cy-r,cx+r,cy+r,moving ? phase*360 : 305,moving ? 60 : 38,false,paint);
            if(moving) {
                paint.setColor(Color.argb((int)(90*(1-phase)),117,188,255));
                paint.setStrokeWidth(1.5f*d); canvas.drawCircle(cx,cy,r*(0.45f+0.55f*phase),paint);
            }
        }
        paint.setColor(color); paint.setAlpha(occupied ? 255 : 100);
        paint.setStrokeWidth(2.4f*d); paint.setStrokeCap(Paint.Cap.ROUND);
        if(!occupied) paint.setPathEffect(new DashPathEffect(new float[]{4*d,4*d},0));
        float drift = moving ? (float)Math.sin(phase*2*Math.PI)*3*d : 0;
        canvas.drawCircle(cx+drift,cy-22*d,7*d,paint);
        Path body = new Path(); body.moveTo(cx-17*d+drift,cy+14*d);
        body.lineTo(cx-13*d+drift,cy-4*d); body.quadTo(cx+drift,cy-15*d,cx+13*d+drift,cy-4*d); body.lineTo(cx+17*d+drift,cy+14*d);
        canvas.drawPath(body,paint); canvas.drawLine(cx-8*d+drift,cy,cx-8*d+drift,cy+26*d,paint);
        canvas.drawLine(cx+8*d+drift,cy,cx+8*d+drift,cy+26*d,paint);
        paint.setPathEffect(null); paint.setAlpha(255); paint.setStrokeCap(Paint.Cap.BUTT);
        paint.setStyle(Paint.Style.FILL); paint.setTextAlign(Paint.Align.CENTER);
        paint.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));paint.setTextSize(23*d);paint.setColor(0xffe2edf9);
        canvas.drawText(label,cx,cy+63*d,paint);
        paint.setTypeface(Typeface.DEFAULT);paint.setTextSize(11*d);paint.setColor(0xff859cb5);
        canvas.drawText(note,cx,201*d,paint);
        if(live && occupied && animate && isShown() && getWindowVisibility()==VISIBLE) postInvalidateDelayed(moving ? 40 : 80);
    }
}
