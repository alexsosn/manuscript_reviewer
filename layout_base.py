"""Conservative PAGE layout repair. Originals are never overwritten.

Run with a Python environment containing lxml and Pillow.
"""
from pathlib import Path
from collections import Counter
from copy import deepcopy
import argparse
import csv
import hashlib
import json
import math
import re
from functools import lru_cache
from datetime import datetime, timezone
from lxml import etree as ET
from PIL import Image, ImageDraw

NS = 'http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15'
N = {'p': NS}
def tag(s): return '{'+NS+'}'+s
def points(el, kind='Coords'):
    c = el.find('p:'+kind, N)
    return [tuple(map(int, p.split(','))) for p in c.get('points', '').split()] if c is not None else []
def bbox(ps):
    return (min(x for x,y in ps), min(y for x,y in ps), max(x for x,y in ps), max(y for x,y in ps)) if ps else None
def hull(ps):
    ps = sorted(set(ps))
    def cross(o,a,b): return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lo=[]; hi=[]
    for p in ps:
        while len(lo)>1 and cross(lo[-2],lo[-1],p)<=0: lo.pop()
        lo.append(p)
    for p in reversed(ps):
        while len(hi)>1 and cross(hi[-2],hi[-1],p)<=0: hi.pop()
        hi.append(p)
    return lo[:-1]+hi[:-1]
def setpoints(el, ps, kind='Coords'):
    c=el.find('p:'+kind,N)
    if c is None: c=ET.Element(tag(kind)); el.insert(0,c)
    c.set('points',' '.join(f'{x},{y}' for x,y in ps))
def text(el): return el.findtext('p:TextEquiv/p:Unicode','',N)
def order(el,i):
    custom=el.get('custom','')
    custom=re.sub(r'readingOrder\s*\{[^}]*\}\s*','',custom)
    el.set('custom',(f'readingOrder {{index:{i};}} '+custom).strip())
@lru_cache(maxsize=8192)
def geom(line):
    ps=points(line,'Baseline')
    if len(set(ps))<2: return None
    ps=sorted(ps); b=bbox(ps); dx=b[2]-b[0]; dy=b[3]-b[1]
    if dx<10 or dy>dx*.55: return None
    # Least squares captures page curvature better than the polygon centre.
    mx=sum(p[0] for p in ps)/len(ps); my=sum(p[1] for p in ps)/len(ps)
    slope=sum((x-mx)*(y-my) for x,y in ps)/sum((x-mx)**2 for x,y in ps)
    return {'left':ps[0], 'right':ps[-1], 'slope':slope, 'mx':mx, 'my':my, 'box':b}
def y_at(g,x): return g['my']+g['slope']*(x-g['mx'])
def protected(line):
    return bool(re.sub(r"(?:readingOrder|structure)\s*\{[^}]*\}", "", line.get("custom", "")).strip())

def match(a,b,width):
    if protected(a) or protected(b): return None
    ga=geom(a); gb=geom(b)
    if ga is None or gb is None: return None
    if ga['left'][0]>gb['left'][0]: ga,gb=gb,ga
    gap=gb['left'][0]-ga['right'][0]
    if gap < 0 or gap>min(100,width*.32): return None
    if abs(ga['slope']-gb['slope'])>.16: return None
    x=(ga['right'][0]+gb['left'][0])/2
    # Compare at the gap, not at the column centre: short fragments cannot
    # safely be extrapolated over an entire column.
    err=abs(y_at(ga,x)-y_at(gb,x))
    if err>4.0: return None
    if not points(a) or not points(b): return None
    return (err,gap)
def merge(group):
    # PAGE Unicode is in logical order; concatenate right fragment first.
    rtl=sorted(group,key=lambda l:bbox(points(l,'Baseline'))[2],reverse=True)
    out=deepcopy(rtl[0])
    out.set('id','merged_'+hashlib.sha256('|'.join(l.get('id') for l in rtl).encode()).hexdigest()[:16])
    setpoints(out,hull([p for l in group for p in points(l)]))
    setpoints(out,sorted(set(p for l in group for p in points(l,'Baseline'))),'Baseline')
    # Retain every fragment's word nodes and IDs, in logical RTL sequence.
    for child in list(out):
        if ET.QName(child).localname in ('Word','TextEquiv'):out.remove(child)
    for source in rtl:
        for word in source.findall('p:Word',N):out.append(deepcopy(word))
    te=ET.SubElement(out,tag('TextEquiv')); ET.SubElement(te,tag('Unicode')).text=' '.join(text(l) for l in rtl if text(l))
    return out,rtl

def repair(src,dest):
    tree=ET.parse(str(src)); page=tree.find('p:Page',N)
    regs=page.findall('p:TextRegion',N)
    main=sorted([r for r in regs if not re.search(r'marginalia|outside_body_columns',r.get('custom',''))],key=lambda r:len(r.findall('p:TextLine',N)),reverse=True)[:2]
    assert all(len(r.findall('p:TextLine',N))>15 for r in main),src
    main.sort(key=lambda r:(bbox(points(r))[0]+bbox(points(r))[2])/2,reverse=True)
    report={'file':src.name,'pageNr':tree.find('p:Metadata/p:TranskribusMetadata',N).get('pageNr'),
            'original_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),
            'columns':[r.get('id') for r in main],'merges':[],'moves':[],'removed_empty':[],
            'review':[],'region_order_changed':False,'lines_before':len(page.findall('.//p:TextLine',N))}
    old_order=[r.get('regionRef') for r in page.findall('p:ReadingOrder/p:OrderedGroup/p:RegionRefIndexed',N)]
    # Coordinate-less dummy containers are export artifacts. Assign normal
    # horizontal lines only when their complete baseline fits one column.
    for reg in [r for r in regs if r not in main]:
        if points(reg):continue
        for line in list(reg.findall('p:TextLine',N)):
            g=geom(line)
            if g is None:continue
            matches=[]
            for col in main:
                b=bbox(points(col)); lb=g['box']
                if lb[0]>=b[0]-8 and lb[2]<=b[2]+8 and lb[1]>=b[1]-20 and lb[3]<=b[3]+20:matches.append(col)
            if len(matches)==1:
                reg.remove(line);matches[0].append(line)
                report['moves'].append({'line':line.get('id'),'from':reg.get('id'),'to':matches[0].get('id')})
        if not reg.findall('p:TextLine',N):
            page.remove(reg);report['removed_empty'].append(reg.get('id'));continue
        allpts=[p for l in reg.findall('p:TextLine',N) for p in points(l)]
        if len(set(allpts))>=3:setpoints(reg,hull(allpts))
        else:report['review'].append({'id':reg.get('id'),'reason':'missing region geometry'})
    for reg in page.findall('p:TextRegion',N):
        for line in list(reg.findall('p:TextLine',N)):
            if not points(line) and len(set(points(line,'Baseline')))<2 and not text(line):
                reg.remove(line);report['removed_empty'].append(line.get('id'))
        if reg not in main:continue
        b=bbox(points(reg)); width=b[2]-b[0]
        groups=[[l] for l in reg.findall('p:TextLine',N)]
        # Greedy nearest aligned pair, with every member checked for overlap.
        while True:
            candidates=[]
            for i in range(len(groups)):
                for j in range(i+1,len(groups)):
                    combined=groups[i]+groups[j]
                    if any(geom(l) is None for l in combined):continue
                    ordered=sorted(combined,key=lambda l:geom(l)['box'][0])
                    ms=[match(a,z,width) for a,z in zip(ordered,ordered[1:])]
                    if ms and all(m is not None for m in ms):candidates.append((max(m[0] for m in ms),i,j))
            if not candidates:break
            _,i,j=min(candidates);groups[i]+=groups.pop(j)
        lines=[]
        for group in groups:
            if len(group)>1:
                new,rtl=merge(group);lines.append(new)
                report['merges'].append({'region':reg.get('id'),'new_id':new.get('id'),
                    'sources':[{'id':l.get('id'),'text':text(l),'xml':ET.tostring(l,encoding='unicode')} for l in rtl]})
            else:lines+=group
        for l in reg.findall('p:TextLine',N):reg.remove(l)
        horizontal=[l for l in lines if geom(l) is not None]
        other=[l for l in lines if geom(l) is None]
        horizontal.sort(key=lambda l:y_at(geom(l),(b[0]+b[2])/2))
        # Vertical annotations get their own region rather than participating
        # in body-text order. Keep original line geometry and transcription.
        for line in other:
            ps=points(line)
            if len(set(ps))>=3:
                note=ET.Element(tag('TextRegion'),id='note_'+line.get('id'),readingDirection='right-to-left')
                note.set('custom','structure {type:marginalia;}')
                setpoints(note,hull(ps)); order(line,0);note.append(line);page.append(note)
                report['moves'].append({'line':line.get('id'),'from':reg.get('id'),'to':note.get('id')})
                report['review'].append({'id':line.get('id'),'reason':'vertical or very short baseline; separated from body'})
            else:
                horizontal.append(line);report['review'].append({'id':line.get('id'),'reason':'unusable line geometry'})
        for i,l in enumerate(horizontal):order(l,i);reg.append(l)
        reg.set('readingDirection','right-to-left')
        # Potentially fragmented lines which did not meet the strict merge
        # threshold are listed for human review instead of guessed.
        for l in horizontal:
            g=geom(l)
            if g and g['box'][2]-g['box'][0]<width*.5:
                report['review'].append({'id':l.get('id'),'reason':'short body line; inspect for remaining fragments'})
    extras=[r for r in page.findall('p:TextRegion',N) if r not in main]
    extras.sort(key=lambda r:(bbox(points(r))[1],-bbox(points(r))[2]) if points(r) else (99999,0))
    ordered=main+extras
    ro=page.find('p:ReadingOrder',N)
    if ro is None:ro=ET.Element(tag('ReadingOrder'));page.insert(0,ro)
    ro.clear();og=ET.SubElement(ro,tag('OrderedGroup'),id='ro_rtl',caption='Right column, left column, separate annotations')
    for i,r in enumerate(ordered):
        order(r,i);ET.SubElement(og,tag('RegionRefIndexed'),index=str(i),regionRef=r.get('id'))
        # Set annotation line indices too, preserving their original sequence.
        if r not in main:
            for j,l in enumerate(r.findall('p:TextLine',N)):order(l,j)
        page.remove(r);page.append(r)
    report['region_order_changed']=old_order!=[r.get('id') for r in ordered]
    report['lines_after']=len(page.findall('.//p:TextLine',N))
    tree.find('p:Metadata/p:LastChange',N).text=datetime.now(timezone.utc).isoformat()
    # Every original non-whitespace Unicode character must survive.
    original=ET.parse(str(src))
    before=Counter(''.join(''.join(text(l).split()) for l in original.findall('.//p:TextLine',N)))
    after=Counter(''.join(''.join(text(l).split()) for l in page.findall('.//p:TextLine',N)))
    assert before==after,(src,'transcription character loss')
    ids=[e.get('id') for e in tree.iter() if e.get('id')]
    assert len(ids)==len(set(ids)),(src,'duplicate IDs')
    dest.parent.mkdir(parents=True,exist_ok=True)
    tree.write(str(dest),encoding='UTF-8',xml_declaration=True,pretty_print=True)
    return report
