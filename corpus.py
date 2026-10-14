"""Offline reference alignment, preserving PAGE line boundaries and split words."""
import json,re,unicodedata,html,bisect
from collections import defaultdict,Counter
from difflib import SequenceMatcher
from pathlib import Path

SYRIAC='ܐܒܓܕܗܘܙܚܛܝܟܠܡܢܣܥܦܨܩܪܫܬ'
LEXMAP=dict(zip(SYRIAC,')bgdhwzḥṭyklmns(pṣqršt'));LEXMAP['ܤ']='s'
def clean_gloss(label,key):
 text=html.unescape(re.sub('<[^>]+>','',label)).strip()
 if text.startswith(key):text=text[len(key):].strip()
 if text.startswith('(') and text.endswith(')'):text=text[1:-1]
 return ' · '.join(dict.fromkeys(part.strip() for part in text.split(' / ') if part.strip()))
def letters(s):return ''.join(ch for ch in unicodedata.normalize('NFD',s) if unicodedata.category(ch).startswith('L'))
def normalized_map(raw):
 text=[];offsets=[]
 for i,ch in enumerate(raw):
  for c in unicodedata.normalize('NFD',ch):
   if unicodedata.category(c).startswith('L'):text.append(c);offsets.append(i)
 return ''.join(text),offsets

def semiglobal(query,reference):
 """Character edit distance with free reference prefix/suffix; return boundary map.

Boundary positions are monotone. Each manuscript boundary partitions a single
reference span; words crossing that boundary are split, never duplicated.
"""
 n,m=len(query),len(reference)
 if not n:return [],0,0,0
 if (n+1)*(m+1)>20000000:raise ValueError('Passage too large; select a book or reference start')
 trace=bytearray((n+1)*(m+1));previous=list(range(m+1))
 previous=[0]*(m+1)
 for i,a in enumerate(query,1):
  current=[i]+[0]*m;trace[i*(m+1)]=1
  for j,b in enumerate(reference,1):
   sub=previous[j-1]+(a!=b);delete=previous[j]+1;insert=current[j-1]+1
   if sub<=delete and sub<=insert:current[j]=sub;trace[i*(m+1)+j]=0
   elif delete<=insert:current[j]=delete;trace[i*(m+1)+j]=1
   else:current[j]=insert;trace[i*(m+1)+j]=2
  previous=current
 end=min(range(m+1),key=lambda j:previous[j]);cost=previous[end];i,j=n,end;edges=[None]*(n+1);edges[n]=j
 while i>0:
  step=trace[i*(m+1)+j]
  if step==0:i-=1;j-=1;edges[i]=j
  elif step==1:i-=1;edges[i]=j
  else:j-=1
 start=j;edges[0]=start
 return edges,start,end,cost

class Corpus:
 def __init__(self,data):
  self.verses=[];self.books=[];self.raw='';self.ranges=[]
  plain=Path(data)/'syrnt-source/plain/0.1'
  order=['Matthew','Mark','Luke','John','Acts','Romans','1_Corinthians','2_Corinthians','Galatians','Ephesians','Philippians','Colossians','1_Thessalonians','2_Thessalonians','1_Timothy','2_Timothy','Titus','Philemon','Hebrews','James','1_Peter','2_Peter','1_John','2_John','3_John','Jude','Revelation']
  for book in order:
   f=plain/(book+'.txt')
   if not f.exists():continue
   begin=len(self.raw);chapter=0
   for line in f.read_text().splitlines():
    chapter_match=re.match(r'^\S+\s+(\d+)$',line)
    if chapter_match:chapter=int(chapter_match[1]);continue
    match=re.match(r'^(\d+)\s+(.+)$',line)
    if not match or not chapter:continue
    verse=int(match[1]);text=match[2].strip();start=len(self.raw);self.raw+=text+' '
    self.verses.append({'book':book,'chapter':chapter,'verse':verse,'text':text,'start':start,'end':len(self.raw)})
   self.books.append({'name':book,'start':begin,'end':len(self.raw)})
  self.text,self.offsets=normalized_map(self.raw);self.verse_starts=[v['start'] for v in self.verses]
  self.grams=defaultdict(list)
  for i in range(len(self.text)-7):
   key=self.text[i:i+8]
   if len(self.grams[key])<100:self.grams[key].append(i)
  entries=json.loads((Path(data)/'sycgloss-source/lexeme.json').read_text())
  self.lex=defaultdict(list)
  for item in entries:
   val=item.get('value','').strip()
   if val:
    entry={'term':item['term'],'transliteration':val,'headword':''.join({v:k for k,v in LEXMAP.items() if k!='ܤ'}.get(ch,ch) for ch in val),'gloss':clean_gloss(item.get('label',''),val),'etymologies':item.get('etymologies',[])}
    if not any(r['term']==entry['term'] and r['gloss']==entry['gloss'] for r in self.lex[val]):self.lex[val].append(entry)
  self.lexkeys=list(self.lex)
  from morphology import Morphology
  self.morphology=Morphology(Path(data)/'syrnt-source/tf/0.1',self.raw)
 def verse_at(self,raw):return self.verses[max(0,bisect.bisect_right(self.verse_starts,raw)-1)]
 def lookup(self,word,word_id=None):
  normalized=letters(word);key=''.join(LEXMAP.get(ch,ch) for ch in normalized)
  queries=[(key,'exact')]
  # Clitic stripping is a hypothesis, not an asserted morphological analysis.
  for count in (1,2):
   if len(key)>count+2 and all(ch in 'wbdl' for ch in key[:count]):queries.append((key[count:],'possible clitic'))
  hits=[];seen=set()
  for k,kind in queries:
   for entry in self.lex.get(k,[]):
    ident=(entry['term'],entry['gloss'])
    if ident not in seen:hits.append({**entry,'match':kind,'score':1});seen.add(ident)
  if len(hits)<8 and len(key)>=3:
   candidates=sorted(((SequenceMatcher(None,key,k).ratio(),k) for k in self.lexkeys if abs(len(k)-len(key))<=2),reverse=True)[:6]
   for score,k in candidates:
    if score<.55:continue
    for entry in self.lex[k][:2]:
     ident=(entry['term'],entry['gloss'])
     if ident not in seen:hits.append({**entry,'match':'similar lexeme','score':round(score,3)});seen.add(ident)
  analyses=self.morphology.lookup(word,word_id)
  for analysis in analyses:
   analysis['glosses']=list(dict.fromkeys(e['gloss'] for e in self.lex.get(analysis['lexicalKey'],[]) if e['gloss']))
  return {'query':word,'analyses':analyses,'lookupKey':key,'entries':[h for h in hits[:16] if h['gloss']], 'note':'Lexeme candidates; inflected forms and manuscript variants may not have exact headword matches.'}
 def align(self,lines,book='',anchor='',end_anchor=''):
  query='';segments=[]
  for line in lines:
   value=letters(line['text']);segments.append((line['id'],len(query),len(query)+len(value)));query+=value
  if len(query)<12:return {'lines':[],'score':0,'warning':'Not enough body text to identify a passage.'}
  lo,hi=0,len(self.text)
  if book:
   b=next(b for b in self.books if b['name']==book);lo=bisect.bisect_left(self.offsets,b['start']);hi=bisect.bisect_left(self.offsets,b['end'])
  if anchor:
   match=re.match(r'(?:(.*?)\s+)?(\d+):(\d+)$',anchor.strip())
   if not match:raise ValueError('Reference start must be Book chapter:verse, or chapter:verse with a book selected')
   abook=match[1] or book
   v=next((v for v in self.verses if v['book']==abook and v['chapter']==int(match[2]) and v['verse']==int(match[3])),None)
   if not v:raise ValueError('Reference start was not found in the corpus')
   lo=max(lo,bisect.bisect_left(self.offsets,v['start'])-100);hi=min(hi,lo+len(query)+900)
  votes=Counter()
  for q in range(0,len(query)-7,11):
   positions=[p for p in self.grams.get(query[q:q+8],[]) if lo<=p<hi]
   if not positions or len(positions)>45:continue
   weight=1/(len(positions)**.5)
   for p in positions:votes[(p-q)//100]+=weight
  if not votes and not anchor:return {'lines':[],'score':0,'warning':'No reliable passage anchors. Select the book and enter a reference start.'}
  candidates=[bin*100 for bin,_ in votes.most_common(8)] if votes else [lo]
  scored=[]
  for candidate in candidates:
   a=max(lo,candidate-180);b=min(hi,candidate+len(query)+max(350,len(query)//3))
   score=SequenceMatcher(None,query,self.text[a:b],autojunk=False).ratio();scored.append((score,a,b))
  _,a,b=max(scored);window=self.text[a:b];edges,start,end,cost=semiglobal(query,window)
  letter_confidence=max(0,1-cost/max(1,len(query),end-start))
  from alignment import mapped,global_path,differences
  # Locate by letters, then pin both ends and compare every mark/punctuation.
  rawstart=self.offsets[a+start]
  end_index=a+end
  rawend=self.offsets[end_index] if end_index<len(self.offsets) else len(self.raw)
  passage_start=rawstart
  if end_anchor:
   if not anchor:raise ValueError('Enter a reference start as well as the reference end')
   endmatch=re.match(r'(?:(.*?)\s+)?(\d+):(\d+)$',end_anchor.strip())
   if not endmatch:raise ValueError('Reference end must be Book chapter:verse or chapter:verse')
   endbook=endmatch[1] or abook
   endverse=next((verse for verse in self.verses if verse['book']==endbook and verse['chapter']==int(endmatch[2]) and verse['verse']==int(endmatch[3])),None)
   if not endverse or endverse['end']<=v['start']:raise ValueError('Reference end precedes the start or was not found')
   passage_start=rawstart=v['start'];rawend=endverse['end']
  full_reference=self.raw[rawstart:rawend]
  if end_anchor:
   _,letter_cost=global_path(query,letters(full_reference));letter_confidence=max(0,1-letter_cost/max(1,len(query),len(letters(full_reference))))
  full_query='';segments=[]
  for line in lines:
   value,_=mapped(line['text']);segments.append((line['id'],len(full_query),len(full_query)+len(value)));full_query+=value
  ref_chars,ref_offsets=mapped(full_reference)
  edges,cost=global_path(full_query,ref_chars);items=[]
  confidence=max(0,1-cost/max(1,len(full_query),len(ref_chars)))
  def raw_boundary(q):
   pos=edges[q]
   return passage_start+(ref_offsets[pos] if pos<len(ref_offsets) else len(full_reference))

  for ident,qstart,qend in segments:
   if qstart==qend:items.append({'id':ident,'reference':'','address':'','splitStart':False,'splitEnd':False,'score':0});continue
   rawstart,rawend=raw_boundary(qstart),raw_boundary(qend)
   span=self.raw[rawstart:rawend];leading=len(span)-len(span.lstrip());text=span.strip();words=self.morphology.fragments(rawstart+leading,rawstart+leading+len(text));vs=self.verse_at(rawstart);ve=self.verse_at(max(rawstart,rawend-1))
   address=f"{vs['book'].replace('_',' ')} {vs['chapter']}:{vs['verse']}"
   if vs!=ve:address+=f"–{ve['chapter']}:{ve['verse']}"
   split=lambda off:0<off<len(self.raw) and self.raw[off-1].isalpha() and self.raw[off].isalpha()
   line=next(l for l in lines if l['id']==ident)
   ratio=SequenceMatcher(None,letters(line['text']),letters(text),autojunk=False).ratio()
   items.append({'id':ident,'reference':text,'words':words,'address':address,'splitStart':split(rawstart),'splitEnd':split(rawend),'score':round(SequenceMatcher(None,mapped(line['text'])[0],mapped(text)[0],autojunk=False).ratio(),3),'changes':differences(line['text'],text),'referenceStart':rawstart,'referenceEnd':rawend})
  joined=''.join(item['reference'] for item in items)
  assert mapped(joined)[0]==ref_chars,'Reference span was omitted at a line boundary'
  changes=differences(''.join(l['text'] for l in lines),full_reference)
  missing=sum(len(c['reference']) for c in changes if c['operation']=='insert')
  extra=sum(len(c['ocr']) for c in changes if c['operation']=='delete')
  return {'lines':items,'score':round(confidence,3),'letterScore':round(letter_confidence,3),'passage':items[0]['address']+' → '+items[-1]['address'],
   'warning':'Low-confidence passage location: verify the book and reference start; all differences remain visible.' if letter_confidence<.85 else '',
   'coverage':{'boundsSource':'manual verses' if end_anchor else 'automatic; verify page boundaries','referenceStart':passage_start,'referenceEnd':passage_start+len(full_reference),'referenceCharacters':len(ref_chars),'assignedReferenceCharacters':len(mapped(joined)[0]),'unassignedReferenceCharacters':0,'missingReferenceCharacters':missing,'extraOcrCharacters':extra,'differenceGroups':len(changes),'complete':True,'scope':'One continuous selected reference span; passage boundaries require review.'},
   'normalization':'Passage located by letters; comparison retains diacritics, punctuation and all other non-whitespace characters (NFD).'}
