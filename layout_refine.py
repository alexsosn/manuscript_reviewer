"""Local experimental row reconstruction from PAGE anchors plus image evidence.

Never uploads. Source layouts are copied; all changes retain provenance.
"""
from pathlib import Path
from copy import deepcopy
import argparse,json,re,hashlib
from datetime import datetime,timezone
import numpy as np
from PIL import Image,ImageFilter,ImageDraw
from lxml import etree as E
import layout_base as c

_GUIDES={}
_GUIDE_CURVES={}
BASE=Path('Preliminary_Setup__BL_Add_MS_14,470')
def curve(line,x):
    bs=np.array(sorted(c.points(line,'Baseline')),dtype=float);x=np.asarray(x,dtype=float)
    if len(bs)<2:return np.full(x.shape,np.nan)
    y=np.interp(x,bs[:,0],bs[:,1])
    for side in (0,-1):
        a,b=(bs[0],bs[min(2,len(bs)-1)]) if side==0 else (bs[max(0,len(bs)-3)],bs[-1])
        slope=np.clip((b[1]-a[1])/max(1,b[0]-a[0]),-.2,.2)
        mask=x<bs[0,0] if side==0 else x>bs[-1,0]
        y=np.where(mask,bs[side,1]+slope*(x-bs[side,0]),y)
    return y

def guide(line,lines,x,width):
    """Extrapolate missing spans using nearby complete rows, not tiny fragments."""
    bs=sorted(c.points(line,'Baseline')); xs=np.asarray(x,dtype=float)
    cachekey=(tuple(lines),line,tuple(xs))
    if cachekey in _GUIDE_CURVES:return _GUIDE_CURVES[cachekey]
    y=curve(line,xs)
    long=[l for l in lines if l.get('id')!=line.get('id') and c.geom(l) and c.geom(l)['box'][2]-c.geom(l)['box'][0]>.55*width]
    for anchor,outside in [(bs[0],xs<bs[0][0]),(bs[-1],xs>bs[-1][0])]:
        key=(tuple(lines),line,tuple(anchor))
        if key not in _GUIDES:_GUIDES[key]=sorted(long,key=lambda l:abs(float(curve(l,[anchor[0]])[0])-anchor[1]))[:4]
        neighbors=_GUIDES[key]
        if neighbors:
            shapes=np.array([curve(l,xs)-curve(l,[anchor[0]])[0] for l in neighbors])
            y=np.where(outside,anchor[1]+np.median(shapes,axis=0),y)
    _GUIDE_CURVES[cachekey]=y
    return y

def join_fragments(region,changes):
    lines=region.findall('p:TextLine',c.N);rb=c.bbox(c.points(region));width=rb[2]-rb[0];mid=(rb[0]+rb[2])/2
    long=[l for l in lines if c.geom(l) and c.geom(l)['box'][2]-c.geom(l)['box'][0]>.55*width]
    levels=sorted(float(curve(l,[mid])[0]) for l in long)
    spacing=float(np.median(np.diff(levels))) if len(levels)>2 else 24
    while True:
        c.geom.cache_clear(); options=[]
        for i,a in enumerate(lines):
            ga=c.geom(a)
            if not ga:continue
            for j in range(i+1,len(lines)):
                b=lines[j];gb=c.geom(b)
                if c.protected(a) or c.protected(b):continue
                if not gb:continue
                left,right=(a,b) if ga['box'][0]<gb['box'][0] else (b,a)
                gl,gr=c.geom(left),c.geom(right);gap=gr['box'][0]-gl['box'][2]
                if gap<0 or gap>min(125,width*.40):continue
                xm=(gl['box'][2]+gr['box'][0])/2
                err=abs(float(guide(left,lines,[xm],width)[0]-guide(right,lines,[xm],width)[0]))
                if err>min(9,spacing*.34):continue
                # A full row on either side excludes fragments of different rows.
                level=(float(guide(left,lines,[mid],width)[0])+float(guide(right,lines,[mid],width)[0]))/2
                competing=[l for l in long if l is not a and l is not b and abs(float(curve(l,[mid])[0])-level)<spacing*.45]
                if competing:continue
                options.append((err+.015*gap,i,j,gap,err))
        if not options:break
        _,i,j,gap,err=min(options); group=[lines[i],lines[j]];new,rtl=c.merge(group)
        changes.append({'kind':'merge','region':region.get('id'),'id':new.get('id'),'gap_px':gap,'alignment_error_px':round(err,2),'sources':[{'id':l.get('id'),'xml':E.tostring(l,encoding='unicode')} for l in rtl],'text_boundary_needs_review':True})
        region.remove(lines[i]);region.remove(lines[j]);region.append(new)
        lines[i]=new;lines.pop(j)
    lines.sort(key=lambda l:float(guide(l,lines,[mid],width)[0]) if c.geom(l) else 1e6)
    for i,l in enumerate(lines):region.remove(l);c.order(l,i);region.append(l)
    return lines,spacing

def extend_line(line,region,lines,spacing,ink,changes):
    g=c.geom(line)
    if not g:return
    rb=c.bbox(c.points(region));width=rb[2]-rb[0]
    xs=np.arange(max(0,rb[0]-6),min(ink.shape[1]-1,rb[2]+6)+1)
    ys=guide(line,lines,xs,width)
    top=ys-19;bottom=ys+4
    for other in lines:
        if other.get('id')==line.get('id') or not c.geom(other):continue
        oy=guide(other,lines,xs,width);delta=oy-ys
        top=np.where((delta<-spacing*.45)&(delta>-spacing*1.7),np.maximum(top,(oy+ys)/2-7),top)
        bottom=np.where((delta>spacing*.45)&(delta<spacing*1.7),np.minimum(bottom,(oy+ys)/2-7),bottom)
    offsets=np.arange(-20,6);rows=np.round(ys[:,None]+offsets).astype(int)
    valid=(rows>=0)&(rows<ink.shape[0])&(rows>=top[:,None])&(rows<=bottom[:,None])
    values=ink[np.clip(rows,0,ink.shape[0]-1),xs[:,None]]&valid
    counts=values.sum(axis=1);support=counts>=2
    support=support&(np.r_[False,support[:-1]]|np.r_[support[1:],False])
    endpoints=[];boundaries=[g['box'][0],g['box'][2]]
    for side,original in [('left',boundaries[0]),('right',boundaries[1])]:
        inside=(xs>=original)&(xs<=original+16) if side=='left' else (xs>=original-16)&(xs<=original)
        if counts[inside].sum()<12:continue
        indices=np.flatnonzero(xs<original if side=='left' else xs>original)
        if side=='left':indices=indices[::-1]
        blank=0;last=None;total=0;maxgap=max(20,min(30,round(spacing*1.05)))
        for k in indices:
            if support[k]:last=k;total+=int(counts[k]);blank=0
            else:blank+=1
            if blank>maxgap:break
        if last is None or abs(int(xs[last])-original)<12 or total<35:continue
        edge=int(xs[last])+(-2 if side=='left' else 2);edge=max(int(xs[0]),min(int(xs[-1]),edge))
        endpoints.append({'side':side,'old_x':original,'new_x':edge,'extension_px':abs(edge-original),'ink_pixels':total,'search_boundary_reached':bool(abs(edge-(xs[0] if side=='left' else xs[-1]))<4)})
    if not endpoints:return
    old=E.tostring(line,encoding='unicode');bs=c.points(line,'Baseline');extra=[]
    for e in endpoints:
        low,high=sorted([e['old_x'],e['new_x']]);xx=list(range(low,high+1,12))+[high]
        yy=guide(line,lines,xx,width)
        extra.extend((int(x),int(round(y))) for x,y in zip(xx,yy) if x<g['box'][0] or x>g['box'][2])
    newbs=sorted(set(bs+extra));newpoly=c.points(line)
    # Capture the observed ink at the recovered ends, plus a modest baseline cap.
    for e in endpoints:
        low,high=sorted([e['old_x'],e['new_x']]);ks=np.flatnonzero((xs>=low)&(xs<=high))
        for k in ks:
            rr=rows[k][values[k]]
            if len(rr):newpoly.extend([(int(xs[k]),int(rr.min())-2),(int(xs[k]),int(rr.max())+2)])
        y=int(round(guide(line,lines,[e['new_x']],width)[0]));newpoly.extend([(e['new_x'],y-18),(e['new_x'],y+5)])
    newpoly=[(max(0,min(ink.shape[1]-1,x)),max(0,min(ink.shape[0]-1,y))) for x,y in c.hull(newpoly)]
    c.setpoints(line,newbs,'Baseline');c.setpoints(line,newpoly)
    # Recognition did not cover the recovered characters; do not reuse confidence.
    for te in line.findall('p:TextEquiv',c.N):te.attrib.pop('conf',None)
    applied=not any(e['search_boundary_reached'] for e in endpoints)
    changes.append({'kind':'endpoint' if applied else 'endpoint_candidate','applied':applied,'region':region.get('id'),'id':line.get('id'),'endpoints':endpoints,'old_xml':old,'new_xml':E.tostring(line,encoding='unicode'),'transcription_needs_review':True,'review_reason':None if applied else 'Ink continues to the search boundary; possible marginal stain or unresolved endpoint.'})
    if not applied:
        source=E.fromstring(old.encode())
        line.attrib.clear();line.attrib.update(source.attrib)
        for child in list(line):line.remove(child)
        for child in source:line.append(deepcopy(child))
    c.geom.cache_clear()
