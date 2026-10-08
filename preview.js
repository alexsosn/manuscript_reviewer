// Development preview uses the same offline backend. Remote credentials and writes
// are available only through Electron IPC, never the browser preview.
import http from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Bridge} from './bridge.js';
const HERE=path.dirname(fileURLToPath(import.meta.url));const bridge=new Bridge(HERE,process.env.SYRIAC_WORKSPACE||path.dirname(HERE));let settings=await bridge.request('settings');
const readCommands=new Set(['settings','index','page','align','lookup','paleography']);const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.jpg':'image/jpeg','.png':'image/png'};
const server=http.createServer(async(req,res)=>{
 try{
  const url=new URL(req.url,'http://127.0.0.1');
  if(url.pathname==='/api'&&req.method==='POST'){
   if(!req.headers.origin||req.headers.origin!==`http://${req.headers.host}`)throw new Error('Origin rejected');
   let body='';for await(const chunk of req){body+=chunk;if(body.length>2000000)throw new Error('Request too large')}
   const {command,args={}}=JSON.parse(body);if(!readCommands.has(command))throw new Error('Use the desktop app to save files or access Transkribus');
   if(command==='settings'&&Object.keys(args).length)throw new Error('Preview settings are read-only');
   const result=await bridge.request(command,args);res.setHeader('Content-Type','application/json');res.end(JSON.stringify({ok:true,result}));return;
  }
  let file;
  if(url.pathname.startsWith('/image/')){
   const [, ,mode,encoded]=url.pathname.split('/');const name=decodeURIComponent(encoded||'');if(path.basename(name)!==name)throw new Error('Invalid image');
   file=mode==='source'?path.join(settings.images,name):['colour','ink'].includes(mode)?path.join(settings.root,'readable_images',mode,name):null;
  }else{const name=url.pathname==='/'?'index.html':url.pathname.slice(1);file=path.resolve(HERE,'renderer',name);if(!file.startsWith(path.join(HERE,'renderer')+path.sep))throw new Error('Invalid path')}
  if(!file)throw new Error('Image mode not found');res.setHeader('Content-Type',types[path.extname(file)]||'application/octet-stream');res.end(await readFile(file));
 }catch(error){res.statusCode=400;res.setHeader('Content-Type','application/json');res.end(JSON.stringify({ok:false,error:error.message}))}
});server.listen(8770,'127.0.0.1',()=>console.log('Syriac validator read-only preview: http://127.0.0.1:8770'));
process.on('SIGTERM',()=>{server.close();bridge.close()});
