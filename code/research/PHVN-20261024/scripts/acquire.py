"""Archive public research sources without touching the production map inputs."""
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urljoin, urlparse
from html.parser import HTMLParser
from datetime import datetime, timezone, timedelta
import hashlib, json, csv, argparse, concurrent.futures, re

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
 'hokkaido': 'https://kouseikyoku.mhlw.go.jp/hokkaido/iryo_shido/ns_iryou.html',
 'tohoku': 'https://kouseikyoku.mhlw.go.jp/tohoku/gyomu/gyomu/hoken_kikan/houmon_00005.html',
 'kantoshinetsu': 'https://kouseikyoku.mhlw.go.jp/kantoshinetsu/chousa/houmon.html',
 'tokaihokuriku': 'https://kouseikyoku.mhlw.go.jp/tokaihokuriku/newpage_00245.html',
 'kinki': 'https://kouseikyoku.mhlw.go.jp/kinki/gyomu/gyomu/hoken_kikan/shitei_jokyo_00005.html',
 'chugoku': 'https://kouseikyoku.mhlw.go.jp/chugokushikoku/chousaka/shisetsukijunjuri.html',
 'shikoku': 'https://kouseikyoku.mhlw.go.jp/shikoku/gyomu/gyomu/hoken_kikan/shitei/index.html',
 'kyushu': 'https://kouseikyoku.mhlw.go.jp/kyushu/gyomu/gyomu/hoken_kikan/index_00018.html',
 'ncnp630': 'https://www.ncnp.go.jp/nimh/seisaku/data/630.html',
 'remhrad': 'https://remhrad.jp/facility_mapping',
 'mesh500': 'https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-mesh500r6.html',
 'mesh_method': 'https://www.mlit.go.jp/kokudoseisaku/kokudoseisaku_tk3_000086.html',
 'kaigo': 'https://www.mhlw.go.jp/stf/kaigo-kouhyou_opendata.html',
 'pcn_society': 'https://www.jspn.or.jp/modules/journal/index.php?content_id=6',
 'kochi_paper': 'https://www.jstage.jst.go.jp/article/jans/43/0/43_43752/_html/-char/ja',
}

class Links(HTMLParser):
 def __init__(self):
  super().__init__(); self.href=None; self.label=[]; self.links=[]; self.text=[]
 def handle_starttag(self, tag, attrs):
  if tag=='a': self.href=dict(attrs).get('href'); self.label=[]
 def handle_data(self, d):
  if self.href is not None: self.label.append(d)
  if d.strip(): self.text.append(d.strip())
 def handle_endtag(self, tag):
  if tag=='a' and self.href is not None:
   self.links.append((self.href,' '.join(self.label).strip())); self.href=None

def now(): return datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds')

def acquire(key,url,subdir='pages',filename=None):
 target=ROOT/'sources'/subdir/(filename or (key+'.html'))
 target.parent.mkdir(parents=True,exist_ok=True)
 record={'key':key,'source_url':url,'retrieved_jst':now(),'path':str(target.relative_to(ROOT))}
 try:
  if target.exists():
   data=target.read_bytes(); record['status']='existing_preserved'
  else:
   with urlopen(Request(url,headers={'User-Agent':'PHVN academic source audit/0.1'}),timeout=60) as r:
    data=r.read(); record.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'),last_modified=r.headers.get('Last-Modified'))
   target.write_bytes(data)
  record.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
  if target.suffix=='.html':
   match=re.search(br'charset\s*=\s*["\x27]?([a-zA-Z0-9_-]+)',data[:8000],re.I)
   encoding=match.group(1).decode('ascii') if match else 'utf-8'
   text=data.decode(encoding,errors='replace'); p=Links(); p.feed(text)
   target.with_suffix('.txt').write_text('\n'.join(p.text),encoding='utf-8')
   rows=[{'label':label,'url':urljoin(url,href)} for href,label in p.links]
   target.with_suffix('.links.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
 except Exception as e: record.update(status='failed',error=str(e))
 log=ROOT/'audit'/'acquisition.jsonl'; log.parent.mkdir(parents=True,exist_ok=True)
 with log.open('a',encoding='utf-8') as f: f.write(json.dumps(record,ensure_ascii=False)+'\n')
 return record

if __name__=='__main__':
 ap=argparse.ArgumentParser(); ap.add_argument('--url'); ap.add_argument('--name'); args=ap.parse_args()
 if args.url:
  print(json.dumps(acquire(args.name,args.url,'downloads',args.name),ensure_ascii=False))
 else:
  # One request per host at a time; small public source pages only.
  for key,url in SOURCES.items():
   r=acquire(key,url); print(key,r['status'],r.get('bytes',r.get('error')),flush=True)
