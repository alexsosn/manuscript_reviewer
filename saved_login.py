import base64,json,plistlib,zipfile,re,urllib.request,urllib.parse
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from cryptography.hazmat.primitives.padding import PKCS7

def access_token():
 d=plistlib.loads((Path.home()/'Library/Preferences/eu.transkribus.swt_gui.plist').read_bytes())
 def find(x):
  if isinstance(x,dict):
   for k,v in x.items():
    if isinstance(v,str) and 'refreshToken' in v:
     yield json.loads(v)
    elif isinstance(v,dict): yield from find(v)
 items=list(find(d))
 if len(items)!=1: raise RuntimeError('Expected exactly one saved Transkribus login')
 with zipfile.ZipFile(Path.home()/'Applications/Transkribus-1.29.0/Transkribus-1.29.0.jar') as z:
  s=z.read('eu/transkribus/swt_gui/TrpGuiPrefs.java').decode()
 key=re.search(r'^\s*final static String wtf = "([^"]+)";',s,re.M).group(1)
 dec=Cipher(algorithms.AES(base64.b64decode(key+'===')),modes.ECB()).decryptor()
 raw=dec.update(base64.b64decode(items[0]['refreshToken']))+dec.finalize()
 unpad=PKCS7(128).unpadder(); refresh=(unpad.update(raw)+unpad.finalize()).decode()
 claims=json.loads(base64.urlsafe_b64decode(refresh.split('.')[1]+'==='))
 body=urllib.parse.urlencode({'grant_type':'refresh_token','refresh_token':refresh,'client_id':claims['azp']}).encode()
 req=urllib.request.Request('https://account.readcoop.eu/auth/realms/readcoop/protocol/openid-connect/token',body)
 try:
  with urllib.request.urlopen(req,timeout=45) as r: response=json.load(r)
 except urllib.error.HTTPError as e: raise RuntimeError('Saved-login authentication failed: HTTP '+str(e.code)) from None
 return response['access_token']
def get(path,token):
 req=urllib.request.Request('https://transkribus.eu/TrpServer/rest/'+path,headers={'Authorization':'Bearer '+token})
 with urllib.request.urlopen(req,timeout=45) as r: return r.read()
