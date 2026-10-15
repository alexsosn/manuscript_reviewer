"""Import the public-domain Murdock and Etheridge texts; retain source segmentation."""
from pathlib import Path
from urllib.parse import urljoin,urlparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from copy import deepcopy
import re,json,urllib.request,hashlib,time,sys
from lxml import html
APP=Path(__file__).resolve().parents[1]
BASE='https://aramaicnewtestament.org/peshitta/'
def document(raw):
 try:text=raw.decode('utf-8')
 except UnicodeDecodeError:text=raw.decode('windows-1252',errors='replace')
 return html.fromstring(text)
def clean(text):return re.sub(r'\s+',' ',text).strip()
def chapter_links(raw,url):
 root=document(raw)
 return sorted({urljoin(url,a.get('href')).replace('http:','https:') for a in root.xpath('//a[@href]') if re.search(r'/[^/]+\.htm$',urljoin(url,a.get('href'))) and urlparse(urljoin(url,a.get('href'))).netloc=='aramaicnewtestament.org' and '/peshitta/'+url.split('/peshitta/')[1].split('/')[0]+'/' in urljoin(url,a.get('href'))})
def parse_chapter(raw,version,chapter,last):
 root=document(raw);tables=root.xpath('//table[contains(@class,"contenttable")]')
 if not tables:raise ValueError('No translation content table')
 cells=tables[0].xpath('./tr[2]/td')
 if not cells:raise ValueError('No translation text cell')
 cell=deepcopy(cells[0])
 for el in cell.xpath('.//script|.//style|.//sup|.//form|.//iframe|.//*[starts-with(@id,"dropinbox") and not(ancestor::*[starts-with(@id,"dropinbox")])]'):el.drop_tree()
 if version=='murdock':
  for el in cell.xpath('.//strong|.//b'):
   number=clean(el.text_content())
   if number.isdigit():el.text='\n@@VERSE '+number+'@@ ';[el.remove(c) for c in list(el)]
  text=cell.text_content();text=re.split(r'\* (?:The Syriac punctuation|This verse|In the Syriac,)',text,maxsplit=1)[0];matches=list(re.finditer(r'@@VERSE (\d+)@@',text));rows=[]
  for i,m in enumerate(matches):
   verse=int(m[1]);body=clean(text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)])
   if not body:raise ValueError('Empty verse')
   previous=next((r for r in rows if r['start']==verse),None)
   if previous:
    previous['text']+=' '+body;previous['note']='Source repeats this verse number; both printed segments are retained.'
   else:rows.append({'start':verse,'end':verse,'text':body})
  if not rows:raise ValueError('No numbered verses')
  return rows
 for br in cell.xpath('.//br'):br.tail='\n'+(br.tail or '')
 text=cell.text_content();matches=list(re.finditer(r'(?m)^\s*(?:[IVXLCDM]+[.\-–]*\s+)?'+str(chapter)+r'\s*:\s*(\d+)\s*\n',text));rows=[]
 if not matches:return [{'start':1,'end':last,'text':clean(text),'segmentation':'chapter'}]
 for i,m in enumerate(matches):
  first=int(m[1]);end=int(matches[i+1][1])-1 if i+1<len(matches) else last
  if end<first:return [{'start':1,'end':last,'text':clean(text),'segmentation':'chapter','note':'Source paragraph numbering differs from SyrNT; chapter shown intact.'}]
  body=clean(text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)])
  rows.append({'start':first,'end':end,'text':body,'segmentation':'paragraph'})
 # Some chapters continue a paragraph before the first numbered heading.
 prefix=clean(text[:matches[0].start()])
 if rows[0]['start']>1 and prefix:rows.insert(0,{'start':1,'end':rows[0]['start']-1,'text':prefix,'segmentation':'paragraph'})
 return rows

def main():
 cache=APP/'downloads/translations';cache.mkdir(parents=True,exist_ok=True);out=APP/'data/translations';out.mkdir(parents=True,exist_ok=True)
 books={re.sub('[^a-z0-9]','',p.stem.lower()):p.stem for p in (APP/'data/syrnt-source/plain/0.1').glob('*.txt')};ends={}
 for book in books.values():
  chapter=0
  for line in (APP/'data/syrnt-source/plain/0.1'/f'{book}.txt').read_text().splitlines():
   m=re.match(r'^\S+\s+(\d+)$',line)
   if m:chapter=int(m[1]);continue
   m=re.match(r'^(\d+)\s+',line)
   if m and chapter:ends[(book,chapter)]=int(m[1])
 def fetch(url):
  file=cache/(hashlib.sha256(url.encode()).hexdigest()+'.html')
  if file.exists():return file.read_bytes()
  req=urllib.request.Request(url,headers={'User-Agent':'ManuscriptReviewer/0.7 (public-domain translation import)'})
  with urllib.request.urlopen(req,timeout=45) as response:raw=response.read()
  file.write_bytes(raw);time.sleep(.15);return raw
 for version in ('murdock','etheridge'):
  seed=BASE+version+'/gospel/matthew_1.htm';links=chapter_links(fetch(seed),seed);data={};errors=[];sources=[]
  def task(url):
   stem=Path(urlparse(url).path).stem;slug,ch=stem.rsplit('_',1) if re.search(r'_\d+$',stem) else (stem,'1');book=books.get(re.sub('[^a-z0-9]','',slug.lower()));chapter=int(ch)
   if not book:raise ValueError('Unknown book '+slug)
   raw=fetch(url);rows=parse_chapter(raw,version,chapter,ends[(book,chapter)])
   return book,chapter,rows,{'url':url,'sha256':hashlib.sha256(raw).hexdigest()}
  with ThreadPoolExecutor(max_workers=3) as pool:
   futures={pool.submit(task,url):url for url in links}
   for i,future in enumerate(as_completed(futures),1):
    try:
     book,ch,rows,source=future.result();data[f'{book} {ch}']=rows;sources.append(source)
    except Exception as e:errors.append({'url':futures[future],'error':str(e)})
    if i%40==0:print(version,i,'/',len(links),flush=True)
  missing=[f'{b} {ch}' for b,ch in ends if f'{b} {ch}' not in data]
  corrections=[]
  if version=='murdock' and (out/'murdock-revelation-2.json').exists():
   patch=json.loads((out/'murdock-revelation-2.json').read_text());data['Revelation 2']=patch['rows'];corrections.append({k:v for k,v in patch.items() if k!='rows'}|{'chapter':'Revelation 2','reason':'Website contains incorrect chapter text.'})
  result={'corrections':corrections,'name':'James Murdock' if version=='murdock' else 'John Wesley Etheridge','license':'Public domain (historical translation); site design excluded','source':seed,'chapters':dict(sorted(data.items())),'missingChapters':missing,'sources':sources,'errors':errors}
  (out/f'{version}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(version,'chapters',len(data),'missing',len(missing),'errors',errors,flush=True)
if __name__=='__main__':main()
