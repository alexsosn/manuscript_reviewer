"""Repair a downloaded OCR document and align it locally; never uploads."""
import argparse,json,sys,hashlib,csv
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
APP=Path(__file__).resolve().parents[1];sys.path.insert(0,str(APP))
from layout_repair import repair_page,body_regions
from pagexml import model
from alignment_cache import input_digest,load_cached,continuity
CORPUS=None

def prepare_one(root,file,revision="corrected"):
 global CORPUS
 try:
  root=Path(root);source=Path(file);dest=root/revision/'page'/source.name;report=root/('reports' if revision=='corrected' else 'reports_v2')/(source.stem+'.json');report.parent.mkdir(parents=True,exist_ok=True)
  if dest.exists():
   prior=json.loads(report.read_text())
   if prior['sourceSha256']!=hashlib.sha256(source.read_bytes()).hexdigest() or prior['correctedSha256']!=hashlib.sha256(dest.read_bytes()).hexdigest():raise ValueError('Existing correction changed; reconcile manually instead of replacing it')
  else:report.write_text(json.dumps(repair_page(source,dest,root/'images'/(source.stem+'.jpg'),APP/'data/pagecontent-2013.xsd'),ensure_ascii=False,indent=2))
  m=model(dest.read_bytes(),dest.name,str(dest));body=body_regions(m['regions']);lines=[{'id':l['id'],'text':l['text']} for r in body for l in r['lines']];cache=root/revision/'alignment';cache.mkdir(exist_ok=True)
  result=load_cached(cache,m['pageNr'],lines)
  if result is None:
   if CORPUS is None:
    from corpus import Corpus
    CORPUS=Corpus(APP/'data')
   result=CORPUS.align(lines);result['excludedLines']=[{'id':l['id'],'text':l['text']} for r in m['regions'] if r not in body for l in r['lines']]
   (cache/f'{m["pageNr"]}.json').write_text(json.dumps({'version':2,'inputDigest':input_digest(lines),'pageNr':m['pageNr'],'result':result},ensure_ascii=False))
  return m['pageNr']
 except Exception as error:raise ValueError(str(error)) from None

def coverage_report(root,revision="corrected"):
 from corpus import Corpus
 corpus=Corpus(APP/'data');rows=[];previous=None
 pages=json.loads((root/'download.json').read_text())['pageList']['pages']
 for page in sorted(pages,key=lambda p:p['pageNr']):
  nr=page['pageNr'];file=root/revision/'alignment'/f'{nr}.json'
  if not file.exists():rows.append({'pageNr':nr,'state':'unresolved','warning':'No alignment cache; inspect preparation errors'});previous=None;continue
  result=json.loads(file.read_text())['result'];coverage=result.get('coverage');boundary=continuity(previous,result,corpus) if previous else {'status':'unverified','message':'Start of coverage or preceding page unresolved; verify passage boundary'}
  rows.append({'pageNr':nr,'state':'aligned' if coverage else 'unresolved','passage':result.get('passage',''),'score':result['score'],'letterScore':result.get('letterScore',0),'coverage':coverage,'boundary':boundary,'excludedLines':len(result.get('excludedLines',[])),'warning':result.get('warning','')});previous=result
 summary={'pages':len(rows),'aligned':sum(r['state']=='aligned' for r in rows),'unresolved':[r['pageNr'] for r in rows if r['state']!='aligned'],'lowLetterAgreement':[r['pageNr'] for r in rows if r.get('letterScore',0)<.85],'boundaryGaps':[r['pageNr'] for r in rows if r.get('boundary',{}).get('status')=='gap'],'bookTransitions':[r['pageNr'] for r in rows if r.get('boundary',{}).get('status')=='book-transition'],'boundaryOverlaps':[r['pageNr'] for r in rows if r.get('boundary',{}).get('status')=='overlap'],'unassignedReferenceCharacters':sum((r.get('coverage') or {}).get('unassignedReferenceCharacters',0) for r in rows)}
 (root/'coverage.json').write_text(json.dumps({'summary':summary,'pages':rows},ensure_ascii=False,indent=2))
 with (root/'coverage.csv').open('w') as f:
  writer=csv.writer(f);writer.writerow(['page','state','passage','full_character_agreement','letter_agreement','missing_reference_characters','extra_ocr_characters','boundary','marginal_lines','warning'])
  for r in rows:writer.writerow([r['pageNr'],r['state'],r.get('passage',''),r.get('score',0),r.get('letterScore',0),(r.get('coverage') or {}).get('missingReferenceCharacters',''),(r.get('coverage') or {}).get('extraOcrCharacters',''),r.get('boundary',{}).get('status',''),r.get('excludedLines',0),r.get('warning','')])
 return summary

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('folder',type=Path);ap.add_argument('--jobs',type=int,default=2);ap.add_argument('--revision',default='corrected');ap.add_argument('--report-only',action='store_true');args=ap.parse_args();errors=[]
 if args.revision not in ('corrected','corrected_v2'):ap.error('Revision must be corrected or corrected_v2')
 if not args.report_only:
  with ProcessPoolExecutor(max_workers=max(1,min(4,args.jobs))) as pool:
   pending={pool.submit(prepare_one,args.folder,f,args.revision):f.name for f in (args.folder/'original/page').glob('*.xml')}
   for i,future in enumerate(as_completed(pending),1):
    try:future.result()
    except Exception as e:errors.append({'file':pending[future],'error':str(e)});print(errors[-1],flush=True)
    if i%25==0:print('Prepared',i,'pages',flush=True)
  (args.folder/'preparation-errors.json').write_text(json.dumps(errors,indent=2))
 print(json.dumps(coverage_report(args.folder,args.revision),indent=2))
 if errors:raise SystemExit(1)
if __name__=='__main__':main()
