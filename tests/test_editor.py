import sys, unittest, tempfile, shutil, json
from pathlib import Path
from copy import deepcopy
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from corpus import Corpus,letters,semiglobal
from pagexml import model,update,parse,N,tag,page_signature,server_metadata
from transkribus import Transkribus
from backend import Backend
from lxml import etree as E
APP=Path(__file__).resolve().parents[1];ROOT=APP.parent
SAMPLE=APP/'tests/fixtures/synthetic.xml'
REAL_SAMPLE=ROOT/'layout_v2/page/add_ms_14470_f044r.xml'
SCHEMA=APP/'data/pagecontent-2013.xsd'
class CorpusTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.c=Corpus(APP/'data')
 def test_complete_corpus(self):
  self.assertEqual(len(self.c.books),27);self.assertEqual(len(self.c.verses),7957)
  self.assertTrue(any(v['book']=='Romans' and v['chapter']==16 for v in self.c.verses))
 @unittest.skipUnless(REAL_SAMPLE.exists(),'Optional manuscript workspace integration test')
 def test_real_page(self):
  m=model(REAL_SAMPLE.read_bytes(),REAL_SAMPLE.name,'test');lines=[l for r in m['regions'][:2] for l in r['lines']]
  a=self.c.align(lines);self.assertGreater(a['score'],.9);self.assertEqual(len(a['lines']),87)
  self.assertTrue(a['passage'].startswith('Luke 3:14'));self.assertIn('4:3',a['passage'])
 def test_split_word_partition(self):
  v=next(v for v in self.c.verses if v['book']=='John' and v['chapter']==1 and v['verse']==1)
  text=v['text'];start=next(i for i in range(4,len(text)-4) if text[i-1].isalpha() and text[i].isalpha())
  lines=[{'id':'a','text':text[:start]},{'id':'b','text':text[start:]}]
  a=self.c.align(lines,book='John',anchor='1:1');self.assertEqual(a['score'],1)
  self.assertEqual(letters(''.join(l['reference'] for l in a['lines'])),letters(text))
  self.assertTrue(a['lines'][0]['splitEnd']);self.assertTrue(a['lines'][1]['splitStart'])
 def test_inflected_reference_word_analysis(self):
  result=self.c.lookup('ܕܝܠܝܕܘܬܗ',2);a=result['analyses'][0]
  self.assertEqual(a['lemma'],'ܝܠܝܕܘܬܐ');self.assertEqual(a['root'],'ܝܠܕ');self.assertIn('noun',a['grammar']);self.assertTrue(a['glosses'])
  self.assertTrue(any(x['label']=='Prefix' and x['text']=='ܕ' for x in a['affixes']))
  with self.assertRaises(ValueError):self.c.lookup('ܐܠܗܐ',2)
 def test_reference_fragment_knows_whole_word(self):
  v=next(v for v in self.c.verses if v['book']=='John' and v['chapter']==1 and v['verse']==1);text=v['text'];cut=next(i for i in range(4,len(text)-4) if text[i-1].isalpha() and text[i].isalpha())
  a=self.c.align([{'id':'a','text':text[:cut]},{'id':'b','text':text[cut:]}],book='John',anchor='1:1')
  first,second=a['lines'];w1,w2=first['words'][-1],second['words'][0];self.assertEqual(w1['wordId'],w2['wordId']);self.assertEqual(w1['word'],w2['word'])
  self.assertEqual(w1['text']+w2['text'],w1['word'])
 def test_no_definition_free_suggestions(self):
  result=self.c.lookup('ܐܬܬܚܕܘ');self.assertTrue(all(e['gloss'] and e['gloss']!=e['transliteration'] for e in result['entries']))
 def test_lexicon(self):
  hits=self.c.lookup('ܐܠܗܐ')['entries'];self.assertTrue(any(h['match']=='exact' and 'God' in h['gloss'] for h in hits))
  self.assertTrue(any(h['match']=='possible clitic' for h in self.c.lookup('ܘܐܠܗܐ')['entries']))
  self.assertTrue(all('<span' not in h['gloss'] for h in hits))
class PageTests(unittest.TestCase):
 def setUp(self):self.raw=SAMPLE.read_bytes();self.m=model(self.raw,SAMPLE.name,'test')
 def test_unchanged_semantics(self):self.assertEqual(page_signature(self.raw),page_signature(update(self.raw,self.m,SCHEMA)))
 def test_text_geometry_and_unknown_attributes(self):
  root=parse(self.raw);line=root.find('.//p:TextLine',N);line.set('custom',line.get('custom')+' testTag {value:keep;}')
  line.find('p:TextEquiv',N).set('conf','0.9');raw=E.tostring(root);m=model(raw,'test','test')
  changed=m['regions'][0]['lines'][0];changed['text']='ܐܠܗܐ';changed['baseline'][0][0]+=1
  out=parse(update(raw,m,SCHEMA));edited=out.find('.//p:TextLine',N)
  self.assertIn('testTag',edited.get('custom'));self.assertIsNone(edited.find('p:TextEquiv',N).get('conf'))
  self.assertEqual(edited.findtext('p:TextEquiv/p:Unicode',namespaces=N),'ܐܠܗܐ')
  self.assertEqual(out.find('.//p:TranskribusMetadata',N).get('pageId'),root.find('.//p:TranskribusMetadata',N).get('pageId'))
 def test_add_delete_reorder(self):
  m=deepcopy(self.m);m['regions'].reverse();lines=m['regions'][0]['lines'];new=deepcopy(lines[0]);new['id']='new_line_test';new['text']='ܐܠܗܐ';lines[0]=new
  out=update(self.raw,m,SCHEMA);loaded=model(out,'test','test');self.assertEqual(loaded['regions'][0]['id'],m['regions'][0]['id']);self.assertEqual(loaded['regions'][0]['lines'][0]['id'],'new_line_test')
 def test_server_download_without_export_extension(self):
  root=parse(self.raw);meta=root.find('.//p:TranskribusMetadata',N);meta.getparent().remove(meta)
  raw=E.tostring(root);attached=server_metadata(raw,{'tsId':99,'pageId':self.m['pageId'],'docId':self.m['docId'],'pageNr':84,'status':'IN_PROGRESS'})
  loaded=model(attached,'server','server');self.assertEqual(loaded['tsId'],99);update(attached,loaded,SCHEMA)
  self.assertEqual(page_signature(raw),page_signature(attached))
 def test_reject_invalid(self):
  for mutate in (lambda m:m.update(pageId=0),lambda m:m['regions'][0]['lines'][0].update(text='a\nb'),lambda m:m['regions'][0]['lines'][0]['baseline'][0].__setitem__(0,-1)):
   m=deepcopy(self.m);mutate(m)
   with self.assertRaises(ValueError):update(self.raw,m,SCHEMA)
 def test_atomic_save_backup_and_conflict(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'page').mkdir();source=root/'page'/SAMPLE.name;source.write_bytes(self.raw)
   with unittest.mock.patch.object(Backend,'get_corpus',return_value=Mock(books=[])):
    b=Backend(root)
   m=b.page(84);m['regions'][0]['lines'][0]['text']='ܐܠܗܐ';saved=b.save(m)
   self.assertEqual(source.read_bytes(),self.raw);self.assertTrue(saved['edited']);self.assertEqual(len(list((root/'local_edits/backups'/SAMPLE.name).glob('*.xml'))),1)
   with self.assertRaisesRegex(ValueError,'changed since'):b.save(m)
class UploadTests(unittest.TestCase):
 def setUp(self):
  self.api=Transkribus();self.raw=SAMPLE.read_bytes();self.m=model(self.raw,'x','x');self.page={'pageId':self.m['pageId']};self.ts={'tsId':1,'status':'IN_PROGRESS'}
 def test_stale_does_not_post(self):
  self.api.remote=Mock(return_value=(self.page,self.ts));self.api.request=Mock()
  with self.assertRaisesRegex(ValueError,'Server version changed'):self.api.upload(1,self.m['docId'],84,self.raw,{'tsId':0})
  self.api.request.assert_not_called()
 def test_new_version_readback(self):
  self.api.remote=Mock(side_effect=[(self.page,self.ts),(self.page,{**self.ts,'tsId':2})]);self.api.request=Mock(side_effect=[b'{"tsId":2}',self.raw])
  raw,receipt=self.api.upload(1,self.m['docId'],84,self.raw,{'tsId':1});self.assertTrue(receipt['verified']);self.assertEqual(raw,self.raw)
  url=self.api.request.call_args_list[0].args[0];self.assertIn('overwrite=false',url);self.assertIn('parent=1',url)
 def test_accepted_with_failed_readback(self):
  self.api.remote=Mock(return_value=(self.page,self.ts));self.api.request=Mock(side_effect=[b'{"tsId":2}',ValueError('network')])
  raw,receipt=self.api.upload(1,self.m['docId'],84,self.raw,{'tsId':1});self.assertIsNone(raw);self.assertFalse(receipt['verified']);self.assertEqual(receipt['tsId'],2)
if __name__=='__main__':unittest.main()
