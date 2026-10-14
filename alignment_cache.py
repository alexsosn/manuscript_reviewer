"""Revision-aware cached alignment and explicit cross-page gaps/overlaps."""
import json,hashlib
from alignment import mapped

def input_digest(lines):return hashlib.sha256(json.dumps(lines,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def load_cached(folder,nr,lines):
 try:
  entry=json.loads((folder/f'{nr}.json').read_text())
  if entry.get('version')==2 and entry.get('inputDigest')==input_digest(lines):return entry['result']
 except (FileNotFoundError,ValueError,KeyError):pass
 return None

def continuity(previous,current,corpus):
 a=(previous or {}).get('coverage',{}).get('referenceEnd');b=current.get('coverage',{}).get('referenceStart')
 if a is None or b is None:return {'status':'unverified','message':'Unresolved page alignment: reference continuity has not been verified.'}
 if a!=b:
  end_book=corpus.verse_at(max(0,a-1))['book'];start_book=corpus.verse_at(b)['book']
  if end_book!=start_book:
   return {'status':'book-transition','message':f'Book transition: {end_book} → {start_book}. Check the manuscript book order and both passage boundaries; intervening books in the reference edition are not treated as missing manuscript text.'}
 if a==b or not mapped(corpus.raw[min(a,b):max(a,b)])[0]:return {'status':'continuous','message':'No reference gap at the preceding page boundary.'}
 span=corpus.raw[min(a,b):max(a,b)].strip();v=corpus.verse_at(min(a,b))
 if b>a:return {'status':'gap','message':f'Reference gap after the preceding page: {v["book"]} {v["chapter"]}:{v["verse"]}. Check for missed OCR or an incorrect passage boundary.','text':span,'characters':len(mapped(span)[0])}
 return {'status':'overlap','message':'Reference overlap or reversed passage order at the preceding page boundary. Check both page boundaries.','text':span,'characters':len(mapped(span)[0])}
