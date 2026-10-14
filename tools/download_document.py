"""Read-only, resumable download of an immutable Transkribus PAGE snapshot.

Run from the workspace: python tools/download_document.py --collection ID --document ID
Files are pinned to the transcript IDs in download.json; existing exports are retained.
"""
import sys,json,hashlib,urllib.request,time,shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
ap=argparse.ArgumentParser();ap.add_argument('--collection',type=int,required=True);ap.add_argument('--document',type=int,required=True);args=ap.parse_args()
from transkribus import Transkribus
from pagexml import server_metadata,parse,N
root=Path('documents')/str(args.document);(root/'original/page').mkdir(parents=True,exist_ok=True);(root/'images').mkdir(exist_ok=True)
manifest=root/'download.json'
if manifest.exists():data=json.loads(manifest.read_text())
else:
 api=Transkribus();api.login(saved=True);data=json.loads(api.request(f'collections/{args.collection}/{args.document}/fulldoc'));manifest.write_text(json.dumps(data,indent=2))
pages=data['pageList']['pages']
def fetch(url):
 if not url.startswith('https://files.transkribus.eu/'):raise ValueError('Unexpected file host')
 for attempt in range(3):
  try:
   with urllib.request.urlopen(url,timeout=60) as r:return r.read()
  except Exception:
   if attempt==2:raise
   time.sleep(1+attempt)
def task(p):
 ts=p['tsList']['transcripts'][0];name=Path(p['imgFileName']).name;xml=root/'original/page'/(Path(name).stem+'.xml');im=root/'images'/name
 if not im.exists() or hashlib.md5(im.read_bytes()).hexdigest()!=p['md5Sum']:
  old=Path('Preliminary_Setup__BL_Add_MS_14,470')/name
  raw=old.read_bytes() if old.exists() else b''
  if hashlib.md5(raw).hexdigest()!=p['md5Sum']:raw=fetch(p['url'])
  if hashlib.md5(raw).hexdigest()!=p['md5Sum']:raise ValueError(f'Image checksum mismatch {name}')
  im.write_bytes(raw)
 if not xml.exists():
  raw=fetch(ts['url']);parse(raw)
  if ts.get('md5Sum') and hashlib.md5(raw).hexdigest()!=ts['md5Sum']:raise ValueError(f'PAGE checksum mismatch {name}')
  raw=server_metadata(raw,{'tsId':ts['tsId'],'pageId':p['pageId'],'docId':args.document,'pageNr':p['pageNr'],'status':ts['status']})
  xml.write_bytes(raw)
 return p['pageNr']
errors=[]
with ThreadPoolExecutor(max_workers=4) as pool:
 futures={pool.submit(task,p):p['pageNr'] for p in pages}
 for i,f in enumerate(as_completed(futures),1):
  try:f.result()
  except Exception as e:errors.append({'page':futures[f],'error':str(e)});print('error',errors[-1],flush=True)
  if i%25==0:print(i,'/',len(pages),'downloaded',flush=True)
(root/'download_errors.json').write_text(json.dumps(errors,indent=2))
print('COMPLETE',len(pages)-len(errors),'errors',len(errors),flush=True)
if errors:raise SystemExit(1)

if not errors:
 config=root/'document.json'
 if not config.exists():config.write_text(json.dumps({'title':data.get('md',{}).get('title',f'Transkribus document {args.document}'),'collection':args.collection,'document':args.document,'source':'original/page','images':'images','output':'local_edits'},indent=2))
