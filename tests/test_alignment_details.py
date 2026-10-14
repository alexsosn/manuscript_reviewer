import unittest,sys,tempfile,json
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from alignment import mapped,global_path,differences
from alignment_cache import continuity,input_digest,load_cached
from corpus import Corpus,letters
from backend import Backend
from pagexml import parse,N,model,server_metadata
APP=Path(__file__).resolve().parents[1]
class CharacterTests(unittest.TestCase):
 def test_marks_and_punctuation_are_not_discarded(self):
  self.assertEqual(mapped('ܐ̈. ܒ')[0],'ܐ̈.ܒ')
  self.assertEqual({c['kind'] for c in differences('ܐܒ','ܐ̈ܒ.')},{'diacritics','punctuation'})
  self.assertEqual(differences('ܐ\nܒ','ܐ ܒ'),[])
 def test_pinned_path_consumes_internal_and_edge_omissions(self):
  for a,b in [('ܐܒ','ܐܓܕܒ.'),('ܐ̈','ܐ')]:
   edges,cost=global_path(a,b);self.assertEqual(edges[0],0);self.assertEqual(edges[-1],len(b));self.assertGreater(cost,0)
 def test_gap_includes_missing_dots(self):
  c=Mock(raw='ܐ̈.ܒ');c.verse_at.return_value={'book':'John','chapter':1,'verse':1}
  r=continuity({'coverage':{'referenceEnd':1}},{'coverage':{'referenceStart':3}},c)
  self.assertEqual(r['status'],'gap');self.assertEqual(r['text'],'̈.')
class PassageTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.c=Corpus(APP/'data')
 def test_internal_reference_omission_is_retained_across_lines(self):
  text=next(v['text'] for v in self.c.verses if v['book']=='John' and v['chapter']==1 and v['verse']==1)
  cut=len(text)//2;a=self.c.align([{'id':'a','text':text[:cut-4]},{'id':'b','text':text[cut+4:]}],'John','1:1')
  self.assertEqual(letters(''.join(l['reference'] for l in a['lines'])),letters(text))
  self.assertEqual(a['coverage']['unassignedReferenceCharacters'],0);self.assertGreater(a['coverage']['missingReferenceCharacters'],0)
 def test_dots_generate_visible_differences(self):
  text=next(v['text'] for v in self.c.verses if v['book']=='John' and v['chapter']==1 and v['verse']==1)
  a=self.c.align([{'id':'a','text':text+'̈.'}],'John','1:1')
  self.assertTrue(a['lines'][0]['changes']);self.assertLess(a['score'],1);self.assertEqual(a['letterScore'],1)
class ProfileTests(unittest.TestCase):
 def test_switch_preserves_drafts_and_rejects_cross_document_save(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);old=root/'page';old.mkdir();raw=(APP/'tests/fixtures/synthetic.xml').read_bytes();(old/'p.xml').write_bytes(raw)
   base=model(raw,'p.xml','test');new=root/'new/page';new.mkdir(parents=True)
   other=server_metadata(raw,{'docId':999,'pageId':9999,'pageNr':84,'tsId':2,'status':'NEW'});(new/'p.xml').write_bytes(other)
   profiles={'legacy':{'title':'old','source':str(old),'images':str(root),'output':str(root/'old-edits'),'collection':1,'document':base['docId'],'uploadPages':[3]},'new':{'title':'new','source':str(new),'images':str(root),'output':str(root/'new-edits'),'collection':1,'document':999,'uploadPages':[]}}
   settings=root/'local_edits/settings.json';settings.parent.mkdir();settings.write_text(json.dumps({'profiles':profiles,'activeProfile':'legacy'}));saved_settings=settings.read_bytes()
   with patch.object(Backend,'get_corpus',return_value=Mock(books=[])):
    b=Backend(root);page=b.page(84);b.configure({'activeProfile':'new'},persist=False)
    self.assertEqual(settings.read_bytes(),saved_settings);self.assertEqual(b.page(84)['docId'],999);self.assertEqual(b.settings['uploadPages'],[])
    with self.assertRaisesRegex(ValueError,'another selected document'):b.save(page)
    b.configure({'activeProfile':'new'});self.assertEqual(b.settings['output'],str(root/'new-edits'))
    restarted=Backend(root);self.assertEqual(restarted.settings['document'],999)
    restarted.configure({'activeProfile':'legacy'});self.assertEqual(restarted.settings['document'],base['docId']);self.assertEqual(restarted.page(84)['text'] if 'text' in restarted.page(84) else restarted.page(84)['docId'],base['docId'])

class ExplicitBoundaryTests(unittest.TestCase):
 def test_explicit_end_keeps_an_entire_missing_verse(self):
  corpus=Corpus(APP/'data');verses=[v for v in corpus.verses if v['book']=='John' and v['chapter']==1 and v['verse'] in (1,2)]
  result=corpus.align([{'id':'one','text':verses[0]['text']}],'John','1:1','1:2')
  self.assertEqual(letters(''.join(l['reference'] for l in result['lines'])),letters(''.join(v['text'] for v in verses)))
  self.assertGreater(result['coverage']['missingReferenceCharacters'],20);self.assertEqual(result['coverage']['boundsSource'],'manual verses')
