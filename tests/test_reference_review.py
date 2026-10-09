import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from reference_review import differences,escape,reference_tag
class ReferenceReviewTests(unittest.TestCase):
 def diff(self,a,b):return differences(a,{'reference':b,'address':'Matthew 3:1'})
 def test_line_breaks_and_marks_are_not_differences(self):
  self.assertEqual(self.diff('ܐܒ\nܓܕ','ܐܒܓܕ'),[])
  self.assertEqual(self.diff('ܐܒ̈. ܓܕ','ܐܒ ܓܕ'),[])
 def test_missing_letter_is_an_alternative_spelling(self):
  result=self.diff('ܘܗܪܐ','ܢܘܗܪܐ');self.assertEqual(len(result),1)
  self.assertEqual(result[0]['referenceSpelling'],'ܢܘܗܪܐ');self.assertEqual(result[0]['kind'],'difference')
 def test_extra_letter_is_not_an_extra_word(self):
  result=self.diff('ܐܒܓ','ܐܒ');self.assertEqual(result[0]['referenceSpelling'],'ܐܒ')
 def test_missing_whole_word_anchors_neighbor(self):
  result=self.diff('ܐܒ ܗܘ','ܐܒ ܓܕ ܗܘ');self.assertEqual(result[0]['kind'],'missing in transcription')
  self.assertIn('ܓܕ',result[0]['referenceSpelling']);self.assertIn('before',result[0]['referenceSpelling']);self.assertEqual(result[0]['offset'],3)
 def test_extra_word_has_empty_reference(self):
  result=self.diff('ܐܒ ܓܕ ܗܘ','ܐܒ ܗܘ');self.assertEqual(result[0]['kind'],'extra in transcription');self.assertTrue(result[0]['referenceSpelling'].startswith('∅'))
 def test_offsets_use_original_utf16_and_css_escape(self):
  result=self.diff('🙂 ܐܒ','🙂 ܐܓ');self.assertEqual(result[0]['offset'],3);self.assertEqual(result[0]['length'],2)
  self.assertEqual(escape('a:b;c\nd'),r'a\u003ab\u003bc\u000ad')

class CommentCompatibilityTests(unittest.TestCase):
 def test_text_uses_native_alternative_and_reason_fields(self):
  tag=reference_tag(3,2,'Reference spelling: ܐܓ\nPassage: Matthew 3:1')
  self.assertIn('unclear {',tag);self.assertIn('alternative:ܐܓ;',tag)
  self.assertIn(' | Passage',tag);self.assertIn(r'Matthew 3\u003a1',tag)
 def test_repair_preserves_existing_tags_and_is_idempotent(self):
  from fix_reference_comments import repair
  from pagexml import parse,N
  from pathlib import Path
  raw=(Path(__file__).parent/'fixtures/synthetic.xml').read_bytes();root=parse(raw)
  line=root.find('.//p:TextLine',N);original=line.get('custom');note='Reference spelling: ܐܓ\nPassage: Matthew 3:1'
  line.set('custom',original+' '+f'comment {{offset:0; length:2; comment:{escape(note)};}}')
  from lxml import etree as E
  fixed,count=repair(E.tostring(root));self.assertEqual(count,1);custom=parse(fixed).find('.//p:TextLine',N).get('custom')
  self.assertTrue(custom.startswith(original));self.assertIn('alternative:ܐܓ;',custom)
  again,_=repair(fixed);self.assertEqual(fixed,again)
