"""Local, image-guided repair. Original exports and server data are untouched."""
from pathlib import Path
from copy import deepcopy
from collections import Counter
import json,hashlib,re,tempfile
import numpy as np
from PIL import Image,ImageFilter
from lxml import etree as E
import layout_base as c
import layout_refine as refine
from pagexml import model,update

def body_regions(regions):
 candidates=[r for r in regions if r.get('lines') and not re.search(r'(marginalia|footnote|header|page-number|outside_body_columns)',r.get('custom',''),re.I)]
 main=sorted(candidates,key=lambda r:len(r['lines']),reverse=True)[:2]
 return sorted(main,key=lambda r:sum(p[0] for p in r['coords'])/max(1,len(r['coords'])),reverse=True)

def repair_page(source,dest,image,schema):
 source,dest=Path(source),Path(dest);original=source.read_bytes();dest.parent.mkdir(parents=True,exist_ok=True)
 if dest.exists():raise ValueError('Corrected output already exists; preserve it rather than replacing edits')
 from column_layout import normalize_columns
 initial=model(original,source.name,str(source));prepared,column_report=normalize_columns(original,initial['width'])
 m=model(prepared,source.name,str(source));body=body_regions(m['regions']);preliminary=[]
 if len(body)==2 and all(len(r['lines'])>15 for r in body):
  with tempfile.TemporaryDirectory() as temp:
   staged=Path(temp)/source.name;staged.write_bytes(prepared);report=c.repair(staged,dest)
  preliminary=report['merges']
 else:
  m['regions']=body+[r for r in m['regions'] if r not in body]
  for r in body:r['direction']='right-to-left'
  dest.write_bytes(update(prepared,m,schema));report={'review':[{'reason':'Sparse or unusual page: conservative ordering only'}]}
 tree=E.parse(str(dest));page=tree.find('p:Page',c.N);changes=[]
 im=Image.open(image).convert('RGB');gray=im.convert('L')
 if (im.width,im.height)!=(m['width'],m['height']):raise ValueError('Image and PAGE dimensions differ')
 ar=np.array(gray,dtype=np.int16);bg=np.array(gray.filter(ImageFilter.GaussianBlur(9)),dtype=np.int16);rgb=np.array(im,dtype=np.int16)
 red=((rgb[:,:,0]-rgb[:,:,1])>45)&((rgb[:,:,0]-rgb[:,:,1])/(rgb[:,:,0]+rgb[:,:,1]+1)>.24)
 ink=(ar<190)&((bg-ar)>17)&~red
 refine._GUIDES.clear();refine._GUIDE_CURVES.clear();c.geom.cache_clear()
 body_ids={r['id'] for r in body_regions(model(E.tostring(tree),source.name,'repair')['regions'])}
 for region in page.findall('p:TextRegion',c.N):
  if region.get('id') not in body_ids or not c.points(region):continue
  lines,spacing=refine.join_fragments(region,changes);anchors=[deepcopy(l) for l in lines]
  for line,anchor in zip(lines,anchors):
   proposal=deepcopy(anchor);refine.extend_line(proposal,region,anchors,spacing,ink,changes)
   # A complete baseline can still have a clipped polygon. Enclose its ends
   # without extending beyond the neighboring-row safety band.
   polygon=c.points(proposal);baseline=c.points(proposal,'Baseline')
   if polygon and baseline:
    box=c.bbox(polygon);missing=[(x,y) for x,y in baseline if x<box[0] or x>box[2]]
    if missing:
     old=E.tostring(proposal,encoding='unicode')
     for x,y in missing:polygon.extend([(x,y-round(min(18,spacing*.55))),(x,y+round(min(4,spacing*.15)))])
     c.setpoints(proposal,c.hull(polygon));changes.append({'kind':'polygon','id':line.get('id'),'reason':'Polygon did not enclose the complete baseline','old_xml':old})
   # All geometry, including unmodified vertices, must remain on this image.
   for kind in ('Coords','Baseline'):
    pts=c.points(proposal,kind)
    if pts:c.setpoints(proposal,[(max(0,min(im.width-1,x)),max(0,min(im.height-1,y))) for x,y in pts],kind)
   if E.tostring(proposal)!=E.tostring(line):line.getparent().replace(line,proposal)
 # PAGE requires TextLine before region TextEquiv/TextStyle.
 for region in page.findall('p:TextRegion',c.N):
  lines=list(region.findall('p:TextLine',c.N))
  for line in lines:region.remove(line)
  trailing=[ch for ch in region if E.QName(ch).localname in ('TextEquiv','TextStyle','UserDefined','Labels')]
  pos=region.index(trailing[0]) if trailing else len(region)
  for line in lines:region.insert(pos,line);pos+=1
 validation=deepcopy(tree)
 for el in validation.findall('.//p:TranskribusMetadata',c.N):el.getparent().remove(el)
 E.XMLSchema(E.parse(str(schema))).assertValid(validation)
 def chars(t):return Counter(''.join(''.join(c.text(l).split()) for l in t.findall('.//p:TextLine',c.N)))
 assert chars(E.fromstring(original))==chars(tree),'OCR character loss (including marks and punctuation)'
 ids=[el.get('id') for el in tree.iter() if el.get('id')];assert len(ids)==len(set(ids)),'Duplicate IDs'
 tree.write(str(dest),encoding='UTF-8',xml_declaration=True)
 return {'pageNr':m['pageNr'],'file':source.name,'sourceSha256':hashlib.sha256(original).hexdigest(),'correctedSha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'columnReconstruction':column_report,'merges':len(preliminary)+sum(x['kind']=='merge' for x in changes),'extensions':sum(x['kind']=='endpoint' for x in changes),'review':report.get('review',[]),'preliminaryMerges':preliminary,'changes':changes,'schemaValid':True,'ocrCharactersPreserved':True}
