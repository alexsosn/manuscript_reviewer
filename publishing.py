"""Independent full-copy and explicitly selected-page publication.

Plans freeze local XML. Per-page journals prevent blind POST retries. Target page
IDs and image checksums are checked; source XML identities are never rewritten.
"""
from pathlib import Path
from datetime import datetime,timezone
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,hashlib,re,uuid,time,os,threading,urllib.parse
from lxml import etree as E
from pagexml import parse,N,model,server_metadata,page_signature
from layout_repair import body_regions
from alignment_cache import load_cached
from transkribus import APIError

ACTIVE={'running','copying','creating','verifying'}
def digest(raw):return hashlib.sha256(raw).hexdigest()
def pages_spec(value):
 out=set()
 for part in value.split(','):
  part=part.strip()
  if not part:continue
  if not re.fullmatch(r'\d+(?:\s*-\s*\d+)?',part):raise ValueError('Pages must be numbers or ranges, such as 3, 4, 10-12')
  bits=[int(n.strip()) for n in part.split('-')];a,b=bits[0],bits[-1]
  if a<1 or b<a or b-a>10000:raise ValueError('Invalid page range')
  out.update(range(a,b+1))
 return sorted(out)
def escape(s):return ''.join('\\u%04x'%ord(c) if c in ':;{}\\\n\r\t' else c for c in s)
def utf16(s):return len(s.encode('utf-16-le'))//2

def annotate(raw,alignment):
 """Native alternative/reason fields; never change OCR or geometry."""
 root=parse(raw);lines={l.get('id'):l for l in root.findall('.//p:TextLine',N)};count=0
 for ref in alignment.get('lines',[]):
  line=lines.get(ref['id'])
  if line is None:continue
  text=line.findtext('p:TextEquiv/p:Unicode','',N)
  for change in ref.get('changes',[]):
   a,b=change['ocrStart'],change['ocrEnd'];missing=a==b
   if missing:
    if not text:continue
    a=min(a,len(text)-1);b=a+1
    while a>0 and __import__('unicodedata').category(text[a]).startswith('M'):a-=1
   if b<=a:continue
   words=[w for w in ref.get('words',[]) if w['start']<change['referenceEnd'] and w['end']>change['referenceStart']]
   alternative=' '.join(dict.fromkeys(w['word'] for w in words)) or change['reference'] or '∅'
   reason=f"SyrNT automated review | Passage: {ref['address']} | {change['kind']} | OCR: {change['ocr'] or '∅'} | Reference: {change['reference'] or '∅'}"
   if missing:reason+=' | Missing reference text; anchored beside the omission'
   if alignment.get('warning'):reason+=' | Uncertain passage alignment: verify reference boundaries'
   tag=f'unclear {{offset:{utf16(text[:a])}; length:{utf16(text[a:b])}; alternative:{escape(alternative)}; reason:{escape(reason)};}}'
   if tag not in line.get('custom',''):line.set('custom',(line.get('custom','')+' '+tag).strip());count+=1
 # Verify that annotations alone changed.
 clean=deepcopy(root);old=parse(raw)
 for a,b in zip(old.findall('.//p:TextLine',N),clean.findall('.//p:TextLine',N)):
  if 'custom' in a.attrib:b.set('custom',a.get('custom'))
  else:b.attrib.pop('custom',None)
 if page_signature(E.tostring(clean))!=page_signature(raw):raise ValueError('Reference annotations changed layout or OCR')
 return E.tostring(root,encoding='UTF-8',xml_declaration=True),count

class Publisher:
 def __init__(self,backend):
  self.b=backend;self.api=backend.api;self.folder=Path(backend.settings['output'])/'publishing';self.folder.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock()
 def write(self,path,data):self.b.atomic(path,json.dumps(data,ensure_ascii=False,indent=2).encode())
 def plan_folder(self,ident):
  if not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Invalid upload plan')
  return self.folder/ident
 def status(self,ident):return json.loads((self.plan_folder(ident)/'state.json').read_text())
 def plans(self):
  return [json.loads(p.read_text()) for p in sorted(self.folder.glob('*/state.json'),key=lambda p:p.stat().st_mtime,reverse=True)][:10]
 def targets(self):
  prior={}
  try:prior=json.loads((self.folder/'destinations.json').read_text())
  except FileNotFoundError:pass
  return {'collections':json.loads(self.api.request('collections/list',accept='application/json')),'archiveCollection':prior.get('collection',2554943),'archiveDocument':prior.get('document',0),'selectedCollection':self.b.settings['collection'],'selectedDocument':self.b.settings['document'],'jobs':self.plans()}
 def documents(self,coll):return json.loads(self.api.request(f'collections/{int(coll)}/list',accept='application/json'))
 def check_pages(self,plan,target):
  doc=target['md']['docId'];coll=plan['targetCollection'];source=plan['sourceDocument']
  if plan['mode']=='full':
   if doc==source or target['md'].get('mainColId',coll)!=coll:raise ValueError('Full upload requires an independent document in the destination collection, not a shared shortcut')
   if len(target['pageList']['pages'])!=len(plan['rows']):raise ValueError('Full-copy target has a different number of pages')
  pages={p['pageNr']:p for p in target['pageList']['pages']}
  for row in plan['rows']:
   p=pages.get(row['pageNr'])
   if not p or p['imgFileName']!=row['image'] or p.get('md5Sum')!=row['imageMd5']:raise ValueError(f'Page {row["pageNr"]}: destination image does not match the local source')
   if plan['mode']=='full' and p['pageId']==row['sourcePageId']:raise ValueError('The destination shares source page IDs; independent copy required')
  return pages
 def prepare(self,args):
  mode=args['mode'];coll=int(args['collection']);doc=int(args.get('document') or 0)
  if mode not in ('full','selected') or coll<1:raise ValueError('Select an upload mode and destination collection')
  if mode=='full' and coll==int(self.b.settings['collection']):raise ValueError('Full automatic upload must go to a separate collection')
  numbers=sorted(self.b.pages) if mode=='full' else pages_spec(args.get('pages',''))
  if not numbers or any(n not in self.b.pages for n in numbers):raise ValueError('Select pages present in the current local document')
  if mode=='selected' and not doc:raise ValueError('Selected-page uploads require an existing destination document')
  collections=json.loads(self.api.request('collections/list',accept='application/json'));destination=next((c for c in collections if c['colId']==coll),None)
  if not destination:raise ValueError('Destination collection is not accessible')
  ident=uuid.uuid4().hex;folder=self.plan_folder(ident);(folder/'pages').mkdir(parents=True)
  plan={'id':ident,'mode':mode,'sourceDocument':int(self.b.settings['document']),'imagesFolder':self.b.settings['images'],'sourceCollection':int(self.b.settings['collection']),'targetCollection':coll,'targetCollectionName':destination['colName'],'targetDocument':doc,'title':(args.get('title') or self.b.settings.get('title','Manuscript')+' — Automatic review')+f' [{ident[:8]}]','includeNotes':bool(args.get('notes',True)),'includeDrafts':mode=='selected' or bool(args.get('drafts',False)),'rows':[],'created':datetime.now(timezone.utc).isoformat()}
  schema=E.XMLSchema(E.parse(str(self.b.schema())))
  for nr in numbers:
   source,name=self.b.source(nr)
   if not plan['includeDrafts']:source=self.b.pages[nr]
   raw=source.read_bytes();source_hash=digest(raw);m=model(raw,name,str(source))
   if m['docId']!=plan['sourceDocument']:raise ValueError('Local document identity mismatch')
   image=self.b.page(nr)['imageFile'];im=Path(self.b.settings['images'])/image
   if Path(image).name!=image:raise ValueError('Image must be inside the selected image folder')
   notes=0
   if plan['includeNotes']:
    body=body_regions(m['regions']);lines=[{'id':l['id'],'text':l['text']} for r in body for l in r['lines']]
    alignment=load_cached(Path(self.b.settings['source']).parent/'alignment',nr,lines) or self.b.get_corpus().align(lines)
    raw,notes=annotate(raw,alignment)
   validation=parse(raw)
   for el in validation.findall('.//p:TranskribusMetadata',N):el.getparent().remove(el)
   schema.assertValid(validation);(folder/'pages'/f'{nr}.xml').write_bytes(raw)
   if digest(source.read_bytes())!=source_hash or plan['includeDrafts'] and self.b.source(nr)[0]!=source:raise ValueError(f'Page {nr}: local file changed while preparing the upload')
   plan['rows'].append({'pageNr':nr,'file':name,'sourcePath':str(source),'sourceHash':source_hash,'sha256':digest(raw),'sourcePageId':m['pageId'],'sourceTsId':m['tsId'],'image':image,'imageMd5':hashlib.md5(im.read_bytes()).hexdigest(),'notes':notes})
  baseline={}
  if doc:
   target=json.loads(self.api.request(f'collections/{coll}/{doc}/fulldoc'));pages=self.check_pages(plan,target);plan['targetTitle']=target['md']['title']
   # Existing targets require a baseline from this tool or the source snapshot.
   receipts=self.previous_receipts(coll,doc)
   for row in plan['rows']:
    p=pages[row['pageNr']];ts=p['tsList']['transcripts'][0]['tsId'];prior=receipts.get(str(row['pageNr']))
    allowed=(doc==plan['sourceDocument'] and p['pageId']==row['sourcePageId'] and ts==row['sourceTsId']) or (prior and ts==prior['tsId'] and p['pageId']==prior['pageId'])
    if not allowed:raise ValueError(f'Page {row["pageNr"]}: newer or untracked destination work. Download and reconcile it before uploading.')
    baseline[str(row['pageNr'])]={'tsId':ts,'pageId':p['pageId']}
  plan['baseline']=baseline;self.write(folder/'plan.json',plan)
  state={'id':ident,'phase':'prepared','mode':mode,'total':len(numbers),'completed':0,'collection':coll,'document':doc,'title':plan.get('targetTitle',plan['title']),'message':'Ready to upload; no server writes have been made','pages':{},'notes':sum(r['notes'] for r in plan['rows']),'created':plan['created']};self.write(folder/'state.json',state)
  return {**state,'collectionName':plan['targetCollectionName'],'pageNumbers':numbers,'includesDrafts':plan['includeDrafts'],'includesNotes':plan['includeNotes']}
 def previous_receipts(self,coll,doc):
  result={}
  for file in sorted(self.folder.glob('*/state.json'),key=lambda p:p.stat().st_mtime):
   s=json.loads(file.read_text())
   if s.get('collection')==coll and s.get('document')==doc:
    for nr,p in s.get('pages',{}).items():
     if p.get('phase')=='verified':result[nr]=p
  return result
 def update(self,folder,state,**patch):
  with self.lock:state.update(patch);self.write(folder/'state.json',state)
 def active(self):
  try:
   record=json.loads((self.folder/'active.lock').read_text());os.kill(record['pid'],0);return True
  except (FileNotFoundError,ProcessLookupError):return False
 def acquire(self,ident):
  file=self.folder/'active.lock'
  if file.exists():
   old=json.loads(file.read_text())
   try:os.kill(old['pid'],0)
   except ProcessLookupError:file.unlink()
   else:raise ValueError('An upload is already running; inspect its progress first')
  with file.open('x') as f:json.dump({'pid':os.getpid(),'id':ident},f)
  return file
 def pause(self,ident):
  folder=self.plan_folder(ident);(folder/'pause.requested').touch();return {'requested':True}
 def start(self,ident):
  folder=self.plan_folder(ident);state=self.status(ident)
  if state['phase']=='complete':return state
  lock=self.acquire(ident)
  (folder/'pause.requested').unlink(missing_ok=True)
  self.update(folder,state,phase='running',message='Starting or resuming the prepared upload')
  thread=threading.Thread(target=self.run,args=(ident,lock),daemon=True);thread.start();return {**state,'phase':'running'}
 def run(self,ident,lock=None):
  folder=self.plan_folder(ident);plan=json.loads((folder/'plan.json').read_text());state=self.status(ident)
  try:
   if not state.get('document'):
    if state.get('copyForbidden'):self.import_copy(folder,plan,state)
    else:
     try:self.ensure_copy(folder,plan,state)
     except APIError as error:
      if error.status!=403:raise
      self.update(folder,state,copyForbidden=True,message='Server copy forbidden; creating an independent upload from local files')
      self.import_copy(folder,plan,state)
   if state['phase']=='paused':return
   if state.get('importId'):
    self.verify_import(folder,plan,state)
    return
   doc=state['document'];coll=plan['targetCollection'];target=json.loads(self.api.request(f'collections/{coll}/{doc}/fulldoc'));pages=self.check_pages(plan,target)
   if not plan['baseline']:
    plan['baseline']={str(nr):{'tsId':p['tsList']['transcripts'][0]['tsId'],'pageId':p['pageId']} for nr,p in pages.items()};self.write(folder/'plan.json',plan)
   self.update(folder,state,phase='running',message='Uploading and verifying pages')
   stop=threading.Event()
   def send(row):
    if stop.is_set() or (folder/'pause.requested').exists():return
    nr=row['pageNr'];key=str(nr);prior=state['pages'].get(key,{})
    if prior.get('phase')=='verified':return
    raw=(folder/'pages'/f'{nr}.xml').read_bytes()
    if digest(raw)!=row['sha256']:raise ValueError(f'Prepared XML changed for page {nr}')
    expected=plan['baseline'][key];info={'tsId':expected['tsId'],'pageId':expected['pageId'],'docId':doc,'pageNr':nr,'status':pages[nr]['tsList']['transcripts'][0]['status']};raw=server_metadata(raw,info)
    if prior.get('phase') in ('sending','accepted'):
     current,meta=self.api.pull(coll,doc,nr)
     if page_signature(current)==page_signature(raw):
      with self.lock:state['pages'][key]={'phase':'verified','tsId':meta['tsId'],'pageId':meta['pageId']};self.update(folder,state,completed=sum(p['phase']=='verified' for p in state['pages'].values()))
      return
     if meta['tsId']!=expected['tsId']:raise ValueError(f'Page {nr}: ambiguous upload or changed server version; reconcile before retrying')
    with self.lock:state['pages'][key]={'phase':'sending','pageId':expected['pageId']};self.write(folder/'state.json',state)
    downloaded,receipt=self.api.upload(coll,doc,nr,raw,{'tsId':expected['tsId']})
    with self.lock:
     state['pages'][key]={**receipt,'pageId':expected['pageId'],'phase':'verified' if receipt['verified'] else 'accepted'};self.update(folder,state,completed=sum(p['phase']=='verified' for p in state['pages'].values()))
    if not receipt['verified']:raise ValueError(receipt['warning'])
   def guarded(row):
    try:return send(row)
    except Exception:
     stop.set();raise
   # Parallelize only independent private pages. Shared selected pages are sequential.
   if plan['mode']=='full':
    with ThreadPoolExecutor(max_workers=3) as pool:
     futures=[pool.submit(guarded,row) for row in plan['rows']]
     for future in as_completed(futures):future.result()
   else:
    for row in plan['rows']:send(row)
   if (folder/'pause.requested').exists():
    self.update(folder,state,phase='paused',message='Paused after the active page transfers; resume this same plan to continue');return
   if plan['mode']=='full':self.write(self.folder/'destinations.json',{'collection':coll,'document':doc})
   self.update(folder,state,phase='complete',message='All uploaded pages verified')
  except Exception as error:self.update(folder,state,phase='stopped',message=str(error)+' No automatic retry was performed; inspect progress, then resume after reconciliation.')
  finally:
   if lock and lock.exists():lock.unlink()
 def ensure_copy(self,folder,plan,state):
  coll=plan['targetCollection'];docs=self.documents(coll);matches=[d for d in docs if d['title']==plan['title'] and d['docId']!=plan['sourceDocument']]
  if len(matches)>1:raise ValueError('Multiple copy candidates found; choose the correct destination document manually')
  if not matches and not state.get('copyAttempted'):
   self.update(folder,state,phase='creating',copyAttempted=True,message='Creating an independent document copy')
   query=urllib.parse.urlencode({'name':plan['title'],'collId':coll})
   response=self.api.request(f'collections/{plan["sourceCollection"]}/{plan["sourceDocument"]}/duplicate?'+query,data=b'',accept='application/json')
   text=response.decode().strip();job=json.loads(text) if text.startswith(('{','"')) else text
   job=job.get('jobId',job.get('id')) if isinstance(job,dict) else job
   self.update(folder,state,copyJob=str(job),phase='copying',message='Waiting for the independent copy')
  started=time.monotonic()
  while not matches:
   if time.monotonic()-started>300:raise ValueError('Copy is still pending; resume this plan later instead of creating another copy')
   if state.get('copyJob'):
    job=json.loads(self.api.request('jobs/'+state['copyJob'],accept='application/json'))
    if str(job.get('state',job.get('status',''))).upper() in ('FAILED','ERROR','CANCELED'):raise ValueError('Document copy job failed; inspect it in Transkribus')
   time.sleep(3);matches=[d for d in self.documents(coll) if d['title']==plan['title'] and d['docId']!=plan['sourceDocument']]
  doc=matches[0]['docId'];target=json.loads(self.api.request(f'collections/{coll}/{doc}/fulldoc'));self.check_pages(plan,target)
  self.update(folder,state,document=doc,title=matches[0]['title'],phase='running',message='Independent document verified; uploading local results')
 def import_xml(self,folder,row):
  raw=(folder/'pages'/f'{row["pageNr"]}.xml').read_bytes()
  if digest(raw)!=row['sha256']:raise ValueError('Prepared PAGE XML changed')
  root=parse(raw)
  for el in root.findall('.//p:TranskribusMetadata',N):el.getparent().remove(el)
  return E.tostring(root,encoding='UTF-8',xml_declaration=True)
 def multipart(self,image_name,image,xml_name,xml):
  if any('"' in n or '\r' in n or '\n' in n for n in (image_name,xml_name)):raise ValueError('Invalid upload filename')
  boundary='syriac'+uuid.uuid4().hex;parts=[]
  for name,file,raw in [('img',image_name,image),('xml',xml_name,xml)]:
   parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{file}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()+raw+b'\r\n')
  return b''.join(parts)+(f'--{boundary}--\r\n').encode(),'multipart/form-data; boundary='+boundary
 def import_copy(self,folder,plan,state):
  coll=plan['targetCollection']
  if not state.get('importId'):
   if state.get('importAttempted'):raise ValueError('Upload session creation had an uncertain result. Inspect Transkribus uploads; do not create another session blindly')
   pages=[]
   for row in plan['rows']:
    pages.append({'fileName':row['image'],'pageXmlName':Path(row['image']).stem+'.xml','pageNr':row['pageNr'],'imgChecksum':row['imageMd5'],'pageXmlChecksum':hashlib.md5(self.import_xml(folder,row)).hexdigest()})
   self.update(folder,state,importAttempted=True,phase='importing',message='Creating an independent document from local images and PAGE XML')
   response=json.loads(self.api.request(f'uploads?collId={coll}',data=json.dumps({'md':{'title':plan['title']},'pageList':{'pages':pages}}).encode(),accept='application/json',content_type='application/json'))
   self.update(folder,state,importId=response['uploadId'],transferPages={},transferred=0)
  upload=state['importId'];remote=json.loads(self.api.request(f'uploads/{upload}',accept='application/json'));uploaded={p['pageNr'] for p in remote.get('pageList',{}).get('pages',remote.get('pages',[])) if p.get('pageUploaded')}
  stop=threading.Event()
  def transfer(row):
   if stop.is_set() or (folder/'pause.requested').exists():return
   nr=row['pageNr'];key=str(nr)
   if nr not in uploaded:
    image=(Path(plan.get('imagesFolder',self.b.settings['images']))/row['image']).read_bytes()
    if hashlib.md5(image).hexdigest()!=row['imageMd5']:raise ValueError(f'Image changed for page {nr}')
    body,content_type=self.multipart(row['image'],image,Path(row['image']).stem+'.xml',self.import_xml(folder,row))
    with self.lock:state['transferPages'][key]='sending';self.write(folder/'state.json',state)
    self.api.request(f'uploads/{upload}',data=body,accept='application/json',method='PUT',content_type=content_type)
   with self.lock:
    state['transferPages'][key]='received';self.update(folder,state,transferred=sum(v=='received' for v in state['transferPages'].values()),message=f'Transferred {sum(v=="received" for v in state["transferPages"].values())}/{state["total"]} images and PAGE files')
  def guarded(row):
   try:return transfer(row)
   except Exception:stop.set();raise
  with ThreadPoolExecutor(max_workers=3) as pool:
   futures=[pool.submit(guarded,row) for row in plan['rows']]
   for future in as_completed(futures):future.result()
  if (folder/'pause.requested').exists():
   self.update(folder,state,phase='paused',message='File transfer paused; resume this same plan to continue');return
  self.update(folder,state,phase='importing',message='All files transferred; waiting for Transkribus to ingest the independent document')
  started=time.monotonic()
  while True:
   if (folder/'pause.requested').exists():self.update(folder,state,phase='paused',message='Import is pending on Transkribus; resume to check progress');return
   matches=[d for d in self.documents(coll) if d['title']==plan['title'] and d['docId']!=plan['sourceDocument']]
   if len(matches)>1:raise ValueError('Multiple independent upload candidates found; inspect before continuing')
   if matches:
    doc=matches[0]['docId'];target=json.loads(self.api.request(f'collections/{coll}/{doc}/fulldoc'))
    if len(target['pageList']['pages'])==len(plan['rows']):
     self.check_pages(plan,target);self.update(folder,state,document=doc,phase='verifying',message='Independent document ingested; verifying every PAGE file');return
   if time.monotonic()-started>1200:raise ValueError('Document ingest is still pending; resume this plan later')
   remote=json.loads(self.api.request(f'uploads/{upload}',accept='application/json'))
   if remote.get('jobId'):
    job=json.loads(self.api.request(f'jobs/{remote["jobId"]}',accept='application/json'))
    if str(job.get('state',job.get('status',''))).upper() in ('FAILED','ERROR','CANCELED'):raise ValueError('Document ingest failed; inspect the server job before resuming')
   time.sleep(4)
 def verify_import(self,folder,plan,state):
  coll,doc=plan['targetCollection'],state['document'];target=json.loads(self.api.request(f'collections/{coll}/{doc}/fulldoc'));self.check_pages(plan,target)
  self.update(folder,state,phase='verifying',message='Verifying imported layout, OCR and reference annotations')
  def check(row):
   nr=row['pageNr'];expected=self.import_xml(folder,row);actual,info=self.api.pull(coll,doc,nr)
   if page_signature(actual)!=page_signature(expected):raise ValueError(f'Page {nr}: imported PAGE differs from prepared text/layout/tags. No overwrite was attempted')
   with self.lock:
    state['pages'][str(nr)]={'phase':'verified','tsId':info['tsId'],'pageId':info['pageId']};self.update(folder,state,completed=len(state['pages']))
  with ThreadPoolExecutor(max_workers=3) as pool:
   for future in as_completed([pool.submit(check,row) for row in plan['rows']]):future.result()
  self.write(self.folder/'destinations.json',{'collection':coll,'document':doc});self.update(folder,state,phase='complete',message='All uploaded pages verified')
