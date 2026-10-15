"""Offline English comparisons, anchored by verses without inventing word alignment."""
from pathlib import Path
import json,bisect
class Translations:
 def __init__(self,folder):
  self.versions={}
  for name in ('murdock','etheridge'):
   path=Path(folder)/(name+'.json')
   if path.exists():self.versions[name]=json.loads(path.read_text())
 def span(self,corpus,start,end):
  if start is None or end is None or end<=start:return []
  first=max(0,bisect.bisect_right(corpus.verse_starts,start)-1)
  verses=[v for v in corpus.verses[first:] if v['start']<end and v['end']>start]
  result=[]
  for version in ('murdock','etheridge'):
   data=self.versions.get(version,{});entries=[];seen=set();missing=[]
   for v in verses:
    chapter=f"{v['book']} {v['chapter']}";rows=data.get('chapters',{}).get(chapter,[])
    hits=[r for r in rows if r['start']<=v['verse']<=r['end']]
    if not hits:missing.append(f"{chapter}:{v['verse']}")
    for row in hits:
     key=(chapter,row['start'],row['end'])
     if key in seen:continue
     seen.add(key);address=f"{chapter.replace('_',' ')}:{row['start']}"+(f"–{row['end']}" if row['end']!=row['start'] else '')
     entries.append({'address':address,'text':row['text'],'segmentation':row.get('segmentation','verse'),'note':row.get('note','')})
   result.append({'version':version,'name':data.get('name',version.title()),'entries':entries,'missing':list(dict.fromkeys(missing)),'source':data.get('source','')})
  return result
