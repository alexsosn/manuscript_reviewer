import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import {homedir} from 'node:os';
import path from 'node:path';
export function pythonPath(){
 const candidates=[process.env.SYRIAC_PYTHON,path.join(homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'),'/usr/local/bin/python3','/opt/homebrew/bin/python3','/usr/bin/python3'];
 return candidates.find(p=>p&&existsSync(p))||'python3';
}
export class Bridge{
 constructor(here,workspace){
  this.next=0;this.waiting=new Map();this.buffer='';
  this.child=spawn(pythonPath(),[path.join(here,'backend.py')],{cwd:here,env:{...process.env,SYRIAC_WORKSPACE:workspace},stdio:['pipe','pipe','pipe']});
  this.child.stdout.setEncoding('utf8');this.child.stdout.on('data',chunk=>{this.buffer+=chunk;let at;while((at=this.buffer.indexOf('\n'))>=0){const raw=this.buffer.slice(0,at);this.buffer=this.buffer.slice(at+1);let msg;try{msg=JSON.parse(raw)}catch{continue}const p=this.waiting.get(msg.id);if(p){this.waiting.delete(msg.id);msg.ok?p.resolve(msg.result):p.reject(new Error(msg.error));}}});
  this.child.stderr.on('data',()=>{});
  this.child.on('exit',()=>{for(const p of this.waiting.values())p.reject(new Error('Python service stopped. Check the Python environment has lxml and cryptography.'));this.waiting.clear();});
  this.child.on('error',e=>{for(const p of this.waiting.values())p.reject(e);this.waiting.clear()});
 }
 request(command,args={}){const id=++this.next;return new Promise((resolve,reject)=>{this.waiting.set(id,{resolve,reject});this.child.stdin.write(JSON.stringify({id,command,args})+'\n')})}
 close(){this.child.kill()}
}
