import unittest,sys
from pathlib import Path
from lxml import etree as E
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import layout_base as c
class MergePreservationTests(unittest.TestCase):
 def fragment(self,ident,x,text):
  line=E.Element(c.tag('TextLine'),id=ident,custom='readingOrder {index:0;}')
  c.setpoints(line,[(x,20),(x+30,20),(x+30,40),(x,40)]);c.setpoints(line,[(x,35),(x+30,35)],'Baseline')
  word=E.SubElement(line,c.tag('Word'),id='word_'+ident);c.setpoints(word,[(x,20),(x+30,20),(x+30,40),(x,40)])
  E.SubElement(E.SubElement(word,c.tag('TextEquiv')),c.tag('Unicode')).text=text
  E.SubElement(E.SubElement(line,c.tag('TextEquiv')),c.tag('Unicode')).text=text
  return line
 def test_merge_keeps_all_word_ids_marks_and_rtl_text(self):
  a=self.fragment('left',10,'ܐ̈.');b=self.fragment('right',50,'ܒܓ')
  merged,_=c.merge([a,b]);self.assertEqual(c.text(merged),'ܒܓ ܐ̈.');self.assertEqual([w.get('id') for w in merged.findall('p:Word',c.N)],['word_right','word_left'])
 def test_human_annotation_blocks_automatic_merge(self):
  a=self.fragment('a',10,'ܐ');b=self.fragment('b',50,'ܒ');a.set('custom','unclear {offset:0;length:1;alternative:ܓ;}')
  self.assertIsNone(c.match(a,b,300))

class ColumnSeparationTests(unittest.TestCase):
 def test_single_region_with_two_columns_and_facing_leaf_is_separated_before_merging(self):
  from column_layout import normalize_columns
  from layout_repair import body_regions
  from collections import Counter
  root=E.Element(c.tag('PcGts'));page=E.SubElement(root,c.tag('Page'),imageWidth='1200',imageHeight='1500');region=E.SubElement(page,c.tag('TextRegion'),id='mixed');c.setpoints(region,[(200,80),(1100,80),(1100,900),(200,900)])
  for prefix,x,width in [('left',200,250),('right',550,250),('facing',1000,80)]:
   for i in range(20):
    line=E.SubElement(region,c.tag('TextLine'),id=f'{prefix}{i}');y=100+i*30;c.setpoints(line,[(x,y-20),(x+width,y-20),(x+width,y+3),(x,y+3)]);c.setpoints(line,[(x,y),(x+width,y)],'Baseline');E.SubElement(E.SubElement(line,c.tag('TextEquiv')),c.tag('Unicode')).text='ܐ̈.'
  raw=E.tostring(root);fixed,report=normalize_columns(raw,1200);self.assertTrue(report['changed']);tree=E.fromstring(fixed);regions=tree.findall('.//p:TextRegion',c.N);self.assertEqual(len(regions),3)
  self.assertTrue(all(l.get('id').startswith('right') for l in regions[0].findall('p:TextLine',c.N)));self.assertTrue(all(l.get('id').startswith('left') for l in regions[1].findall('p:TextLine',c.N)))
  self.assertIn('outside_body_columns',regions[2].get('custom'));self.assertEqual(len(tree.findall('.//p:TextLine',c.N)),60);self.assertEqual(Counter(''.join(c.text(l) for l in root.findall('.//p:TextLine',c.N))),Counter(''.join(c.text(l) for l in tree.findall('.//p:TextLine',c.N))))
