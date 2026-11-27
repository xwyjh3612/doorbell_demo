"""Publish a clear entry point that distinguishes candidates from release files."""
from pathlib import Path
import datetime,hashlib,html,json,os
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'exports'
current=Path(os.environ.get('A18_AUDIT_BOARD',str(ROOT/'power_relayout_candidate/voice_mainboard_a18_2layer.kicad_pcb'))).resolve()
current_dir=current.parent.relative_to(ROOT).as_posix()
entries=[]
for directory,stem,report,label in [
 (current_dir,current.stem,'exports/review-drc.json','当前两层工作版'),
 ('','voice_mainboard_v8_a18','exports/review-drc.json','原两层工作工程'),
 ('comparison_clean_2layer','voice_mainboard_a18_clean_2layer','review-drc.json','两层布线对照'),
 ('comparison_clean_4layer','voice_mainboard_a18_clean_4layer','exports/review-drc.json','四层供电优化对照'),
]:
    folder=ROOT/directory;file=folder/(stem+'.kicad_pcb');drc=json.loads((folder/report).read_text(encoding='utf-8'))
    assert drc['source']==file.name
    entries.append({'label':label,'directory':directory,'PCB':str(file.relative_to(ROOT)),
                    'PCB_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
                    'counts':{k:len(drc[k])for k in ['violations','unconnected_items','schematic_parity']},
                    'native_report':str((folder/report).relative_to(ROOT))})
latest=current.parent;review=json.loads((latest/'exports/review-summary.json').read_text(encoding='utf-8'))
assert review['PCB_sha256']==entries[0]['PCB_sha256']
rows=''.join('<tr><td>'+q['label']+'</td><td>'+str(q['counts']['violations'])+'</td><td>'+str(q['counts']['unconnected_items'])+'</td><td>'+str(q['counts']['schematic_parity'])+'</td></tr>'for q in entries)
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>语音对讲主板 · A18设计进展</title><style>body{background:#eef3f5;color:#203744;font:16px/1.7 "Microsoft YaHei",sans-serif;margin:0}main{max-width:980px;padding:32px;margin:auto}section{background:white;border-radius:16px;padding:24px;margin:18px 0}h1{margin:0}table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #dde5e9;text-align:left}a{color:#086b78}img{width:100%;max-height:650px;object-fit:contain;background:#121a1f}.warning{color:#78520d;background:#ffedc3;padding:14px;border-radius:9px}</style><main><p>A18外壳 · 73×73mm · 1.2mm板厚 · 电池仓避让</p><h1>语音对讲主板</h1><p class="warning">按用户选择继续两层设计，四层工程保留作对照。当前工作版尚未生产放行。</p><section><h2>当前检查结果</h2><table><tr><th>工程</th><th>DRC违规</th><th>未连接</th><th>原理图一致性</th></tr>__ROWS__</table><p>当前两层新版 ERC __ERC__。检查数字针对各自保存的工程，不能混用历史报告。</p></section><section><h2>当前两层工作版</h2><p><a href="../two_layer_work/exports/preview.html">打开正背面预览、模型仿真与机械模板</a> · <a href="../two_layer_work/voice_mainboard_a18_2layer.kicad_pcb">打开KiCad PCB</a> · <a href="../two_layer_work/设计审查记录.md">工程审查记录</a></p><img src="../two_layer_work/exports/review-front.png"><p>重新安排4G降压、串口电平转换、复位和音频区域，预留密集引脚引出与较宽电源主干。器件数量未增加。红色是KiCad铜层颜色，实际阻焊颜色可选。</p></section><section><h2>打样前审查</h2><p>布通仍需以这版原生报告为准。USB／射频参考地与阻抗、开关电源回路、电池峰值电流／热行为、L5准确料号及外壳装配空间尚需闭环。80%停充／70%恢复需要固件与电芯校准，当前未实现。</p><p>实际运行了12组被动储能与4组充电控制ngspice模型；没有整板芯片内部／电芯化学模型，不能据此代替样板上电和通话测试。</p><p><a href="design-comparison.json">下载工程版本与检查记录</a> · <a href="../README.md">工作说明</a> · <a href="../comparison_clean_4layer/exports/preview.html">查看四层历史对照</a></p></section></main></html>'''.replace('__ROWS__',rows).replace('__ERC__',str(review['ERC_violations']))
page=page.replace('../two_layer_work/voice_mainboard_a18_2layer.kicad_pcb','../'+current.relative_to(ROOT).as_posix())
page=page.replace('../two_layer_work/','../'+current_dir+'/')
if (latest/'exports/vbat-storage/results.json').is_file():
    page=page.replace('器件数量未增加。','在ML307C的VBAT处增加两颗220µF储能电容，保留原陶瓷电容。')
    page=page.replace('12组被动储能与4组充电控制ngspice模型','12组电源切换、4组充电控制及8组模组VBAT储能ngspice模型')
page=page.replace('L5准确料号','L5采购编号与备料')
(OUT/'preview.html').write_text(page,encoding='utf-8')
data={'product':'语音对讲主板','generated_at':datetime.datetime.now().astimezone().isoformat(),
      'candidates':entries,'selected_production_layer_count':2,'manufacturing_ready':False,
      'latest_review':current_dir+'/exports/preview.html','firmware_modified_for_CAD':False}
(OUT/'design-comparison.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'review-summary.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('Updated A18 preview entry point; all candidates explicitly marked unreleased.')
