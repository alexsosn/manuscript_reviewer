"""Prepare/review an immutable upload plan, then execute or resume it explicitly."""
import sys,json,argparse,time
from pathlib import Path
APP=Path(__file__).resolve().parents[1];sys.path.insert(0,str(APP))
from backend import Backend
from publishing import Publisher

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['prepare','run','status']);ap.add_argument('--workspace',type=Path,default=APP.parent);ap.add_argument('--profile');ap.add_argument('--mode',choices=['full','selected'],default='full');ap.add_argument('--collection',type=int);ap.add_argument('--document',type=int,default=0);ap.add_argument('--pages',default='');ap.add_argument('--title',default='BL Add MS 14,470 — Automatic review');ap.add_argument('--include-drafts',action='store_true');ap.add_argument('--without-notes',action='store_true');ap.add_argument('--plan');args=ap.parse_args()
 b=Backend(args.workspace)
 if args.profile:b.configure({'activeProfile':args.profile},persist=False)
 p=Publisher(b)
 if args.action=='status':print(json.dumps(p.status(args.plan),indent=2));return
 b.api.login(saved=True)
 if args.action=='prepare':
  if not args.collection:ap.error('--collection is required')
  result=p.prepare({'mode':args.mode,'collection':args.collection,'document':args.document,'pages':args.pages,'title':args.title,'drafts':args.include_drafts,'notes':not args.without_notes});print(json.dumps({k:v for k,v in result.items() if k!='pageNumbers'},ensure_ascii=False,indent=2));return
 if not args.plan:ap.error('--plan is required')
 p.start(args.plan);previous=None
 while True:
  state=p.status(args.plan);progress=(state['phase'],state['completed'],state['document'],state.get('transferred',0))
  if progress!=previous:print(json.dumps({k:state.get(k,0) for k in ['phase','completed','transferred','total','collection','document','message']}),flush=True);previous=progress
  if state['phase'] in ('complete','stopped','paused'):
   if state['phase']=='stopped':raise SystemExit(1)
   return
  time.sleep(3)
if __name__=='__main__':main()
