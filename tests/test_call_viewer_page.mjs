// Execute the shipped page's JS with a small DOM harness. This checks data
// rendering, filters and timer behavior without opening the user's browser.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';

class Element {
  constructor(tag='div') { this.tagName=tag;this.children=[];this.value='';this.textContent='';this.dataset={};this.checked=false;this.hidden=false;this.classList={add(){}};this.scrollHeight=0;this.scrollTop=0;this.clientHeight=0; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children=items; }
  setAttribute(name,value) { this[name]=value; }
  get options() { return this.children; }
}
const elements=new Map();
const element=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
for(const id of ['filter','call-filter'])element(id).value='all';
element('source').value='live';
const document={getElementById:element,createElement:tag=>new Element(tag),createDocumentFragment:()=>new Element('fragment'),
  querySelector:()=>null};
const record={attempt:82,round:15,direction:'device-calls-app',status:'connected',active:true,fresh:true,
  started_at:'2026-11-26T07:27:33Z',connected_at:'2026-11-26T15:27:41',duration_seconds:600,
  last_audio_at:'2026-11-26T15:37:39',reason:'正在观察双向音频',bidirectional_samples:300,afe_alerts:0};
const data={batch:'formal40',batches:[{id:'formal40'}],target_rounds:40,target_seconds:1800,
  server_time:'2026-11-26T07:37:41Z',updated_at:'2026-11-26T07:37:40Z',phase:'calling',active:record,
  summary:{completed:14,passed:10,failed:4,excluded:3,setup_failed:64},records:[record,
    {...record,attempt:79,round:14,active:false,status:'failed',duration_seconds:1400,error:'AFE overflow',evidence:['<script>unsafe()</script>'],reason:'已观察到AFE音频缓冲溢出'},
    {...record,attempt:78,round:13,active:false,status:'passed',duration_seconds:1800,reason:'通过'},
    {...record,attempt:80,round:null,active:false,status:'excluded',excluded:true,reason:'电脑中断'},
    {...record,attempt:81,round:null,active:false,status:'setup-failed',connected_at:null,reason:'未接通'}]};
let elapsed=0,failCalls=false;
const intervals=[];
const context=vm.createContext({document,Intl,Date,Number,String,Object,JSON,Math,Set,performance:{now:()=>elapsed},
  requestAnimationFrame:callback=>callback(),setTimeout(){},setInterval:callback=>intervals.push(callback),
  AbortSignal:{timeout(){}},navigator:{clipboard:{writeText:async()=>{}}},
  fetch:async url=>({ok:!failCalls||!url.startsWith('/api/calls'),json:async()=>url.startsWith('/api/calls')?data:
    url.startsWith('/api/sources')?{sources:[]}:{reset:true,epoch:1,last_id:0,lines:[],bytes:0,selection:'live',note:'等待日志'}})});
const page=await fs.readFile(new URL('../examples/serial_log_viewer/index.html',import.meta.url),'utf8');
vm.runInContext(page.match(/<script>([\s\S]*?)<\/script>/)[1],context);
const settle=async()=>{for(let i=0;i<10;i++)await Promise.resolve();};
await settle();
assert.equal(element('calls-completed').textContent,'14 / 40');
assert.equal(element('calls-failed').textContent,4);
assert.match(element('live-title').textContent,/第15轮.*通话中/);
assert.equal(element('live-timer').textContent,'10分00秒');
assert.match(element('live-connected').textContent,/15:27:41/);
elapsed=6000;
intervals.at(-1)();
assert.equal(element('live-timer').textContent,'10分06秒');
element('call-filter').value='failed';element('call-filter').onchange();
assert.match(element('call-count').textContent,/显示 1 条/);
element('call-filter').value='all';element('call-search').value='AFE';element('call-search').oninput();
assert.match(element('call-count').textContent,/显示 1 条/);
const allText=node=>String(node.textContent)+node.children.map(allText).join('');
assert.match(allText(element('call-rows')),/<script>unsafe\(\)<\/script>/); // Plain text, no innerHTML.
element('logs-tab').onclick();assert.equal(element('calls-panel').hidden,true);assert.equal(element('logs-panel').hidden,false);
element('calls-tab').onclick();assert.equal(element('calls-panel').hidden,false);
failCalls=true;element('calls-refresh').onclick();await settle();
assert.match(element('calls-error').textContent,/计时暂停/);
assert.equal(element('live-timer').textContent,'10分00秒');
assert.match(element('live-title').textContent,/状态待确认/);
console.log('PASS: page JS rendering, Beijing timestamps, timer, failure filter, search, tabs and disconnected-service state');
