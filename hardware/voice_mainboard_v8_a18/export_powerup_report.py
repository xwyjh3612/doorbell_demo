"""Export a reviewable report from actual simulator output, never synthetic data."""
import base64
import collections
import datetime
import hashlib
import html
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OUT=ROOT/'power_relayout_candidate/exports/powerup-simulation-20261127'
sys.path.insert(0,str(REPO/'build/cad-tools/sim-python'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
font=FontProperties(fname='C:/Windows/Fonts/msyh.ttc')
plt.rcParams.update({'font.family':font.get_name(),'font.size':10,'axes.unicode_minus':False,
                     'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'path'})
report=json.loads((OUT/'results.json').read_text(encoding='utf-8'))
board=ROOT/'power_relayout_candidate/voice_mainboard_a18_2layer.kicad_pcb'
assert hashlib.sha256(board.read_bytes()).hexdigest()==report['PCB_sha256']
records=report['cases']+report['control_cases']
bycase={q['case']:q for q in records}
assert len(bycase)==len(records),'Do not silently duplicate scenario results'
for q in records:
    assert (OUT/(q['case']+'.cir')).exists(),q['case']
    assert (OUT/(q['case']+'.log')).exists(),q['case']
    if q['ngspice_completed']:
        assert (OUT/(q['case']+'-vectors.json')).exists()
        assert q['checks'],q
        if q['status']=='PASS_IN_DECLARED_MODEL':assert all(q['checks'].values()),q

def vec(case):return json.loads((OUT/(case+'-vectors.json')).read_text())
def graph(ax,case,signals,window=None):
    q=vec(case)
    indices=[i for i,t in enumerate(q['time']) if window is None or window[0]<=t*1000<=window[1]]
    stride=max(1,len(indices)//3000)
    indices=indices[::stride]
    for sig,label,color in signals:
        ax.plot([q['time'][i]*1000 for i in indices],[q[sig][i] for i in indices],label=label,color=color,lw=1.5)
    ax.grid(alpha=.2)
    ax.set_xlabel('时间 / ms')
    ax.set_ylabel('电压 / V')
    ax.legend(loc='best',fontsize=8)
def limit(ax,v,label):ax.axhline(v,ls='--',lw=1,color='#b91c1c',label=label)
def save(fig,name):
    fig.tight_layout(pad=2)
    fig.savefig(OUT/(name+'.png'),dpi=150,facecolor='white',bbox_inches='tight')
    fig.savefig(OUT/(name+'.svg'),facecolor='white',bbox_inches='tight')
    plt.close(fig)

fig,axs=plt.subplots(2,2,figsize=(12,8))
graph(axs[0,0],'vendor_5V_modem_base0p7A',[
    ('v(SYS_5V)','系统5V','#64748b'),('v(MODEM_3V8)','模组3.8V','#2563eb'),('v(ESP_3V3)','ESP 3.3V','#0d9488')])
axs[0,0].set_title('真实上电运算：5V输入，模组负载假定0.7A')
graph(axs[0,1],'vendor_5V_base0p7A_peak2A_500us',[
    ('v(MODEM_3V8)','模组3.8V','#2563eb'),('v(ESP_3V3)','ESP 3.3V','#0d9488')],(9.8,13))
limit(axs[0,1],3.4,'模组最低工作电压3.4V')
axs[0,1].set_title('0.7A基础负载 + 假定2A、500µs脉冲')
for case,label,col in [('vendor_4p5V_2A_pulse100us','4.5V / 100µs / TI切换模型','#2563eb'),
                        ('engineering_4p5V_2A_pulse500us','4.5V / 500µs / 工程切换模型','#ea580c'),
                        ('vendor_5V_2A_pulse500us','5V / 500µs / TI切换模型','#0d9488')]:
    graph(axs[1,0],case,[('v(MODEM_3V8)',label,col)],(9.8,13))
limit(axs[1,0],3.4,'3.4V')
axs[1,0].legend(fontsize=7)
axs[1,0].set_title('输入电压及假定脉冲宽度会改变压降')
graph(axs[1,1],'engineering_unplug_peak1p3A_gap100us',[
    ('v(SYS_5V)','系统5V','#64748b'),('v(MODEM_3V8)','模组3.8V','#2563eb'),('v(ESP_3V3)','ESP 3.3V','#0d9488')],(14.8,15.8))
axs[1,1].set_title('掉外电工程边界：1.3A峰值 / 100µs间隔\n理想备用5V；没有模拟真实升压芯片')
fig.suptitle('语音对讲主板 · ngspice上电与脉冲波形\nTI模型与工程近似组合，不能代替新板实测',fontsize=14,y=1.03)
save(fig,'powerup-waveforms')

fig,axs=plt.subplots(1,2,figsize=(12,4.5))
for cell,case,col in [(3.0,'controls_cell3p0_room','#2563eb'),(3.7,'controls_cell3p7_room','#0d9488'),(4.2,'controls_cell4p2_room','#7c3aed')]:
    graph(axs[0],case,[('v(BAT_ADC2)',f'电芯电压源{cell}V',col)])
axs[0].axvline(3,color='#64748b',ls=':',lw=1)
axs[0].set_title('真实R/C分压网络：3ms打开采样，40ms读取\n时间常数6ms；电芯使用固定电压源')
graph(axs[1],'controls_cell3p7_room',[('v(CHG_CE)','充电使能CE','#2563eb')],(0,9))
q=vec('controls_cell3p7_room')
ax2=axs[1].twinx()
ax2.plot([t*1000 for t in q['time']],[x*1000 for x in q['i(V_CHARGER_MON)']],color='#ea580c',lw=1.4,label='近似充电电流')
ax2.set_ylabel('近似充电电流 / mA')
ax2.set_ylim(-5,115)
axs[1].set_xlim(0,9)
axs[1].set_title('GPIO暂停充电：实际CE拓扑 + CC/CV近似\n没有模拟化学电芯或芯片温升')
save(fig,'battery-control-waveforms')

statuses={'PASS_IN_DECLARED_MODEL':'模型内通过','FAIL_IN_DECLARED_MODEL':'模型内失败',
    'INCONCLUSIVE_SIMULATOR_ABORTED':'求解中止，未得结论',
    'INCONCLUSIVE_VENDOR_DIODE_MODE_NOT_MODELLED':'官方模型缺功能，未得结论',
    'KNOWN_LIMIT_NTC_SHORT_DISABLES_TEMP_MONITOR':'已知限制：温度短路禁用检测'}
counts=collections.Counter(q['status']for q in records)
def fnum(x):return '—'if x is None else f'{x:.3f}'
rows=[]
for q in records:
    a=q.get('assumptions',{})
    m=q.get('metrics',{})
    model='TI切换＋降压近似'if a.get('mux_model','TI_vendor')=='TI_vendor'else '工程切换＋降压近似'
    if q in report['control_cases']:model='真实R/C＋开关/充电近似'
    state='pass'if q['status'].startswith('PASS')else 'fail'if q['status'].startswith('FAIL')else 'uncertain'
    rows.append('<tr><td>'+html.escape(q['case'])+'</td><td>'+model+'</td><td class="'+state+'">'+statuses[q['status']]+
        '</td><td>'+fnum(a.get('adapter_V'))+'</td><td>'+fnum(a.get('modem_base_load_A'))+
        '</td><td>'+str(a.get('modem_pulse_width_us','—'))+'</td><td>'+fnum(m.get('modem_min_after_start_V'))+
        '</td><td>'+fnum(m.get('esp_min_after_start_V'))+'</td></tr>')

images={name:base64.b64encode((OUT/(name+'.png')).read_bytes()).decode()for name in ('powerup-waveforms','battery-control-waveforms')}
sampled=json.loads((OUT/'sampled-traces.json').read_text())
viewer_data={q['case']:q for q in sampled}
viewer_data={k:v for k,v in viewer_data.items()if 'v(MODEM_3V8)'in v}
payload=json.dumps(viewer_data,separators=(',',':')).replace('</','<\\/')
power_rows=[]
for band,r,c in [('B1',621,462),('B3',543,456),('B5',541,474),('B38',305,262),('B40',285,220),('B34',241,259)]:
    power_rows.append(f'<tr><td>{band}</td><td>{r}mA</td><td>{c}mA</td></tr>')
document='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>语音对讲主板上电仿真报告</title><style>
body{font:15px/1.75 "Microsoft YaHei",sans-serif;color:#172033;background:#f5f7fb;margin:0}main{max-width:1150px;margin:auto;padding:32px 24px}h1{font-size:28px}h2{font-size:21px;margin-top:30px}section{background:white;padding:22px;border-radius:12px;margin:18px 0}p{margin:10px 0}.note{border-left:4px solid #ca8a04;padding:12px 18px;background:#fff8e5}code{overflow-wrap:anywhere;font-size:12px}img{width:100%;height:auto}table{width:100%;border-collapse:collapse;font-size:12px}th,td{text-align:left;border-bottom:1px solid #e2e8f0;padding:9px}th{background:#eef2f8}.overflow{overflow:auto}.pass{color:#067647}.fail{color:#b42318}.uncertain{color:#9a6700}.muted{color:#64748b}select{padding:8px;max-width:100%}svg{width:100%;height:auto;background:#fff}a{color:#1d4ed8}.legend{display:flex;gap:18px;flex-wrap:wrap}</style><main>
<h1>语音对讲主板上电仿真报告</h1><p class="muted">DATE · 两层A18工作版 · 实际ngspice瞬态运算</p>
<div class="note">已实际仿真上电、负载脉冲、供电切换及电池控制网络。通过只代表所声明模型与条件；USB、ESP32/ML307内部运行、真实升压/充电芯片及化学电芯未完成整板仿真。当前没有新主板实物上电记录。</div>
<section><h2>0.7A读数对主板设计的影响</h2><p>若0.7A是在5V整板输入处测得，约为3.5W；若在模组3.8V处测得，约为2.66W。它本身不要求重画主板。测量位置、仪表带宽和峰值捕获方式尚未记录，本报告分别保留0.2A基础负载、0.7A/0.8A模组负载与短时2A脉冲测试。</p>
<p>厂家手册说明最大发射功率下可能出现2A瞬态，但没有给出脉冲宽度。本报告的20/50/100/500/2000µs均为工程扫描假设，2ms属于保守边界，不能当作已测到的真实通话波形，也不能单凭该边界失败断定电源不够。</p>
<p>相同3.8V、常温、23dBm连表发射条件下，厂家功耗表没有显示ML307C全面高于ML307R：</p><table><thead><tr><th>频段</th><th>ML307R</th><th>ML307C</th></tr></thead><tbody>POWER_ROWS</tbody></table>
<p class="muted">来源：ML307C硬件手册PDF第56–57页，ML307R手册第55–56页。连表典型值仅供比较，不能直接等同实际蜂窝网络、测试开发板或整机电流。</p></section>
<section><h2>运算结果与证据</h2><p>SUMMARY</p><p>PCB SHA256：<code>BOARD_SHA</code></p>
<p>切换芯片使用TI未改动的TPS2117 Final1.10模型；SY8089降压采用工程平均模型，使用当前板的电阻、电感、已贴装电容和铜线电阻。备用电源为理想5V，不能据此声称ETA1096、电池保护或电芯已经通过。</p>
<p>在默认MODE接VIN1的实际接法下，完整拔外电会进入二极管模式。TI模型没有实现该功能；该运算结果明确保留为“未得结论”。另列工程切换间隔扫描，使用16/50/100µs假设与理想反向阻断，仅用于储能和压降敏感性检查，不能取代官方模型。</p>
<p>外部电源限流2A；数值容差0.5%，报告保留实际峰值。铜线模型不包含地平面分布、接触电阻变化和完整热模型；MLCC有效容量与ESR、转换效率、控制时间常数均为假定值。C5未贴装，未计入储能。</p>
<div class="overflow"><table><thead><tr><th>场景</th><th>模型</th><th>结果</th><th>输入/V</th><th>模组基础/A</th><th>脉冲/µs</th><th>模组最低/V</th><th>ESP最低/V</th></tr></thead><tbody>ROWS</tbody></table></div></section>
<section><h2>实际运算波形</h2><img src="data:image/png;base64,POWER_IMAGE" alt="实际上电及脉冲波形">
<p>以下查看器使用同一运算的采样数据。短脉冲放大图与上表极值取自完整原始向量；浏览采样可能略过窄峰值，不能代替极值检查。</p><select id="case"></select><select id="window"><option value="0,45">完整上电</option><option value="9.5,13">第一次负载脉冲</option><option value="14.5,18">掉外电窗口</option><option value="27.5,30">恢复外电窗口</option></select>
<p id="case-status" class="muted"></p><svg id="plot" viewBox="0 0 1000 320" aria-label="仿真电压曲线"></svg><div class="legend"><span style="color:#64748b">系统5V</span><span style="color:#2563eb">模组3.8V</span><span style="color:#0d9488">ESP 3.3V</span><span style="color:#b91c1c">模组3.4V下限（虚线）</span></div></section>
<section><h2>电池采样与充电控制</h2><img src="data:image/png;base64,BAT_IMAGE" alt="ADC与充电使能实际运算波形">
<p>ADC电路时间常数约6ms，GPIO打开后等待约40ms可接近0.4倍电芯电压。初次12ms观察尚未稳定的问题已通过延长仿真时间澄清，没有为消除误判修改元件值。</p>
<p>实际RPROG为12k，充电设定100mA。CE、温度分压和ADC拓扑使用当前板上的R/C；通断MOS及充电CC/CV为明确的近似。3.0/3.7/4.2V、GPIO暂停、低温、高温、NTC开路均单列运算。NTC短路会禁用该类充电芯片的温度检测，保留为已知限制；化学电芯、保护动作、真实充电结束、升压与温升尚未验证。</p>
<p>80%停充/70%恢复尚未实现。本次仅做CAD/仿真与报告，没有改动ESP32官方通信协议、音频主动丢旧包策略或测试固件。</p></section>
<section><h2>复查资料</h2><p>同目录保存results.json、完整原始向量、每个场景的.cir及ngspice日志。可在项目根目录运行：</p><pre><code>build/cad-tools/kicad/bin/python.exe hardware/voice_mainboard_v8_a18/simulate_board_powerup.py
build/cad-tools/kicad/bin/python.exe hardware/voice_mainboard_v8_a18/export_powerup_report.py</code></pre>
<p>USB差分/支路整理、采购与封装确认、外壳实物核对仍需闭环。本报告不把ERC/DRC结果作为整板功能仿真，不把当前开发板长通话结果作为新主板已上电的证明。</p></section>
<script>const data=PAYLOAD;const states=STATES;const sel=document.getElementById('case');Object.keys(data).forEach(k=>{let o=document.createElement('option');o.value=k;o.textContent=k;sel.append(o)});sel.value='vendor_5V_modem_base0p7A';
function draw(){const q=data[sel.value], [a,b]=document.getElementById('window').value.split(',').map(Number),svg=document.getElementById('plot');let s='';const xx=t=>60+(t-a)/(b-a)*915,yy=v=>275-v/6*245;for(let v=0;v<=6;v++){s+=`<line x1="60" y1="${yy(v)}" x2="975" y2="${yy(v)}" stroke="#e2e8f0"/><text x="40" y="${yy(v)+5}" font-size="13">${v}V</text>`}for(let i=0;i<=5;i++){let t=a+(b-a)*i/5;s+=`<text x="${xx(t)-12}" y="305" font-size="13">${t.toFixed(1)}ms</text>`}s+=`<line x1="60" x2="975" y1="${yy(3.4)}" y2="${yy(3.4)}" stroke="#b91c1c" stroke-dasharray="5 5"/>`;for(const [sig,col]of[['v(SYS_5V)','#64748b'],['v(MODEM_3V8)','#2563eb'],['v(ESP_3V3)','#0d9488']]){let pts=q.time_ms.map((t,i)=>t>=a&&t<=b?`${xx(t).toFixed(2)},${yy(q[sig][i]).toFixed(2)}`:null).filter(Boolean).join(' ');s+=`<polyline points="${pts}" fill="none" stroke="${col}" stroke-width="2"/>`}svg.innerHTML=s;document.getElementById('case-status').textContent=states[sel.value]}sel.onchange=draw;document.getElementById('window').onchange=draw;draw();</script></main></html>'''
summary='；'.join(f'{statuses[k]} {v}项'for k,v in sorted(counts.items()))+'。合计'+str(len(records))+'项；该数量不代表整板成功率。'
replacements={'DATE':report['created_at'],'BOARD_SHA':report['PCB_sha256'],'SUMMARY':summary,
    'POWER_ROWS':''.join(power_rows),'ROWS':''.join(rows),'POWER_IMAGE':images['powerup-waveforms'],
    'BAT_IMAGE':images['battery-control-waveforms'],'PAYLOAD':payload,
    'STATES':json.dumps({q['case']:statuses[q['status']]+' / '+q['scope']for q in records if q['case']in viewer_data},ensure_ascii=False)}
for token,value in replacements.items():document=document.replace(token,value)
dest=OUT/'上电仿真报告.html'
dest.write_text(document,encoding='utf-8')
summary_record={'created_at':datetime.datetime.now().astimezone().isoformat(),'PCB_sha256':report['PCB_sha256'],
    'case_count':len(records),'status_counts':dict(counts),'full_board_function_simulated':False,'manufacturing_ready':False,
    'report':str(dest.relative_to(REPO)),'plots':['powerup-waveforms.png','battery-control-waveforms.png']}
(OUT/'report-summary.json').write_text(json.dumps(summary_record,ensure_ascii=False,indent=2),encoding='utf-8')

# Package actual logs/netlists and samples; full uncompressed vectors stay local
# and their hashes in the manifest identify the evidence used for reported minima.
files=[q for q in OUT.iterdir()if q.is_file()and not q.name.endswith('-vectors.json')and q.name!='evidence-manifest.json']
sources=[ROOT/'simulate_board_powerup.py',ROOT/'export_powerup_report.py',ROOT.parent/'voice_mainboard_v2/spice_runtime.py']
model_dir=REPO/'build/voice-mainboard-simulation-20261127/tps2117-ti'
model_files=[model_dir/'source.json',model_dir/'TPS2117_PSPICE_TRANS/TPS2117_TRANS.LIB']
manifest={'PCB_sha256':report['PCB_sha256'],'files':{},'uncompressed_raw_vectors':{}}
for f in files+sources+model_files:manifest['files'][str(f.relative_to(REPO))]=hashlib.sha256(f.read_bytes()).hexdigest()
for f in OUT.glob('*-vectors.json'):manifest['uncompressed_raw_vectors'][f.name]={'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size}
(OUT/'evidence-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
archive=ROOT/'上电仿真资料-20261127.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
    for f in files+[OUT/'evidence-manifest.json']+sources+model_files:z.write(f,str(f.relative_to(REPO)))
with zipfile.ZipFile(archive)as z:assert z.testzip()is None
print(json.dumps({'report':str(dest),'archive':str(archive),'summary':summary_record},ensure_ascii=False,indent=2))
