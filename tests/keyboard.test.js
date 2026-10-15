import test from 'node:test';import assert from 'node:assert/strict';
import {keyboardEdit,letters,marks} from '../renderer/keyboard.js';
test('Syriac insertion replaces the selection and preserves manuscript line boundary',()=>{assert.deepEqual(keyboardEdit('ܐܒܓ',1,2,'ܠ'),{value:'ܐܠܓ',caret:2});assert.deepEqual(keyboardEdit('ܐܒ',1,1,'Space'),{value:'ܐ ܒ',caret:2})});
test('Backspace removes a complete marked grapheme or the selected range',()=>{assert.deepEqual(keyboardEdit('ܐܒܰ',3,3,'Backspace'),{value:'ܐ',caret:1});assert.deepEqual(keyboardEdit('ܐܒܓ',1,3,'Backspace'),{value:'ܐ',caret:1});assert.deepEqual(keyboardEdit('',0,0,'Backspace'),{value:'',caret:0})});
test('Keyboard offers all 22 letters and vowel and plural marks',()=>{assert.equal(letters.length,22);assert.ok(marks.some(m=>m.text==='\u0308'));assert.ok(marks.some(m=>m.text==='ܰ'))});

test('Requested marks insert exactly their code points',()=>{for(const mark of ['\u0745','\u0307','\u0308']){assert.equal(marks.filter(m=>m.text===mark).length,1);assert.equal(keyboardEdit('ܐ',1,1,mark).value,'ܐ'+mark)}});
