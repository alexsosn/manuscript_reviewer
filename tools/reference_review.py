#!/usr/bin/env python3
"""Page-local SyrNT review comments. Remote writes are restricted to pages 3/4."""
import sys,json,re,hashlib,unicodedata
from pathlib import Path
from difflib import SequenceMatcher
from copy import deepcopy
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from corpus import Corpus,normalized_map
from pagexml import parse,N,server_metadata,page_signature
from transkribus import Transkribus
from lxml import etree as E
APP=Path(__file__).resolve().parents[1]
COLL=2536248;DOC=19244795;PAGES=(3,4)
MARKER='SyrNT review'

def escape(value):
 return ''.join('\\u%04x'%ord(c) if c in ':;{}\\\n\r\t' else c for c in value)
def utf16(text):return len(text.encode('utf-16-le'))//2

def word_spans(text):
 return [(m.start(),m.end()) for m in re.finditer(r'\S+',text)]
def expand(text,start,end):
 spans=word_spans(text);hit=[(a,b) for a,b in spans if a<end and b>start]
 return (hit[0][0],hit[-1][1]) if hit else (start,end)

def differences(text,ref,verse_for_word=None):
 """Compare a whole page, ignoring physical line breaks during matching."""
 from bisect import bisect_left
 reference=ref['reference'];a,am=normalized_map(text);b,bm=normalized_map(reference);out=[]
 words=ref.get('words') or [{'start':s,'end':e,'word':reference[s:e]} for s,e in word_spans(reference)]
 ops=SequenceMatcher(None,a,b,autojunk=False).get_opcodes();b_to_a={};a_to_b={}
 for op,i,j,k,l in ops:
  if op=='equal':
   for x,y in zip(range(i,j),range(k,l)):b_to_a[y]=x;a_to_b[x]=y
 ranges=[(bisect_left(bm,w['start']),bisect_left(bm,w['end']),w) for w in words]
 for op,i,j,k,l in ops:
  if op=='equal':continue
  rw=[w for x,y,w in ranges if x<l and y>k]
  matched=[b_to_a[pos] for x,y,w in ranges if w in rw for pos in range(x,y) if pos in b_to_a]
  missing=i==j and not matched
  start=am[i] if i<len(am) else len(text);end=am[j-1]+1 if j>i else start
  if i==j:
   if matched:start=am[min(matched)];end=am[max(matched)]+1
   else:
    spans=word_spans(text);neighbor=next(((s,e) for s,e in spans if e>start),spans[-1] if spans else None)
    if neighbor is None:continue
    start,end=neighbor
  start,end=expand(text,start,end)
  if not missing:
   related={a_to_b[pos] for pos in range(bisect_left(am,start),bisect_left(am,end)) if pos in a_to_b}
   rw=[w for x,y,w in ranges if w in rw or any(x<=pos<y for pos in related)]
  refwords=list(dict.fromkeys(w['word'] for w in rw));addresses=list(dict.fromkeys(verse_for_word(w) if verse_for_word else ref['address'] for w in rw))
  spelling=' '.join(refwords) if refwords else '∅ (no corresponding word in SyrNT)'
  if missing:spelling+=(' (missing from transcription; '+('after' if i==len(a) else 'before')+' “'+text[start:end]+'”)')
  passage='; '.join(addresses) or ref['address']
  note='Reference spelling: '+spelling+'\nPassage: '+passage
  item={'start':start,'end':end,'offset':utf16(text[:start]),'length':utf16(text[start:end]),'referenceSpelling':spelling,'passage':passage,'kind':'missing in transcription' if missing else 'extra in transcription' if not refwords else 'difference','comment':note}
  if not any(e['start']==start and e['end']==end and e['comment']==note for e in out):out.append(item)
 return out

def annotate(raw,alignment,corpus):
 tree=parse(raw);lookup={r['id']:r for r in alignment['lines']};report=[];lines=[];ocr='';reference='';words={}
 for ident in lookup:
  line=next(l for l in tree.findall('.//p:TextLine',N) if l.get('id')==ident);ref=lookup[ident];text=line.findtext('p:TextEquiv/p:Unicode','',N)
  lines.append((line,len(ocr),len(ocr)+len(text)));ocr+=text+'\n'
  for w in ref.get('words',[]):
   node=w['wordId'];a,b=len(reference)+w['start'],len(reference)+w['end']
   if node in words:words[node]['end']=b
   else:words[node]={**w,'start':a,'end':b}
  reference+=ref['reference']+'\n'
 def verse(word):
  node=word['wordId'];v=corpus.verse_at(corpus.morphology.starts[node-1])
  return f"{v['book'].replace('_',' ')} {v['chapter']}:{v['verse']}"
 global_ref={'reference':reference,'words':list(words.values()),'address':alignment['passage']}
 for item in differences(ocr,global_ref,verse):
  for line,start,end in lines:
   a,b=max(start,item['start']),min(end,item['end'])
   if a>=b:continue
   text=line.findtext('p:TextEquiv/p:Unicode','',N);offset=utf16(ocr[start:a]);length=utf16(ocr[a:b]);custom=line.get('custom','')
   tag=f"comment {{offset:{offset}; length:{length}; comment:{escape(item['comment'])};}}"
   if tag not in custom:line.set('custom',(custom+' '+tag).strip())
   report.append({'lineId':line.get('id'),'ocr':ocr[a:b],**item,'offset':offset,'length':length})
 old=parse(raw);clean=deepcopy(tree)
 for before,after in zip(old.findall('.//p:TextLine',N),clean.findall('.//p:TextLine',N)):
  if 'custom' in before.attrib:after.set('custom',before.get('custom'))
  else:after.attrib.pop('custom',None)
 assert page_signature(E.tostring(clean))==page_signature(raw),'Annotation changed text/layout'
 return E.tostring(tree,encoding='UTF-8',xml_declaration=True),report

def main():
 mode=sys.argv[1];folder=Path(sys.argv[2]).resolve();folder.mkdir(parents=True,exist_ok=True)
 api=Transkribus();api.login(saved=True)
 if mode=='prepare':
  corpus=Corpus(APP/'data');manifest=[]
  for nr in PAGES:
   raw,info=api.pull(COLL,DOC,nr);raw=server_metadata(raw,info)
   from pagexml import model
   m=model(raw,'page.xml','server');regions=sorted(m['regions'],key=lambda r:float(sum(x for x,y in r['coords'])/max(1,len(r['coords']))),reverse=True)
   # Keep existing line order within the two body regions; exclude small marginal regions.
   body=sorted(regions,key=lambda r:len(r['lines']),reverse=True)[:2];body.sort(key=lambda r:sum(x for x,y in r['coords'])/len(r['coords']),reverse=True)
   lines=[{'id':l['id'],'text':l['text']} for r in body for l in r['lines']]
   alignment=corpus.align(lines)
   if alignment['score']<.85:raise ValueError(f'Page {nr}: alignment too uncertain ({alignment["score"]}); no upload prepared')
   annotated,report=annotate(raw,alignment,corpus)
   validation=parse(annotated)
   for meta in validation.findall('.//p:TranskribusMetadata',N):meta.getparent().remove(meta)
   E.XMLSchema(E.parse(str(APP/'data/pagecontent-2013.xsd'))).assertValid(validation)
   (folder/f'page_{nr}_before.xml').write_bytes(raw);(folder/f'page_{nr}_annotated.xml').write_bytes(annotated)
   (folder/f'page_{nr}_review.json').write_text(json.dumps({'alignment':alignment,'differences':report},ensure_ascii=False,indent=2))
   manifest.append({'pageNr':nr,'info':info,'sha256':hashlib.sha256(annotated).hexdigest(),'comments':len(report),'alignmentScore':alignment['score'],'passage':alignment['passage']})
   print(json.dumps({k:v for k,v in manifest[-1].items() if k not in ('sha256','info')},ensure_ascii=False))
  (folder/'manifest.json').write_text(json.dumps(manifest,indent=2))
 elif mode=='upload':
  manifest=json.loads((folder/'manifest.json').read_text());assert [e['pageNr'] for e in manifest]==list(PAGES)
  for entry in manifest:
   nr=entry['pageNr'];receipt=folder/f'page_{nr}_receipt.json'
   if receipt.exists():raise ValueError(f'Page {nr} already has an upload receipt; do not repeat')
   raw=(folder/f'page_{nr}_annotated.xml').read_bytes();assert hashlib.sha256(raw).hexdigest()==entry['sha256']
   # Existing upload path version-checks and compares all PAGE custom attributes on read-back.
   after,result=api.upload(COLL,DOC,nr,raw,entry['info']);receipt.write_text(json.dumps(result,indent=2))
   if not result['verified']:raise ValueError(result['warning'])
   after=server_metadata(after,{**entry['info'],'tsId':result['tsId']})
   (folder/f'page_{nr}_after.xml').write_bytes(after);print(json.dumps(result))
 else:raise ValueError('Use prepare or upload')
if __name__=='__main__':main()
