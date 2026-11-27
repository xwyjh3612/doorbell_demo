import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
const require=createRequire(new URL('../../../build/radar-browser-tools/package.json',import.meta.url));
const {chromium}=require('playwright');
const out=new URL('../../../build/v6-price-recheck-20261124/',import.meta.url);
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
try{
 const page=await browser.newPage();
 for(const key of process.argv.slice(2)){
  const file=new URL(encodeURIComponent(key)+'.json',out);
  try{await fs.access(file);console.log(JSON.stringify({key,cached:true}));continue;}catch{}
  const url='https://so.szlcsc.com/global.html?k='+encodeURIComponent(key);
  const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:30000});
  const html=await page.content();
  const m=html.match(/<script id="__NEXT_DATA__"[^>]*>(.*?)<\/script>/s);
  const result=m?JSON.parse(m[1]).props.pageProps.soData?.searchResult:null;
  if(!result){console.log(JSON.stringify({key,status:response?.status(),title:await page.title(),error:'Public data unavailable'}));break;}
  const records=(result.productRecordList??[]).map(({productVO:r})=>({code:r.productCode,model:r.productModel,brand:r.productGradePlateName,encapsulation:r.encapsulationModel,stock:r.stockNumber,page:'https://item.szlcsc.com/'+r.productId+'.html',tiers:(r.productPriceList??[]).map(p=>({start:p.startPurchasedNumber,end:p.endPurchasedNumber,cny:p.productPrice})),datasheets:r.fileTypeVOList,remark:r.remark,ratio:r.theRatio,attributes:r.productAttributeList??r.productAttributeVOList??null}));
  await fs.writeFile(file,JSON.stringify({date:'2026-11-24',source:url,records},null,2));
  console.log(JSON.stringify({key,count:records.length,records:records.slice(0,3).map(({datasheets,attributes,remark,...r})=>r)}));
  await page.waitForTimeout(1500);
 }
}finally{await browser.close();}
