import {app,BrowserWindow,ipcMain,dialog,protocol,net} from 'electron';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {existsSync} from 'node:fs';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
import {Bridge} from './bridge.js';
const HERE=path.dirname(fileURLToPath(import.meta.url));
protocol.registerSchemesAsPrivileged([{scheme:'syriac-image',privileges:{standard:true,secure:true,supportFetchAPI:true,corsEnabled:true}}]);
let bridge,settings,window;
const allowed=new Set(['settings','index','page','save','align','lookup','login','disconnect','pull','upload','paleography','paleoSave','paleoDelete']);
function parentWorkspace(start){let p=start;for(let i=0;i<9;i++){if(existsSync(path.join(p,'Preliminary_Setup__BL_Add_MS_14,470')))return p;const q=path.dirname(p);if(q===p)break;p=q}return null}
async function create(){
 const persisted=path.join(app.getPath('userData'),'workspace.json');let workspace=process.env.SYRIAC_WORKSPACE||parentWorkspace(HERE);
 if(!workspace){try{workspace=JSON.parse(await readFile(persisted,'utf8')).root}catch{}}
 if(!workspace){const picked=await dialog.showOpenDialog({title:'Choose the manuscript workspace (images and PAGE XML)',properties:['openDirectory']});if(picked.canceled){app.quit();return}workspace=picked.filePaths[0]}
 const backendHere=app.isPackaged?process.resourcesPath:HERE;bridge=new Bridge(backendHere,workspace);settings=await bridge.request('settings');
 protocol.handle('syriac-image',req=>{
  const url=new URL(req.url),name=decodeURIComponent(url.pathname.slice(1));
  if(!name||path.basename(name)!==name)return new Response('',{status:400});
  const folder=url.hostname==='source'?settings.images:['colour','ink'].includes(url.hostname)?path.join(settings.root,'readable_images',url.hostname):null;
  if(!folder)return new Response('',{status:404});return net.fetch(pathToFileURL(path.join(folder,name)).href);
 });
 ipcMain.handle('request',async(event,command,args)=>{
  if(!allowed.has(command)||event.sender!==window.webContents)throw new Error('Request rejected');
  if(command==='settings'){settings=await bridge.request(command,args);return settings}return bridge.request(command,args);
 });
 ipcMain.handle('chooseFolder',async(event,kind)=>{
  if(event.sender!==window.webContents||!['root','source','images','output'].includes(kind))throw new Error('Folder request rejected');
  const picked=await dialog.showOpenDialog(window,{title:'Choose '+kind+' folder',properties:['openDirectory']});
  if(picked.canceled)return null;settings=await bridge.request('settings',{[kind]:picked.filePaths[0]});
  if(kind==='root'){await mkdir(app.getPath('userData'),{recursive:true});await writeFile(persisted,JSON.stringify({root:settings.root}));}
  return settings;
 });
 window=new BrowserWindow({width:1580,height:1020,minWidth:1120,minHeight:700,title:'Syriac validator',webPreferences:{preload:path.join(HERE,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
 window.webContents.setWindowOpenHandler(()=>({action:'deny'}));window.webContents.on('will-navigate',event=>event.preventDefault());
 let closing=false;window.on('close',event=>{if(closing)return;event.preventDefault();window.webContents.send('prepare-close')});
 ipcMain.on('close-ready',event=>{if(event.sender===window.webContents){closing=true;window.close()}});
 ipcMain.on('close-failed',(event,message)=>{if(event.sender===window.webContents)dialog.showErrorBox('Local edits could not be saved',message)});
 await window.loadFile(path.join(HERE,'renderer/index.html'));
 console.log('Syriac validator desktop window loaded');
}
app.whenReady().then(create).catch(error=>{dialog.showErrorBox('Cannot start Syriac validator',error.message);app.quit()});
app.on('window-all-closed',()=>{bridge?.close();app.quit()});
