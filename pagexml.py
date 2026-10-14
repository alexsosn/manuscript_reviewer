"""Loss-minimizing PAGE edits; unknown elements and untouched confidence survive."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import re,hashlib,uuid,math
from lxml import etree as E
NS='http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15';N={'p':NS}
def tag(name):return '{'+NS+'}'+name
def parse(raw):return E.fromstring(raw,E.XMLParser(resolve_entities=False,no_network=True,remove_blank_text=False))
def normalize_custom_attributes(raw):
 """Keep tag values intact; the web editor rejects whitespace after the last }."""
 root=parse(raw);changed=False
 for el in root.iter():
  value=el.get('custom')
  if value is not None and value!=value.strip():el.set('custom',value.strip());changed=True
 return E.tostring(root,encoding='UTF-8',xml_declaration=True) if changed else raw

def validate_web_custom(raw):
 """Check custom blocks with the web editor's split-based grammar before writing."""
 for el in parse(raw).iter():
  value=el.get('custom','')
  if value!=value.strip():raise ValueError(f"Transkribus web editor cannot read trailing custom-tag whitespace on {el.get('id',el.tag)}. Prepare a fresh upload plan.")
  if value and not value.endswith('}'):raise ValueError('Incomplete Transkribus custom-tag block')
  for block in value.split('}'):
   if not block:continue
   parts=block.split('{')
   if len(parts)!=2 or not parts[0].strip():raise ValueError('Malformed Transkribus custom-tag block')
   for rule in parts[1].split(';'):
    if rule and (':' not in rule or not rule.split(':',1)[0].strip()):raise ValueError('Malformed Transkribus custom-tag property')

def points(el,kind='Coords'):
 child=el.find('p:'+kind,N)
 return [[int(x) for x in s.split(',')] for s in child.get('points','').split()] if child is not None else []
def bbox(ps):return [min(x for x,y in ps),min(y for x,y in ps),max(x for x,y in ps),max(y for x,y in ps)] if ps else [0,0,0,0]
def model(raw,name,source):
 root=parse(raw);page=root.find('p:Page',N);meta=root.find('.//p:TranskribusMetadata',N)
 if page is None or meta is None:raise ValueError('Expected native Transkribus PAGE XML with page metadata')
 regions=[]
 for r in page.findall('p:TextRegion',N):
  regions.append({'id':r.get('id'),'custom':r.get('custom',''),'direction':r.get('readingDirection',''),'coords':points(r),'lines':[{'id':l.get('id'),'text':l.findtext('p:TextEquiv/p:Unicode','',N),'coords':points(l),'baseline':points(l,'Baseline'),'custom':l.get('custom','')} for l in r.findall('p:TextLine',N)]})
 return {'file':name,'pageNr':int(meta.get('pageNr')),'pageId':int(meta.get('pageId')),'docId':int(meta.get('docId')),'tsId':int(meta.get('tsid','0')),'status':meta.get('status','IN_PROGRESS'),'image':page.get('imageFilename'),'width':int(page.get('imageWidth')),'height':int(page.get('imageHeight')),'regions':regions,'revision':hashlib.sha256(raw).hexdigest(),'source':source}
def setpoints(el,kind,pts,w,h):
 minimum=2 if kind=='Baseline' else 3
 if len(pts)<minimum:raise ValueError(f'{kind} requires at least {minimum} vertices')
 for p in pts:
  if len(p)!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in p):raise ValueError('Invalid coordinates')
  if not (0<=round(p[0])<w and 0<=round(p[1])<h):raise ValueError('A vertex is outside the image')
 value=' '.join(f'{round(x)},{round(y)}' for x,y in pts);c=el.find('p:'+kind,N)
 if c is not None and c.get('points')==value:return False
 if c is None:c=E.Element(tag(kind));el.insert(0 if kind=='Coords' else 1,c)
 c.set('points',value);return True
def order(el,i):
 custom=el.get('custom','');without=re.sub(r'readingOrder\s*\{[^}]*\}\s*','',custom)
 el.set('custom',(f'readingOrder {{index:{i};}} '+without).strip())
def update(raw,data,schema_path=None):
 root=parse(raw);page=root.find('p:Page',N);w,h=int(page.get('imageWidth')),int(page.get('imageHeight'))
 meta=root.find('.//p:TranskribusMetadata',N)
 if (int(meta.get('pageId')),int(meta.get('docId')),int(meta.get('pageNr'))) != (data['pageId'],data['docId'],data['pageNr']):raise ValueError('PAGE identity mismatch')
 existing={r.get('id'):r for r in page.findall('p:TextRegion',N)};seen=set();ordered=[]
 for r in data['regions']:
  if r['id'] in seen:raise ValueError('Duplicate region ID')
  seen.add(r['id']);el=existing.get(r['id'])
  if el is None:el=E.Element(tag('TextRegion'),id=r['id']);el.set('custom',r.get('custom',''))
  if r.get('coords'):setpoints(el,'Coords',r['coords'],w,h)
  elif r['id'] not in existing:raise ValueError('New regions require a polygon')
  if r.get('direction'):el.set('readingDirection',r['direction'])
  oldlines={l.get('id'):l for l in el.findall('p:TextLine',N)};newlines=[]
  for l in r['lines']:
   if l['id'] in seen:raise ValueError('Duplicate line ID')
   seen.add(l['id']);line=oldlines.get(l['id']);created=line is None
   if created:line=E.Element(tag('TextLine'),id=l['id']);line.set('custom',l.get('custom',''))
   changed=False
   if l.get('coords'):changed|=setpoints(line,'Coords',l['coords'],w,h)
   if l.get('baseline'):changed|=setpoints(line,'Baseline',l['baseline'],w,h)
   text=l.get('text','')
   if '\n' in text or '\r' in text:raise ValueError('Use separate PAGE lines for manuscript line breaks')
   if text!=line.findtext('p:TextEquiv/p:Unicode','',N) or created:
    for t in line.findall('p:TextEquiv',N):line.remove(t)
    te=E.SubElement(line,tag('TextEquiv'));E.SubElement(te,tag('Unicode')).text=text;changed=True
   if changed:
    for t in line.findall('p:TextEquiv',N):t.attrib.pop('conf',None)
    # Word coordinates/text are stale after editing their enclosing line.
    for word in line.findall('p:Word',N):line.remove(word)
   newlines.append(line)
  oldorder=[l.get('id') for l in el.findall('p:TextLine',N)];neworder=[l.get('id') for l in newlines]
  for l in el.findall('p:TextLine',N):el.remove(l)
  for i,l in enumerate(newlines):
   if oldorder!=neworder:order(l,i)
   te=el.find('p:TextEquiv',N)
   if te is None:el.append(l)
   else:el.insert(el.index(te),l)
  ordered.append(el)
 original_order=list(existing)
 if original_order!=[r.get('id') for r in ordered]:
  for r in page.findall('p:TextRegion',N):page.remove(r)
  for i,r in enumerate(ordered):order(r,i);page.append(r)
  ro=page.find('p:ReadingOrder',N)
  if ro is None:ro=E.Element(tag('ReadingOrder'));page.insert(0,ro)
  ro.clear();group=E.SubElement(ro,tag('OrderedGroup'),id='reading_order')
  other=[r for r in page if E.QName(r).localname.endswith('Region') and E.QName(r).localname!='TextRegion']
  for i,r in enumerate(ordered+other):E.SubElement(group,tag('RegionRefIndexed'),index=str(i),regionRef=r.get('id'))
 else:
  for r in ordered:
   if r.getparent() is None:page.append(r)
 root.find('p:Metadata/p:LastChange',N).text=datetime.now(timezone.utc).isoformat()
 if schema_path:
  validation=deepcopy(root)
  for m in validation.findall('.//p:TranskribusMetadata',N):m.getparent().remove(m)
  E.XMLSchema(E.parse(str(schema_path))).assertValid(validation)
 return normalize_custom_attributes(E.tostring(root,encoding='UTF-8',xml_declaration=True))
def page_signature(raw):
 root=parse(raw);page=root.find('p:Page',N)
 def signature(x):return (x.tag,tuple(sorted((k,v.strip() if k=='custom' else v) for k,v in x.attrib.items())),x.text if E.QName(x).localname in ('Unicode','PlainText') else (x.text or '').strip(),tuple(signature(c) for c in x))
 return signature(page)

def server_metadata(raw,info):
 """Attach export identity omitted by the server's PAGE download endpoint."""
 root=parse(raw);metadata=root.find('p:Metadata',N)
 if metadata is None:raise ValueError('Server PAGE has no Metadata element')
 meta=metadata.find('p:TranskribusMetadata',N)
 if meta is None:meta=E.SubElement(metadata,tag('TranskribusMetadata'))
 for source,target in [('tsId','tsid'),('pageId','pageId'),('docId','docId'),('pageNr','pageNr'),('status','status')]:meta.set(target,str(info[source]))
 return E.tostring(root,encoding='UTF-8',xml_declaration=True)
