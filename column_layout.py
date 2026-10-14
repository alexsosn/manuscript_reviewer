"""Recover two body columns before fragment merging; preserve outsiders separately."""
from collections import Counter
from copy import deepcopy
import numpy as np
from lxml import etree as E
import layout_base as c

def normalize_columns(raw,width):
 tree=E.fromstring(raw);page=tree.find('p:Page',c.N);regions=page.findall('p:TextRegion',c.N);lines=page.findall('.//p:TextLine',c.N)
 long=[l for l in lines if c.geom(l) and c.geom(l)['box'][2]-c.geom(l)['box'][0]>=width*.15]
 if len(long)<16:return raw,{'changed':False,'warning':'Too few complete baselines to infer columns'}
 typical=float(np.median([c.geom(l)['box'][2]-c.geom(l)['box'][0] for l in long]))
 suspicious=any(c.points(r) and c.bbox(c.points(r))[2]-c.bbox(c.points(r))[0]>typical*1.65 for r in regions) or len(regions)<2
 if not suspicious:return raw,{'changed':False}
 centers=np.array([(c.geom(l)['box'][0]+c.geom(l)['box'][2])/2 for l in long]);means=np.quantile(centers,[.25,.75])
 for _ in range(20):
  labels=np.argmin(abs(centers[:,None]-means),axis=1)
  if any(sum(labels==i)<8 for i in range(2)):return raw,{'changed':False,'warning':'Column clusters uncertain'}
  revised=np.array([np.median(centers[labels==i]) for i in range(2)])
  if np.max(abs(revised-means))<.1:break
  means=revised
 if means[1]-means[0]<width*.18:return raw,{'changed':False,'warning':'Column separation uncertain'}
 boxes=[]
 for i in range(2):
  group=[c.geom(l)['box'] for l,label in zip(long,labels) if label==i]
  boxes.append([float(np.quantile([b[0] for b in group],.05))-12,min(b[1] for b in group)-20,float(np.quantile([b[2] for b in group],.95))+12,max(b[3] for b in group)+20])
 for box in boxes:
  box[0]=max(0,box[0]);box[2]=min(width-1,box[2]);box[1]=max(0,box[1]);box[3]=min(int(page.get('imageHeight'))-1,box[3])
 gutter=(boxes[0][2]+boxes[1][0])/2;boxes[0][2]=min(boxes[0][2],gutter);boxes[1][0]=max(boxes[1][0],gutter)
 groups=[[],[]];outsiders=[]
 for line in lines:
  g=c.geom(line)
  if not g:outsiders.append(line.get('id'));continue
  b=g['box'];matches=[]
  for i,box in enumerate(boxes):
   overlap=max(0,min(b[2],box[2])-max(b[0],box[0]))
   if overlap/max(1,b[2]-b[0])>=.75 and box[1]<=g['my']<=box[3]:matches.append(i)
  if len(matches)==1:groups[matches[0]].append(line)
  else:outsiders.append(line.get('id'))
 if any(len(g)<15 for g in groups):return raw,{'changed':False,'warning':'Insufficient body lines after column separation'}
 # Each original region ID is retained for one body column or its remaining notes.
 parents={line.get('id'):line.getparent() for line in lines};used=set();new=[]
 for i in (1,0):
  votes=Counter(parents[l.get('id')].get('id') for l in groups[i]);origin=next((r for rid,_ in votes.most_common() for r in regions if r.get('id')==rid and rid not in used and not any(l.get('id') in outsiders for l in r.findall('p:TextLine',c.N))),None)
  ident=origin.get('id') if origin is not None else 'body_'+('right' if i else 'left')
  while ident in used or origin is None and any(r.get('id')==ident for r in regions):ident+='x'
  used.add(ident);region=E.Element(c.tag('TextRegion'),id=ident,readingDirection='right-to-left')
  c.setpoints(region,[(round(boxes[i][0]),round(boxes[i][1])),(round(boxes[i][2]),round(boxes[i][1])),(round(boxes[i][2]),round(boxes[i][3])),(round(boxes[i][0]),round(boxes[i][3]))])
  for line in groups[i]:region.append(line)
  new.append(region)
 extras=[]
 for region in regions:
  if region.get('id') in used and not region.findall('p:TextLine',c.N):continue
  if region.findall('p:TextLine',c.N):
   custom=region.get('custom','');region.set('custom',custom+' layoutReview {reason:outside_body_columns;}')
   pts=[p for l in region.findall('p:TextLine',c.N) for p in c.points(l)]
   if pts:c.setpoints(region,c.hull(pts))
   extras.append(region)
 for region in regions:page.remove(region)
 for i,region in enumerate(new+extras):c.order(region,i);page.append(region)
 return E.tostring(tree,encoding='UTF-8',xml_declaration=True),{'changed':True,'columns':boxes,'outsideBody':outsiders,'sourceRegionIds':[r.get('id') for r in regions]}
