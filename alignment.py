"""Pinned, continuous character comparison after passage location.

Whitespace is the only ignored content. NFD preserves marks and punctuation.
Every reference character in the selected span is consumed, including omissions.
"""
import unicodedata
from difflib import SequenceMatcher

def mapped(text):
 chars=[];offsets=[]
 for i,ch in enumerate(text):
  for c in unicodedata.normalize('NFD',ch):
   if not c.isspace():chars.append(c);offsets.append(i)
 return ''.join(chars),offsets

def global_path(query,reference):
 n,m=len(query),len(reference)
 if (n+1)*(m+1)>20000000:raise ValueError('Character comparison too large; narrow the reference passage')
 trace=bytearray((n+1)*(m+1));previous=list(range(m+1))
 for j in range(1,m+1):trace[j]=2
 for i,a in enumerate(query,1):
  current=[i]+[0]*m;trace[i*(m+1)]=1
  for j,b in enumerate(reference,1):
   sub=previous[j-1]+(a!=b);delete=previous[j]+1;insert=current[j-1]+1
   if sub<=delete and sub<=insert:current[j]=sub;trace[i*(m+1)+j]=0
   elif delete<=insert:current[j]=delete;trace[i*(m+1)+j]=1
   else:current[j]=insert;trace[i*(m+1)+j]=2
  previous=current
 cost=previous[m];i,j=n,m;edges=[None]*(n+1);edges[n]=m
 while i or j:
  step=trace[i*(m+1)+j]
  if step==0:i-=1;j-=1;edges[i]=j
  elif step==1:i-=1;edges[i]=j
  else:j-=1
 edges[0]=0
 return edges,cost

def differences(ocr,reference):
 a,am=mapped(ocr);b,bm=mapped(reference);out=[]
 for op,i,j,k,l in SequenceMatcher(None,a,b,autojunk=False).get_opcodes():
  if op=='equal':continue
  left,right=a[i:j],b[k:l];chars=left+right
  kind='diacritics' if chars and all(unicodedata.category(c).startswith('M') for c in chars) else 'punctuation' if chars and all(unicodedata.category(c).startswith('P') for c in chars) else 'text'
  out.append({'operation':op,'kind':kind,'ocr':left,'reference':right,'ocrStart':am[i] if i<len(am) else len(ocr),'ocrEnd':am[j-1]+1 if j>i else am[i] if i<len(am) else len(ocr),'referenceStart':bm[k] if k<len(bm) else len(reference),'referenceEnd':bm[l-1]+1 if l>k else bm[k] if k<len(bm) else len(reference)})
 return out
