"""SEDRA/SyrNT word analyses, indexed against the identical plain reference text."""
from pathlib import Path
from bisect import bisect_right,bisect_left
from collections import defaultdict
import re,sys
from corpus import letters,LEXMAP
FIELDS='word lexeme root sp vs vt st nu ps gn prefix suffix prtyp ntyp ptctyp sfps sfgn sfnu sfcontract'.split()
LABELS={'s':'singular','p':'plural','m':'masculine','f':'feminine','c':'common gender','1':'1st person','2':'2nd person','3':'3rd person'}
def read_feature(file):
 body=Path(file).read_text().split('\n\n',1)[1].splitlines();result={};node=0
 for row in body:
  if '\t' in row:
   nodes,value=row.split('\t',1);parts=nodes.split('-');begin=int(parts[0]);end=int(parts[-1])
  else:begin=end=node+1;value=row
  value=sys.intern(value)
  for n in range(begin,end+1):result[n]=value
  node=end
 return result
class Morphology:
 def __init__(self,path,raw):
  self.features={name:read_feature(Path(path)/(name+'.tf')) for name in FIELDS}
  self.tokens=list(re.finditer(r'\S+',raw));self.starts=[t.start() for t in self.tokens];self.ends=[t.end() for t in self.tokens];self.forms=defaultdict(list)
  if len(self.tokens)!=len(self.features['word']):raise ValueError('Reference/morphology word count mismatch')
  for i,t in enumerate(self.tokens,1):
   if letters(t.group())!=letters(self.features['word'][i]):raise ValueError('Reference/morphology word mismatch at '+str(i))
   self.forms[letters(t.group())].append(i)
 def fragments(self,start,end):
  result=[]
  for i in range(bisect_right(self.ends,start),bisect_left(self.starts,end)):
   a,b=max(start,self.starts[i]),min(end,self.ends[i]);token=self.tokens[i]
   if a<b:result.append({'start':a-start,'end':b-start,'text':token.string[a:b],'word':token.group(),'wordId':i+1})
  return result
 def analysis(self,node):
  f={k:v.get(node,'') for k,v in self.features.items()};grammar=[]
  def add(key):
   value=f[key]
   if value and value!='NA':grammar.append(LABELS.get(value,value))
  add('sp')
  if f['ntyp']=='proper':grammar.append('proper name')
  for key in ['vs','vt','ptctyp','ps','gn','nu','st','prtyp']:add(key)
  affixes=[]
  if f['prefix']:affixes.append({'label':'Prefix','text':f['prefix']})
  if f['suffix']:
   features=[LABELS.get(f[k],f[k]) for k in ['sfps','sfgn','sfnu'] if f[k] not in ('','NA')]
   affixes.append({'label':'Suffix'+(' · '+', '.join(features) if features else ''),'text':f['suffix']})
  return {'wordId':node,'form':f['word'],'lemma':f['lexeme'],'root':f['root'],'grammar':', '.join(grammar),'affixes':affixes,'lexicalKey':''.join(LEXMAP.get(ch,ch) for ch in letters(f['lexeme']))}
 def lookup(self,word,node=None):
  if node is not None:
   node=int(node)
   if node not in self.features['word'] or letters(word)!=letters(self.tokens[node-1].group()):raise ValueError('Word analysis does not match this reference token')
   return [self.analysis(node)]
  seen=set();out=[]
  for n in self.forms.get(letters(word),[]):
   a=self.analysis(n);signature=(a['lemma'],a['root'],a['grammar'],str(a['affixes']))
   if signature not in seen:seen.add(signature);out.append(a)
   if len(out)>=8:break
  return out
