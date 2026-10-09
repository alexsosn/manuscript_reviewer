#!/usr/bin/env python3
"""Convert only page 3/4 experiment comments to native unclear alternative/reason tags."""
import sys,re,json,hashlib
from pathlib import Path
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from transkribus import Transkribus
from pagexml import parse,N,server_metadata,page_signature
from tools.reference_review import escape,reference_tag,COLL,DOC,PAGES
from lxml import etree as E

def decode(value):return re.sub(r'\\u([0-9a-fA-F]{4})',lambda m:chr(int(m[1],16)),value)
def repair(raw):
 tree=parse(raw);count=0
 for line in tree.findall('.//p:TextLine',N):
  def fix(match):
   nonlocal count
   tag=match[0];prop=re.search(r'\bcomment\s*:\s*([^;]*);',tag)
   if not prop:return tag
   note=decode(prop[1]).strip()
   if not note.startswith('Reference spelling: ') or '\nPassage: ' not in note:return tag
   offset=re.search(r'\boffset\s*:\s*(\d+)',tag);length=re.search(r'\blength\s*:\s*(\d+)',tag)
   if not offset or not length:raise ValueError('Reference comment has no valid range')
   tag=reference_tag(int(offset[1]),int(length[1]),note)
   count+=1;return tag
  if 'custom' in line.attrib:line.set('custom',re.sub(r'\bcomment\s*\{[^{}]*\}',fix,line.get('custom')))
 old=parse(raw);clean=deepcopy(tree)
 for before,after in zip(old.findall('.//p:TextLine',N),clean.findall('.//p:TextLine',N)):
  if 'custom' in before.attrib:after.set('custom',before.get('custom'))
  else:after.attrib.pop('custom',None)
 assert page_signature(E.tostring(clean))==page_signature(raw),'Repair changed text/layout'
 return E.tostring(tree,encoding='UTF-8',xml_declaration=True),count

def main():
 mode=sys.argv[1];folder=Path(sys.argv[2]);folder.mkdir(parents=True,exist_ok=True)
 api=Transkribus();api.login(saved=True)
 if mode=='prepare':
  manifest=[]
  for nr in PAGES:
   raw,info=api.pull(COLL,DOC,nr);raw=server_metadata(raw,info);fixed,count=repair(raw)
   if not count:raise ValueError(f'Page {nr}: no experiment comments found; no upload prepared')
   (folder/f'page_{nr}_before.xml').write_bytes(raw);(folder/f'page_{nr}_annotated.xml').write_bytes(fixed)
   manifest.append({'pageNr':nr,'info':info,'sha256':hashlib.sha256(fixed).hexdigest(),'comments':count});print('Page',nr,':',count,'native reference annotations prepared')
  (folder/'manifest.json').write_text(json.dumps(manifest,indent=2))
 elif mode=='upload':
  nr=int(sys.argv[3]);assert nr in PAGES,'Writes restricted to pages 3/4'
  entries=json.loads((folder/'manifest.json').read_text());assert [e['pageNr'] for e in entries]==list(PAGES)
  entry=next(e for e in entries if e['pageNr']==nr);receipt=folder/f'page_{nr}_receipt.json'
  if receipt.exists():raise ValueError('Upload receipt exists; do not resubmit')
  raw=(folder/f'page_{nr}_annotated.xml').read_bytes();assert hashlib.sha256(raw).hexdigest()==entry['sha256']
  after,result=api.upload(COLL,DOC,nr,raw,entry['info']);receipt.write_text(json.dumps(result,indent=2))
  if not result['verified']:raise ValueError(result['warning'])
  after=server_metadata(after,{**entry['info'],'tsId':result['tsId']});(folder/f'page_{nr}_after.xml').write_bytes(after);print(json.dumps(result))
 else:raise ValueError('Use prepare FOLDER or upload FOLDER PAGE')
if __name__=='__main__':main()
