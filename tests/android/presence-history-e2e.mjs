// Isolated demo IDs; exercises MQTT -> durable history -> native Android views.
// Optional VOICE_HISTORY_SERVER / VOICE_HISTORY_PROJECT support a local backend.
import { execFile } from 'node:child_process';
import fs from 'node:fs/promises';
import { MqttProbe } from './mqtt-probe.mjs';
const server=process.env.VOICE_HISTORY_SERVER || 'https://voice.2811.top';
const project=process.env.VOICE_HISTORY_PROJECT || 'project';
const device=process.env.VOICE_TEST_DEVICE || 'demo_history_20261120';
const output=process.env.VOICE_TEST_OUTPUT || 'build/app05-history-visual';
if(!device.startsWith('demo_'))throw Error('Only isolated demo_ devices are permitted');
const native=process.env.VOICE_HISTORY_NATIVE==='1';
const adb=(...args)=>new Promise((resolve,reject)=>execFile(process.env.VOICE_TEST_ADB || 'adb', ['-s',process.env.VOICE_TEST_SERIAL || '127.0.0.1:5561',...args],{encoding:'utf8',timeout:15000},(e,v)=>e?reject(e):resolve(v)));
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
await fs.mkdir(output,{recursive:true});
const mqtt=new MqttProbe('118.31.113.169',device,()=>{});await mqtt.ready;
const report=(presence,activity)=>({schema:1,device,radar:'r60abd1',uptime_ms:500000,rx_age_ms:0,motion_age_ms:0,breath_age_ms:0,heart_age_ms:0,distance_age_ms:0,valid_frames:100,uart_errors:0,presence,activity,motion:activity===2?45:0,breath:16,heart:76,distance_cm:80,bed:-1,sleep_raw:-1});
const publish=data=>mqtt.write(0x30,Buffer.concat([mqtt.field(`/voice/${project}/${device}/telemetry`),Buffer.from(JSON.stringify(data))]));
const query=async()=>{const r=await fetch(`${server}/api/devices/${device}/radar-history?from_ms=${Date.now()-3600000}&to_ms=${Date.now()}`);if(!r.ok)throw Error('History HTTP '+r.status);return r.json();};
const packageName='com.youkong.voiceintercom';
let prefs=null;
const results=[];
const ui=async()=>{await adb('shell','uiautomator','dump','/sdcard/history-ui.xml');return adb('shell','cat','/sdcard/history-ui.xml');};
const clickText=async label=>{
    const xml=await ui();const match=xml.match(new RegExp('<node[^>]*text="'+label+'"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"'));
    if(!match)throw Error('Missing control '+label);const [x1,y1,x2,y2]=match.slice(1).map(Number);
    await adb('shell','input','tap',String(Math.round((x1+x2)/2)),String(Math.round((y1+y2)/2)));
};
const screenshot=async name=>{await adb('shell','screencap','-p','/sdcard/history-visual.png');await adb('pull','/sdcard/history-visual.png',`${output}/${name}.png`);};
try {
    if(native){
        prefs=await adb('shell','run-as',packageName,'cat','shared_prefs/intercom.xml').catch(()=>null);
        await adb('shell','am','force-stop',packageName);
        await fs.writeFile(`${output}/prefs.xml`,`<?xml version="1.0" encoding="utf-8"?><map><string name="server">${server}</string><string name="device">${device}</string><string name="local">demo_history_app</string></map>`);
        await adb('push',`${output}/prefs.xml`,'/data/local/tmp/history-prefs.xml');await adb('shell','run-as',packageName,'mkdir','-p','shared_prefs');await adb('shell','run-as',packageName,'cp','/data/local/tmp/history-prefs.xml','shared_prefs/intercom.xml');
        await adb('shell','am','start','-n',`${packageName}/.MainActivity`);await pause(1000);
    }
    for(const [presence,activity,state,label] of [[0,0,'absent','无人'],[1,1,'still','静止'],[1,2,'moving','活动']]){
        publish(report(presence,activity));await pause(1200);
        const history=await query();if(!history.storage_ok || !history.segments.some(s=>s.state===state))throw Error('Missing persisted '+state);
        if(native){const xml=await ui();if(!xml.includes(`空间感知：${label}`))throw Error('Native hero missing '+label);await screenshot(state);}
        results.push({state,persisted:true,native});await pause(1000);
    }
    const invalid=report(1,2);invalid.device='demo_other';publish(invalid);await pause(14000);
    const history=await query();if(history.segments.at(-1)?.state!=='unknown')throw Error('Missing stale-data gap');
    for(const state of ['absent','still','moving'])if(!history.segments.some(s=>s.state===state))throw Error('Earlier history lost '+state);
    if(native){
        await adb('shell','input','swipe','250','750','250','250','400');await pause(18000);
        const xml=await ui();if(!xml.includes('感知时间线') || !xml.includes('静止 ') || !xml.includes('活动 '))throw Error('Native history did not load');
        await fs.writeFile(`${output}/timeline-ui.xml`,xml);await screenshot('timeline');
        const chart=xml.match(/<node[^>]*content-desc="感知时间线，共 [^"]*"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"/);
        if(!chart)throw Error('Timeline cannot be selected');const [x1,y1,x2,y2]=chart.slice(1).map(Number);
        await adb('shell','input','tap',String(Math.round(x1+(x2-x1)*0.5)),String(Math.round((y1+y2)/2)));
        if(!(await ui()).includes('无数据  ·'))throw Error('Tapped history segment was not inspected');
        await clickText('今天');await pause(1200);if(!(await ui()).includes('全天记录'))throw Error('Today history filter failed');
        await clickText('选日期');await pause(300);
        const yesterday=new Date();yesterday.setDate(yesterday.getDate()-1);await clickText(String(yesterday.getDate()));
        const picker=await ui();await clickText(picker.includes('text="OK"')?'OK':'确定');await pause(1200);
        const past=await ui();if(!past.includes('这个时段暂无有效记录'))throw Error('Past-day empty history not displayed');
        await screenshot('past-day');results.push({dateBrowsing:true,segmentInspection:true});
    }
    results.push({state:'unknown-gap',persisted:true});
    const bad=await fetch(`${server}/api/devices/${device}/radar-history?from_ms=${Date.now()-48*3600000}&to_ms=${Date.now()}`);if(bad.status!==400)throw Error('Range bound not enforced');
    await fs.writeFile(`${output}/results.json`,JSON.stringify({results,history},null,2));console.log('PASS history and visual states',JSON.stringify(results));
}finally{
    mqtt.close();
    if(native){await adb('shell','am','force-stop',packageName);
        if(prefs!==null){await fs.writeFile(`${output}/original-prefs.xml`,prefs);await adb('push',`${output}/original-prefs.xml`,'/data/local/tmp/history-original.xml');await adb('shell','run-as',packageName,'cp','/data/local/tmp/history-original.xml','shared_prefs/intercom.xml');}
        else await adb('shell','run-as',packageName,'rm','-f','shared_prefs/intercom.xml');}
}
