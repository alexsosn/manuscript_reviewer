import sys,unittest,tempfile,json,hashlib
from pathlib import Path
from unittest.mock import Mock,patch
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import Backend
from publishing import Publisher,pages_spec,annotate
from pagexml import model,server_metadata,page_signature
APP=Path(__file__).resolve().parents[1]
class PublishingTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);(self.root/'page').mkdir();self.raw=(APP/'tests/fixtures/synthetic.xml').read_bytes();self.m=model(self.raw,'p.xml','x');(self.root/'page/p.xml').write_bytes(self.raw);(self.root/self.m['image']).write_bytes(b'original-image')
  with patch.object(Backend,'get_corpus',return_value=Mock(books=[])):self.b=Backend(self.root)
  self.b.get_corpus=Mock(return_value=Mock(books=[]))
  self.b.configure({'collection':10,'document':self.m['docId'],'source':str(self.root/'page'),'images':str(self.root),'output':str(self.root/'edits')});self.api=Mock();self.b.api=self.api;self.p=Publisher(self.b)
  self.target=self.doc(20,999,9999,2);self.api.request.side_effect=self.request
 def doc(self,coll,doc,pid,ts):
  return {'md':{'docId':doc,'mainColId':coll,'title':'Independent'},'pageList':{'pages':[{'pageNr':84,'pageId':pid,'imgFileName':self.m['image'],'md5Sum':hashlib.md5(b'original-image').hexdigest(),'tsList':{'transcripts':[{'tsId':ts,'status':'IN_PROGRESS'}]}}]}}
 def request(self,path,**kwargs):
  if path=='collections/list':return json.dumps([{'colId':10,'colName':'Group'},{'colId':20,'colName':'Personal'}]).encode()
  if path.endswith('/fulldoc'):return json.dumps(self.target).encode()
  raise ValueError(path)
 def prepare(self,**patch):return self.p.prepare({'mode':'full','collection':20,'document':999,'notes':False,**patch})
 def test_page_ranges_are_explicit_and_deduplicated(self):
  self.assertEqual(pages_spec('3, 4, 4, 10-12'),[3,4,10,11,12])
  for x in ['0','9-3','3;4','all']:
   with self.assertRaises(ValueError):pages_spec(x)
 def test_full_cannot_target_shared_collection(self):
  with self.assertRaisesRegex(ValueError,'separate collection'):self.prepare(collection=10)
 def test_full_rejects_shared_page_ids_even_for_another_doc_id(self):
  self.target['pageList']['pages'][0]['pageId']=self.m['pageId']
  with self.assertRaisesRegex(ValueError,'shares source page IDs'):self.prepare()
 def test_selected_stale_snapshot_rejected_before_writes(self):
  self.target=self.doc(10,self.m['docId'],self.m['pageId'],self.m['tsId']+1)
  with self.assertRaisesRegex(ValueError,'newer or untracked'):self.prepare(mode='selected',collection=10,document=self.m['docId'],pages='84')
  self.api.upload.assert_not_called()
 def test_independent_target_needs_previous_verified_baseline(self):
  with self.assertRaisesRegex(ValueError,'newer or untracked'):self.prepare()
 def selected_plan(self):
  self.target=self.doc(10,self.m['docId'],self.m['pageId'],self.m['tsId']);return self.prepare(mode='selected',collection=10,document=self.m['docId'],pages='84')
 def test_selected_exact_page_and_source_untouched(self):
  plan=self.selected_plan();self.api.upload.return_value=(self.raw,{'verified':True,'tsId':900,'pageNr':84,'status':'IN_PROGRESS'})
  self.p.run(plan['id']);state=self.p.status(plan['id']);self.assertEqual(state['phase'],'complete');self.assertEqual(state['completed'],1);self.assertEqual(self.api.upload.call_args.args[:3],(10,self.m['docId'],84));self.assertEqual((self.root/'page/p.xml').read_bytes(),self.raw)
  self.p.run(plan['id']);self.assertEqual(self.api.upload.call_count,1)
 def test_uncertain_post_is_reconciled_without_duplicate_upload(self):
  plan=self.selected_plan();folder=self.p.plan_folder(plan['id']);state=self.p.status(plan['id']);state['pages']={'84':{'phase':'sending'}};self.p.write(folder/'state.json',state);submitted=(folder/'pages/84.xml').read_bytes();self.api.pull.return_value=(submitted,{'tsId':900,'pageId':self.m['pageId']})
  self.p.run(plan['id']);self.assertEqual(self.p.status(plan['id'])['phase'],'complete');self.api.upload.assert_not_called()
 def test_uncertain_changed_page_is_not_overwritten(self):
  plan=self.selected_plan();folder=self.p.plan_folder(plan['id']);state=self.p.status(plan['id']);state['pages']={'84':{'phase':'sending'}};self.p.write(folder/'state.json',state);changed=self.raw.replace(b'<Unicode>',b'<Unicode>other',1);self.api.pull.return_value=(changed,{'tsId':900,'pageId':self.m['pageId']})
  self.p.run(plan['id']);self.assertEqual(self.p.status(plan['id'])['phase'],'stopped');self.api.upload.assert_not_called()
 def test_annotation_retains_ocr_and_geometry_and_encodes_marks(self):
  m=self.m;line=m['regions'][0]['lines'][0];text=line['text'];a={'lines':[{'id':line['id'],'reference':'ܐ̈','address':'John 1:1','words':[],'changes':[{'ocrStart':0,'ocrEnd':1,'referenceStart':0,'referenceEnd':2,'ocr':text[:1],'reference':'ܐ̈','kind':'diacritics'}]}]}
  out,count=annotate(self.raw,a);self.assertEqual(count,1);self.assertEqual(model(out,'x','x')['regions'][0]['lines'][0]['text'],text);self.assertIn(b'unclear {',out);self.assertIn(b'reason:SyrNT automated review',out)
 def test_new_private_copy_rebinds_ids_without_touching_source(self):
  plan=self.prepare(document=0);folder=self.p.plan_folder(plan['id'])
  def create(folder,prepared,state):self.p.update(folder,state,document=999)
  self.p.ensure_copy=create;self.api.upload.return_value=(self.raw,{'verified':True,'tsId':3,'pageNr':84,'status':'IN_PROGRESS'});self.p.run(plan['id'])
  self.assertEqual(self.p.status(plan['id'])['phase'],'complete');sent=model(self.api.upload.call_args.args[3],'sent','x');self.assertEqual((sent['docId'],sent['pageId']),(999,9999));self.assertEqual((self.root/'page/p.xml').read_bytes(),self.raw)
 def test_private_copy_failure_never_posts_to_shared_source_text(self):
  plan=self.prepare(document=0);self.target=self.doc(20,self.m['docId'],self.m['pageId'],2)
  self.p.ensure_copy=lambda folder,prepared,state:self.p.update(folder,state,document=self.m['docId'])
  self.p.run(plan['id']);self.assertEqual(self.p.status(plan['id'])['phase'],'stopped');self.api.upload.assert_not_called()
 def test_ambiguous_copy_is_not_created_again(self):
  plan=self.prepare(document=0);folder=self.p.plan_folder(plan['id']);state=self.p.status(plan['id']);state['copyAttempted']=True;self.p.documents=Mock(return_value=[])
  with patch('publishing.time.monotonic',side_effect=[0,301]):
   with self.assertRaisesRegex(ValueError,'still pending'):self.p.ensure_copy(folder,json.loads((folder/'plan.json').read_text()),state)
  self.assertFalse(any('/duplicate?' in call.args[0] for call in self.api.request.call_args_list))
 def test_import_payload_has_both_files_and_no_foreign_transkribus_identity(self):
  plan=self.prepare(document=0);folder=self.p.plan_folder(plan['id']);prepared=json.loads((folder/'plan.json').read_text());xml=self.p.import_xml(folder,prepared['rows'][0]);self.assertNotIn(b'TranskribusMetadata',xml);self.assertEqual(page_signature(xml),page_signature(self.raw));body,content=self.p.multipart('scan.jpg',b'image','scan.xml',xml);self.assertIn('multipart/form-data; boundary=',content);self.assertIn(b'name="img"',body);self.assertIn(b'name="xml"',body)
 def test_forbidden_duplicate_falls_back_only_to_independent_import(self):
  from transkribus import APIError
  plan=self.prepare(document=0);self.p.ensure_copy=Mock(side_effect=APIError(403))
  def imported(folder,prepared,state):self.p.update(folder,state,document=999,importId=123)
  self.p.import_copy=Mock(side_effect=imported)
  self.p.verify_import=lambda folder,prepared,state:self.p.update(folder,state,phase='complete')
  self.p.run(plan['id']);self.assertTrue(self.p.status(plan['id'])['copyForbidden']);self.p.import_copy.assert_called_once();self.api.upload.assert_not_called()
 def test_disconnect_releases_the_publishers_session(self):
  self.b.publisher=self.p;self.b.handle({'command':'disconnect'});self.assertIsNone(self.b.publisher);self.assertIsNone(self.b.api.token)
 def test_resume_checkpoint_is_running_before_worker_starts(self):
  plan=self.selected_plan();state=self.p.status(plan['id']);state['phase']='stopped';self.p.write(self.p.plan_folder(plan['id'])/'state.json',state)
  with patch('publishing.threading.Thread') as thread:
   self.p.start(plan['id']);self.assertEqual(self.p.status(plan['id'])['phase'],'running');thread.return_value.start.assert_called_once()
 def test_dead_worker_lock_does_not_block_resume(self):
  (self.p.folder/'active.lock').write_text(json.dumps({'pid':99999999,'id':'old'}));self.assertFalse(self.p.active());lock=self.p.acquire('new');self.assertEqual(json.loads(lock.read_text())['id'],'new')
 def test_pause_stops_selected_batch_before_any_more_posts(self):
  plan=self.selected_plan();self.p.pause(plan['id']);self.p.run(plan['id']);self.assertEqual(self.p.status(plan['id'])['phase'],'paused');self.api.upload.assert_not_called()

 def test_manual_drafts_are_frozen_when_requested_and_can_be_excluded(self):
  draft=self.raw.replace(b'<Unicode>',b'<Unicode>edited ',1);dest=Path(self.b.settings['output'])/'page/p.xml';dest.parent.mkdir(parents=True);dest.write_bytes(draft)
  included=self.prepare(document=0,drafts=True);automatic=self.prepare(document=0,drafts=False)
  self.assertEqual((self.p.plan_folder(included['id'])/'pages/84.xml').read_bytes(),draft)
  self.assertEqual((self.p.plan_folder(automatic['id'])/'pages/84.xml').read_bytes(),self.raw)
 def test_status_exposes_dead_worker_for_ui_resume(self):
  plan=self.selected_plan();self.b.publisher=self.p
  state=self.p.status(plan['id']);state['phase']='running';self.p.write(self.p.plan_folder(plan['id'])/'state.json',state)
  (self.p.folder/'active.lock').write_text(json.dumps({'pid':99999999,'id':plan['id']}))
  self.assertFalse(self.b.handle({'command':'publishStatus','args':{'id':plan['id']}})['active'])

 def test_prepared_plan_repairs_legacy_custom_before_freezing(self):
  from pagexml import parse,N,validate_web_custom
  from lxml import etree as E
  root=parse(self.raw);root.find('.//p:TextRegion',N).set('custom','readingOrder {index:0;} ');raw=E.tostring(root);(self.root/'page/p.xml').write_bytes(raw)
  plan=self.prepare(document=0);frozen=(self.p.plan_folder(plan['id'])/'pages/84.xml').read_bytes();validate_web_custom(frozen)
  self.assertEqual(page_signature(raw),page_signature(frozen));self.assertEqual((self.root/'page/p.xml').read_bytes(),raw)
