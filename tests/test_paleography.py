import unittest,tempfile,sys,json
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import Backend
from paleography import Paleography
APP=Path(__file__).resolve().parents[1];SAMPLE=APP/'tests/fixtures/synthetic.xml'
class PaleographyTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'page').mkdir();self.source=self.root/'page'/SAMPLE.name;self.raw=SAMPLE.read_bytes();self.source.write_bytes(self.raw)
  with patch.object(Backend,'get_corpus',return_value=Mock(books=[])):self.backend=Backend(self.root)
  self.catalog=Paleography(self.backend);self.page=self.backend.page(84);self.entry={'letter':'ܐ','form':'initial','pageNr':84,'lineId':self.page['regions'][0]['lines'][0]['id'],'rect':[550,150,20,25],'notes':'test note'}
 def tearDown(self):self.temp.cleanup()
 def test_store_and_restore_provenance(self):
  a=self.catalog.read();b=self.catalog.save(self.entry,a['revision']);e=b['examples'][0]
  self.assertEqual(e['pageId'],self.page['pageId']);self.assertEqual(e['lineNumber'],1);self.assertEqual(e['imageFile'],self.page['imageFile']);self.assertEqual(e['rect'],self.entry['rect']);self.assertEqual(self.source.read_bytes(),self.raw)
  c=self.catalog.save({**e,'form':'final','notes':'reclassified'},b['revision']);self.assertEqual(c['examples'][0]['id'],e['id']);self.assertEqual(c['examples'][0]['created'],e['created']);self.assertEqual(c['examples'][0]['form'],'final')
  d=self.catalog.delete(e['id'],c['revision']);self.assertEqual(d['examples'],[]);self.assertEqual(len(list((self.catalog.path().parent/'backups').glob('*.json'))),2)
 def test_stale_write_rejected(self):
  a=self.catalog.read();self.catalog.save(self.entry,a['revision'])
  with self.assertRaisesRegex(ValueError,'another window'):self.catalog.save(self.entry,a['revision'])
 def test_invalid_crop_classification_and_line(self):
  for patch in [{'rect':[-1,10,20,30]},{'rect':[10,10,9999,30]},{'rect':[10,float('nan'),20,30]},{'letter':'x'},{'form':'invented'},{'lineId':'missing'}]:
   with self.assertRaises(ValueError):self.catalog.save({**self.entry,**patch},self.catalog.read()['revision'])
 def test_missing_catalog_does_not_write(self):self.assertEqual(self.catalog.read()['examples'],[]);self.assertFalse(self.catalog.path().exists())
