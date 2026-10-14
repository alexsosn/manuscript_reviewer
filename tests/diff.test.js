import test from 'node:test';import assert from 'node:assert/strict';
import {characterChanges} from '../renderer/diff.js';
test('shows missing and extra dots and letters on both sides',()=>{const r=characterChanges('ܐ̈ܒ.','ܐܒܓ');assert.ok(r.some(x=>x.ocr.includes('̈')&&x.kind==='Diacritics'));assert.ok(r.some(x=>x.reference.includes('ܓ')))});
test('whitespace and manuscript breaks alone do not differ',()=>assert.deepEqual(characterChanges('ܐ\nܒ','ܐ ܒ'),[]));
test('separate changes remain separate across matching text',()=>assert.equal(characterChanges('ܐ.ܒ.ܓ','ܐܒܓ').length,2));
test('does not hide extra OCR words',()=>assert.ok(characterChanges('ܐܒ ܓܕ','ܐܒ').some(x=>x.ocr==='ܓܕ'&&x.reference==='')));
