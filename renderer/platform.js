export const platform=window.syriac??{
 desktop:false,
 async request(command,args={}){const response=await fetch('/api',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command,args})});const data=await response.json();if(!data.ok)throw new Error(data.error);return data.result},
 async chooseFolder(){throw new Error('Choose folders in the desktop app')},
 image(mode,name){return '/image/'+mode+'/'+encodeURIComponent(name)}
};
