"""Read public product metadata for BOM verification; no account/order actions."""
from pathlib import Path
import sys,json,concurrent.futures
import requests
from bs4 import BeautifulSoup
def read(i):
    url='https://item.szlcsc.com/'+i+'.html'
    response=requests.get(url,timeout=25)
    soup=BeautifulSoup(response.text,'html.parser');data=[]
    for s in soup.find_all('script',attrs={'type':'application/ld+json'}):
        if s.string:
            try:data.append(json.loads(s.string))
            except json.JSONDecodeError:pass
    return{'id':i,'url':url,'status':response.status_code,'data':data}
if __name__=='__main__':
    results=list(concurrent.futures.ThreadPoolExecutor(max_workers=4).map(read,sys.argv[1:]))
    Path('build/v3-public-parts.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    for item in results:
        for group in item['data']:
            nodes=group.get('@graph',[group])
            for node in nodes:
                if node.get('@type')=='Product':print(json.dumps({'id':item['id'],'name':node.get('name'),'sku':node.get('sku'),'offers':node.get('offers'),'datasheet':node.get('subjectOf')},ensure_ascii=True))
