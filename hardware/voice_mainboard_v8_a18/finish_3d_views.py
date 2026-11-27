"""Build labelled contact sheet and a gallery from native KiCad renders."""
import datetime
import hashlib
import html
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OUT=ROOT/'power_relayout_candidate/exports/3d-preview-20261127'
sys.path.insert(0,str(REPO/'build/cad-tools/sim-python'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
font=FontProperties(fname='C:/Windows/Fonts/msyh.ttc')
plt.rcParams.update({'font.family':font.get_name(),'axes.unicode_minus':False})
views=[('assembled-front.png','贴好元器件 · 正面'),('assembled-back.png','贴好元器件 · 背面'),
       ('bare-front.png','未贴元器件 · 正面'),('bare-back.png','未贴元器件 · 背面')]
manifest=json.loads((OUT/'3d-preview-manifest.json').read_text(encoding='utf-8'))
source=REPO/manifest['source_PCB']
assert hashlib.sha256(source.read_bytes()).hexdigest()==manifest['source_PCB_sha256']
fig,axs=plt.subplots(2,2,figsize=(16,13))
for ax,(filename,title)in zip(axs.flat,views):
    image=plt.imread(OUT/filename)
    assert image.shape[0]>=1300 and image.shape[1]>=1700,(filename,image.shape)
    ax.imshow(image)
    ax.set_title(title,fontsize=18,pad=10)
    ax.axis('off')
fig.suptitle('语音对讲主板 · 3D视图',fontsize=24,y=.985)
fig.text(.5,.015,'当前两层A18工程；部分器件为简化外形示意。蓝绿色为预览配色。',ha='center',fontsize=12,color='#475569')
fig.tight_layout(rect=[0,.035,1,.955],pad=1.4)
fig.savefig(OUT/'语音对讲主板-3D四视图.png',dpi=150,facecolor='white')
plt.close(fig)
cards=''.join(f'<figure><figcaption>{title}</figcaption><a href="{filename}"><img src="{filename}" alt="{title}"></a><a href="{filename}" download>下载原图</a></figure>'for filename,title in views)
page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>语音对讲主板3D视图</title>
<style>body{{font:16px/1.8 "Microsoft YaHei",sans-serif;margin:0;background:#f5f7fb;color:#172033}}main{{max-width:1400px;margin:auto;padding:28px}}h1{{font-size:28px}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}}figure{{margin:0;background:white;padding:16px;border-radius:12px}}img{{width:100%;height:auto}}figcaption{{font-size:20px;font-weight:bold}}a{{color:#1d4ed8}}code{{font-size:12px;overflow-wrap:anywhere}}@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}</style>
<main><h1>语音对讲主板 · 3D视图</h1><p>73×73mm外包尺寸 · 两层 · 1.2mm板厚 · A18电池仓避让 · 正背面元件布局</p>
<p>使用当前PCB工程由KiCad原生3D渲染；未贴元器件视图保留焊盘和安装孔。贴件视图按当前默认贴装配置显示，未选装器件不显示。4G模组、电源圆口和部分芯片使用简化外形，具体清单见<a href="3d-preview-manifest.json">模型说明</a>；图片用于看布局，不能作为装壳无碰撞的验证。蓝绿色为预览配色。</p>
<div class="grid">{cards}</div><p><a href="语音对讲主板-3D四视图.png" download>下载四视图汇总原图</a></p>
<p>PCB SHA256：<code>{manifest['source_PCB_sha256']}</code></p></main></html>'''
(OUT/'index.html').write_text(page,encoding='utf-8')
notes='''# 语音对讲主板3D视图

四张原图由当前两层PCB工程的隔离副本通过KiCad原生3D渲染生成。
贴件版：按默认贴装清单显示器件，DNP选装件不显示。
裸板版：移除所有器件3D模型，保留当前板形、焊盘及安装孔。
预览蓝绿色和银色焊盘为渲染配色，未修改生产PCB颜色或加工要求。

4G模组及电源圆口使用名义尺寸简化外形；部分芯片为通用封装或简化示意。
圆口的安装面、引脚、开孔等细节不能用示意模型核准，完整清单见3d-preview-manifest.json。
图片不代表已经通过装壳碰撞检查、电气仿真或实际新主板上电。
本次没有修改源PCB布局、走线、官方协议或固件。

打开index.html可查看全部原图；语音对讲主板-3D四视图.png便于快速查看和分享。
'''
(OUT/'README.md').write_text(notes,encoding='utf-8')
manifest['rendered_at']=datetime.datetime.now().astimezone().isoformat()
manifest['images']={filename:hashlib.sha256((OUT/filename).read_bytes()).hexdigest()for filename,_ in views}
manifest['source_unchanged']=True
(OUT/'3d-preview-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
archive=ROOT/'语音对讲主板-3D图片-20261127.zip'
names=[filename for filename,_ in views]+['语音对讲主板-3D四视图.png','index.html','README.md','3d-preview-manifest.json']
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
    for name in names:z.write(OUT/name,name)
with zipfile.ZipFile(archive)as z:assert z.testzip()is None
print(json.dumps({'gallery':str(OUT/'index.html'),'overview':str(OUT/'语音对讲主板-3D四视图.png'),'archive':str(archive),'source_unchanged':True},ensure_ascii=False,indent=2))
