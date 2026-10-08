"""Single-page versioned API writes with stale-version rejection and read-back."""
import json,urllib.request,urllib.parse,time,base64
from pagexml import parse,N,page_signature
BASE='https://transkribus.eu/TrpServer/rest/'
class Transkribus:
 def __init__(self):self.token=None;self.refresh=None;self.client='transkribus-api-client';self.expires=0
 def login(self,user=None,password=None,saved=False):
  if saved:
   from saved_login import access_token
   self.token=access_token();self.refresh=None
  else:
   values={'grant_type':'password','username':user,'password':password,'client_id':self.client}
   self._token(values)
  claims=json.loads(base64.urlsafe_b64decode(self.token.split('.')[1]+'==='));self.expires=claims.get('exp',time.time()+240)
  return {'connected':True,'username':claims.get('preferred_username','Transkribus account')}
 def _token(self,values):
  req=urllib.request.Request('https://account.readcoop.eu/auth/realms/readcoop/protocol/openid-connect/token',urllib.parse.urlencode(values).encode())
  try:
   with urllib.request.urlopen(req,timeout=45) as response:data=json.load(response)
  except urllib.error.HTTPError as e:raise ValueError('Login failed (HTTP '+str(e.code)+'). Credentials were not saved.') from None
  self.token=data['access_token'];self.refresh=data.get('refresh_token')
 def request(self,path,data=None):
  if not self.token:raise ValueError('Connect to Transkribus first')
  if self.expires<time.time()+20:
   if self.refresh:self._token({'grant_type':'refresh_token','refresh_token':self.refresh,'client_id':self.client});self.expires=time.time()+180
   else:self.login(saved=True)
  req=urllib.request.Request(BASE+path,data=data,headers={'Authorization':'Bearer '+self.token,'Accept':'application/json' if data is not None or path.endswith('fulldoc') else 'application/xml','Content-Type':'application/xml; charset=UTF-8'})
  try:
   with urllib.request.urlopen(req,timeout=60) as response:return response.read()
  except urllib.error.HTTPError as e:raise ValueError('Transkribus API returned HTTP '+str(e.code)) from None
 def remote(self,coll,doc,nr):
  document=json.loads(self.request(f'collections/{coll}/{doc}/fulldoc'))
  page=next(p for p in document['pageList']['pages'] if p['pageNr']==nr)
  return page,page['tsList']['transcripts'][0]
 def pull(self,coll,doc,nr):
  page,ts=self.remote(coll,doc,nr);raw=self.request(f'collections/{coll}/{doc}/{nr}/text')
  return raw,{'tsId':ts['tsId'],'pageId':page['pageId'],'docId':doc,'pageNr':nr,'status':ts['status'],'image':page['imgFileName']}
 def upload(self,coll,doc,nr,raw,expected):
  page,current=self.remote(coll,doc,nr)
  if current['tsId']!=expected['tsId']:raise ValueError('Server version changed. Download the current page and reconcile it with your local edits before uploading.')
  root=parse(raw);m=root.find('.//p:TranskribusMetadata',N)
  if int(m.get('pageId'))!=page['pageId'] or int(m.get('docId'))!=doc or int(m.get('pageNr'))!=nr:raise ValueError('Server/page identity mismatch')
  query=urllib.parse.urlencode({'status':current['status'],'parent':current['tsId'],'overwrite':'false','toolName':'Syriac validator','note':'Locally reviewed PAGE layout and transcription; one-page upload.'})
  result=json.loads(self.request(f'collections/{coll}/{doc}/{nr}/text?'+query,data=raw))
  # A failed read-back must not lead to retrying the POST blindly.
  try:
   downloaded=self.request(f'collections/{coll}/{doc}/{nr}/text');p,new=self.remote(coll,doc,nr)
   if new['tsId']!=result['tsId'] or page_signature(downloaded)!=page_signature(raw):raise ValueError('Saved PAGE differs from the submitted layout/text')
   return downloaded,{'verified':True,'tsId':result['tsId'],'parentTsId':current['tsId'],'pageNr':nr,'status':new['status']}
  except Exception as error:
   return None,{'verified':False,'tsId':result['tsId'],'parentTsId':current['tsId'],'pageNr':nr,'warning':'Upload was accepted, but read-back verification failed: '+str(error)+'. Do not submit again; inspect or download the server page.'}
