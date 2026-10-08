"""One JSON request per line. Files and credentials stay outside the renderer."""
from pathlib import Path
from datetime import datetime,timezone
import sys,json,hashlib,os,uuid
from pagexml import model,update,parse,N,server_metadata
from corpus import Corpus
from paleography import Paleography
from transkribus import Transkribus
HERE=Path(__file__).resolve().parent
class Backend:
 def __init__(self,root=None):
  self.root=Path(root or HERE.parent).resolve();self.corpus=None;self.api=Transkribus();self.pages={};self.settings={};self.configure({})
 def configure(self,patch):
  if patch.get('root'):self.root=Path(patch['root']).resolve()
  setting=self.root/'local_edits/settings.json'
  defaults={'source':str(self.root/'layout_corrected/page'),'images':str(self.root/'Preliminary_Setup__BL_Add_MS_14,470'),'output':str(self.root/'local_edits'),'collection':2536248,'document':19244795,'uploadPages':[3,4,349]}
  if not Path(defaults['source']).is_dir():defaults['source']=str(self.root/'page')
  if not Path(defaults['images']).is_dir():defaults['images']=str(self.root)
  try:defaults.update(json.loads(setting.read_text()))
  except FileNotFoundError:pass
  defaults.update({k:v for k,v in patch.items() if k in defaults});self.settings=defaults
  if patch:
   setting.parent.mkdir(parents=True,exist_ok=True);self.atomic(setting,json.dumps(defaults,indent=2).encode())
  self.pages={}
  for f in Path(defaults['source']).glob('*.xml'):
   try:
    t=parse(f.read_bytes());m=t.find('.//p:TranskribusMetadata',N)
    if m is not None:self.pages[int(m.get('pageNr'))]=f
   except Exception:continue
  return {**defaults,'books':self.get_corpus().books_names() if hasattr(self.get_corpus(),'books_names') else [b['name'] for b in self.get_corpus().books],'root':str(self.root),'connected':bool(self.api.token)}
 def get_corpus(self):
  if self.corpus is None:self.corpus=Corpus(HERE/'data')
  return self.corpus
 def atomic(self,path,raw):
  temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');temp.write_bytes(raw);os.replace(temp,path)
 def source(self,nr):
  nr=int(nr)
  if nr not in self.pages:raise ValueError('Page is not in the selected PAGE folder')
  file=self.pages[nr]
  improved=self.root/'layout_v2/page'/file.name
  if Path(self.settings['source']).resolve()==(self.root/'layout_corrected/page').resolve() and improved.exists():file=improved
  dest=Path(self.settings['output'])/'page'/file.name
  return (dest if dest.exists() else file),file.name
 def page(self,nr):
  p,name=self.source(nr);data=model(p.read_bytes(),name,str(p))
  if data['docId']!=int(self.settings['document']):data['identityWarning']='This PAGE file belongs to a different document than the upload settings.'
  # Export metadata sometimes adds a numeric prefix to imageFilename.
  image=data['image'];base=Path(self.settings['images'])/image
  if not base.exists():
   import re
   alternate=re.sub(r'^\d{4}_','',image)
   if (Path(self.settings['images'])/alternate).exists():image=alternate
  data['imageFile']=image
  data['edited']=p.parent==Path(self.settings['output'])/'page'
  return data
 def index(self):
  result=[]
  for nr in sorted(self.pages):
   p,name=self.source(nr)
   t=parse(p.read_bytes());m=t.find('.//p:TranskribusMetadata',N)
   result.append({'pageNr':nr,'file':name,'lines':len(t.findall('.//p:TextLine',N)),'edited':p.parent==Path(self.settings['output'])/'page','tsId':m.get('tsid')})
  return result
 def schema(self):return self.root/'layout_corrected/pagecontent-2013.xsd' if (self.root/'layout_corrected/pagecontent-2013.xsd').exists() else HERE/'data/pagecontent-2013.xsd'
 def save(self,data):
  src,name=self.source(data['pageNr']);raw=src.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=data['revision']:raise ValueError('Local XML changed since opening. Reload it before saving.')
  revised=update(raw,data,self.schema());dest=Path(self.settings['output'])/'page'/name
  dest.parent.mkdir(parents=True,exist_ok=True);backup=dest.parent.parent/'backups'/name
  backup.mkdir(parents=True,exist_ok=True);self.atomic(backup/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.xml'),raw)
  self.atomic(dest,revised)
  # Keep 30 local pre-edit versions per page. Source exports remain untouched.
  for old in sorted(backup.glob('*.xml'))[:-30]:old.unlink()
  return self.page(data['pageNr'])
 def pull(self,nr):
  old,name=self.source(nr);raw,info=self.api.pull(int(self.settings['collection']),int(self.settings['document']),int(nr))
  raw=server_metadata(raw,info)
  m=model(raw,name,'server');assert m['pageId']==info['pageId']
  # The server's PAGE extension may retain an older tsid. Record the actual current version.
  t=parse(raw);meta=t.find('.//p:TranskribusMetadata',N);meta.set('tsid',str(info['tsId']))
  from lxml import etree as E
  raw=E.tostring(t,encoding='UTF-8',xml_declaration=True)
  dest=Path(self.settings['output'])/'page'/name;dest.parent.mkdir(parents=True,exist_ok=True)
  backup=dest.parent.parent/'backups'/name;backup.mkdir(parents=True,exist_ok=True)
  self.atomic(backup/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'_before_pull.xml'),old.read_bytes())
  self.atomic(dest,raw);return self.page(nr)
 def upload(self,nr):
  nr=int(nr)
  if nr not in self.settings['uploadPages']:raise ValueError('This page is outside your selected editing/upload scope. Update Pages I am editing in Settings only after coordinating with its editor.')
  src,name=self.source(nr);raw=src.read_bytes();data=model(raw,name,str(src))
  if data['docId']!=int(self.settings['document']):raise ValueError('Document ID mismatch')
  downloaded,receipt=self.api.upload(int(self.settings['collection']),data['docId'],nr,raw,{'tsId':data['tsId']})
  journal=Path(self.settings['output'])/'uploads';journal.mkdir(parents=True,exist_ok=True)
  self.atomic(journal/(f'{nr}_{receipt["tsId"]}.json'),json.dumps(receipt,indent=2).encode())
  if downloaded:
   downloaded=server_metadata(downloaded,{'tsId':receipt['tsId'],'pageId':data['pageId'],'docId':data['docId'],'pageNr':nr,'status':receipt['status']})
   t=parse(downloaded)
   from lxml import etree as E
   dest=Path(self.settings['output'])/'page'/name;dest.parent.mkdir(parents=True,exist_ok=True);self.atomic(dest,E.tostring(t,encoding='UTF-8',xml_declaration=True))
  return {'receipt':receipt,'page':self.page(nr)}
 def handle(self,req):
  cmd=req['command'];arg=req.get('args',{})
  if cmd=='paleography':return Paleography(self).read()
  if cmd=='paleoSave':return Paleography(self).save(arg['example'],arg['revision'])
  if cmd=='paleoDelete':return Paleography(self).delete(arg['id'],arg['revision'])
  if cmd=='settings':return self.configure(arg)
  if cmd=='index':return self.index()
  if cmd=='page':return self.page(arg['pageNr'])
  if cmd=='save':return self.save(arg['page'])
  if cmd=='align':
   lines=[{'id':l['id'],'text':l['text']} for r in arg['page']['regions'][:2] for l in r['lines']]
   return self.get_corpus().align(lines,arg.get('book',''),arg.get('anchor',''))
  if cmd=='lookup':return self.get_corpus().lookup(arg['word'],arg.get('wordId'))
  if cmd=='login':return self.api.login(arg.get('username'),arg.get('password'),arg.get('saved',False))
  if cmd=='disconnect':self.api=Transkribus();return {'connected':False}
  if cmd=='pull':return self.pull(arg['pageNr'])
  if cmd=='upload':return self.upload(arg['pageNr'])
  raise ValueError('Unknown command')
if __name__=='__main__':
 backend=None
 for line in sys.stdin:
  req={}
  try:
   req=json.loads(line)
   if backend is None:backend=Backend(os.environ.get('SYRIAC_WORKSPACE'))
   result=backend.handle(req);answer={'id':req.get('id'),'ok':True,'result':result}
  except Exception as error:
   # No token, password, request body or stack trace is emitted.
   answer={'id':req.get('id'),'ok':False,'error':str(error)[:900]}
  print(json.dumps(answer,ensure_ascii=False),flush=True)
