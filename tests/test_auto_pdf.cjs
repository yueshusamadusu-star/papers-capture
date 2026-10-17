"use strict";
const fs=require("node:fs"),vm=require("node:vm"),path=require("node:path"),assert=require("node:assert/strict");
const EXT=path.join(__dirname,"../browser-extension"),SID="a".repeat(32),DOI="10.1109/access.2022.3181725";
const RAW="https://ieeexplore.ieee.org/ielx7/6287639/9668973/09792260.pdf",PDF=new TextEncoder().encode("%PDF-1.4\nfixture\n%%EOF");
function fixture(){
 const job={session_id:SID,index:0,doi:DOI,identity_verified:true,identity_source:"IEEE_ARTICLE_URL",ieee_article_id:"9792260",native_until:Date.now()+600000};
 const storage={token:"fixture-token",activeSessionId:SID,managed:{7:job},downloads:{}};
 const calls=[],callbacks={},state={history:[],security:false,failFetch:false,complete:false,status:200,mime:"application/pdf",body:PDF,saveOk:true,finalUrl:null};
 const chrome={permissions:{contains:async()=>false},storage:{local:{get:async()=>structuredClone(storage),set:async v=>Object.assign(storage,structuredClone(v)),remove:async k=>{delete storage[k];}}},
  action:{setBadgeText:async()=>{}},runtime:{id:"fixture-extension",getManifest:()=>({version:"0.5.1"}),onMessage:{addListener:fn=>{callbacks.message=fn;}}},
  tabs:{get:async()=>({url:"https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber=9792260"}),query:async()=>[{id:7}],onUpdated:{addListener:()=>{}},create:async()=>({id:9})},
  scripting:{executeScript:async()=>[{result:{}}]},webRequest:{onHeadersReceived:{addListener:(fn,filter,extra)=>{callbacks.network={fn,filter,extra};}}},
  downloads:{download:async options=>{calls.push({chromeDownload:options});return 12;},search:async()=>state.history,
   onDeterminingFilename:{addListener:fn=>{callbacks.filename=fn;}},onChanged:{addListener:()=>{}},cancel:async()=>{}}};
 const sandbox={chrome,URL,setTimeout,clearTimeout,AbortController,Uint8Array,TextDecoder,console,fetch:async(url,options)=>{
  if(String(url).startsWith('https://')){
   calls.push({remote:String(url),options});if(state.failFetch)throw Error('network fixture');
   const response=new Response(state.body,{status:state.status,headers:{'Content-Type':state.mime}});
   Object.defineProperty(response,'url',{value:state.finalUrl||String(url)});return response;
  }
  const isBytes=String(url).endsWith('/pdf-bytes'),data=isBytes?null:options?.body?JSON.parse(options.body):null;
  calls.push({api:String(url).split('/').pop(),data,headers:options?.headers,bytes:isBytes?options.body:null});
  if(isBytes&&state.saveOk)state.complete=true;
  return {ok:!isBytes||state.saveOk,json:async()=>isBytes?{papers:[{status:'SAVED',title:'Fixture',file:{saved_path:'D:/论文/Fixture.pdf'}}]}:
   {tasks:state.complete?[]:[{session_id:SID,papers:[{doi:DOI,status:'NEED_BROWSER_SAVE',browser_evidence:state.security?{failure_code:'DOWNLOAD_SECURITY'}:{}}]}]}};
 }};
 sandbox.importScripts=(...files)=>files.forEach(file=>vm.runInContext(fs.readFileSync(path.join(EXT,file),'utf8'),sandbox));
 vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path.join(EXT,'background.js'),'utf8'),sandbox);
 const invoke=(name,...args)=>vm.runInContext(name,sandbox)(...args);
 const details=(url=RAW)=>({tabId:7,statusCode:200,url,responseHeaders:[{name:'Content-Type',value:'application/pdf'}]});
 return {storage,calls,state,callbacks,invoke,details,sandbox};
}
(async()=>{
 let count=0;
 {
  const f=fixture();assert.deepEqual(Array.from(f.callbacks.network.filter.urls),['https://ieeexplore.ieee.org/*','https://pdf.sciencedirectassets.com/*','https://pubs.aip.org/*']);assert.deepEqual(Array.from(f.callbacks.network.extra),['responseHeaders']);count++;
 }
 {
  const f=fixture();await f.invoke('observePdfResponse',f.details());await f.invoke('observePdfResponse',{...f.details(),statusCode:206});
  assert.equal(f.calls.filter(x=>x.remote).length,1);assert.equal(f.calls.filter(x=>x.chromeDownload).length,0);
  const remote=f.calls.find(x=>x.remote),save=f.calls.find(x=>x.api==='pdf-bytes');
  assert.equal(remote.options.credentials,'include');assert.equal(remote.options.headers,undefined);
  assert.equal(save.headers['X-Papers-Session'],SID);assert.equal(save.headers['X-Papers-Trigger'],'PDF_RESPONSE');assert.deepEqual(save.bytes,PDF);
  assert.equal(f.calls.find(x=>x.api==='observe').data.download_method,'EXTENSION_FETCH');
  assert.match(f.storage.lastSuccess.summary,/自动保存/);assert.match(f.storage.lastSuccess.summary,/Fixture\.pdf/);count++;
 }
 {
  const f=fixture();for(const url of [RAW.replace('09792260','09792261'),RAW+'?arnumber=9792261',RAW.replace('https:','http:'),RAW.replace('ieeexplore.ieee.org','ieeexplore.ieee.org.evil.example')])await f.invoke('observePdfResponse',f.details(url));
  assert.equal(f.calls.filter(x=>x.remote).length,0);count++;
 }
 {
  const f=fixture();await f.invoke('observePdfResponse',{...f.details(),responseHeaders:[{name:'Content-Type',value:'text/html'}]});
  for(const statusCode of [401,403,418,429])await f.invoke('observePdfResponse',{...f.details(),statusCode});
  await f.invoke('observePdfResponse',{...f.details(),tabId:8});await f.invoke('observePdfResponse',{...f.details(),tabId:-1});
  assert.equal(f.calls.filter(x=>x.remote).length,0);count++;
 }
 {
  const f=fixture();f.storage.managed[7].identity_verified=false;await f.invoke('observePdfResponse',f.details());assert.equal(f.calls.filter(x=>x.remote).length,0);count++;
 }
 {
  const f=fixture();f.state.security=true;await f.invoke('observePdfResponse',f.details());assert.equal(f.calls.filter(x=>x.remote).length,0);count++;
 }
 {
  const f=fixture();f.state.history=[{url:RAW,finalUrl:RAW,mime:'application/pdf',state:'complete',filename:'C:/old/manual.pdf'}];
  await f.invoke('retryKnownIeeeFile',7,f.storage.managed[7]);assert.equal(f.calls.find(x=>x.remote).remote,RAW);
  assert.equal(f.calls.find(x=>x.api==='pdf-bytes').headers['X-Papers-Trigger'],'MATCHED_DOWNLOAD_URL');
  assert.equal(f.calls.some(x=>x.data?.download_path==='C:/old/manual.pdf'),false);count++;
 }
 {
  const f=fixture();f.storage.managed[7]={session_id:SID,index:0,doi:'10.1016/j.fixture',identity_verified:true,expected_pii:'S0263224124013708'};
  const signed='https://pdf.sciencedirectassets.com/a/1-s2.0-S0263224124013708/main.pdf?X-Amz-Signature=fixture-secret';
  await f.invoke('observePdfResponse',f.details(signed));assert.equal(f.calls.filter(x=>x.api==='pdf-bytes').length,1);
  assert.equal(JSON.stringify(f.storage).includes('fixture-secret'),false);assert.equal(JSON.stringify(f.calls.find(x=>x.api==='pdf-bytes').headers).includes('fixture-secret'),false);count++;
 }
 {
  const f=fixture();f.state.failFetch=true;await f.invoke('observePdfResponse',f.details());await f.invoke('observePdfResponse',f.details());
  assert.equal(f.calls.filter(x=>x.remote).length,1);assert.equal(f.calls.filter(x=>x.chromeDownload).length,0);assert.equal(f.storage.managed[7].auto_pdf_started,false);count++;
 }
 {
  for(const status of [206,401,403,418,429]){const f=fixture();f.state.status=status;await f.invoke('observePdfResponse',f.details());assert.equal(f.calls.some(x=>x.api==='pdf-bytes'),false);assert(f.storage.lastFailure);}
  for(const body of [new TextEncoder().encode('<html>Login</html>'),new TextEncoder().encode('%PDF-1.4\ntruncated')]){const f=fixture();f.state.body=body;await f.invoke('observePdfResponse',f.details());assert.equal(f.state.complete,false);}
  count++;
 }
 {
  const f=fixture();f.state.finalUrl=RAW.replace('09792260','09792261');await f.invoke('observePdfResponse',f.details());assert.equal(f.state.complete,false);count++;
 }
 {
  const f=fixture();f.state.saveOk=false;await f.invoke('observePdfResponse',f.details());assert.equal(f.storage.lastSuccess,undefined);assert.equal(f.storage.lastFailure.code,'SAVE_DIRECTORY');count++;
 }
 {
  const f=fixture();await new Promise(resolve=>f.callbacks.filename({byExtensionId:'fixture-extension',url:RAW,mime:'application/pdf'},()=>resolve()));
  assert.equal(f.calls.some(x=>x.data?.download_method==='BROWSER_NATIVE'),false);count++;
 }
 {
  const f=fixture();await new Promise(resolve=>f.callbacks.filename({id:31,url:RAW,mime:'application/pdf'},()=>resolve()));assert.equal(f.storage.downloads[31].transfer_method,'BROWSER_NATIVE');count++;
 }
 {
  const f=fixture();vm.runInContext('DIRECT_PDF_LIMIT',f.sandbox);
  const response={status:200,headers:{get:key=>key==='content-type'?'application/pdf':String(26*1024*1024)}};
  await assert.rejects(f.invoke('pdfResponseBytes',response));count++;
 }
 {
  const f=fixture();f.storage.managed[7]={session_id:SID,index:0,doi:'10.1063/1.3581223',identity_verified:true,article_page:'https://pubs.aip.org/aip/rsi/article-abstract/82/4/046109/353538/title'};
  const file='https://pubs.aip.org/aip/rsi/article-pdf/82/4/046109/353538/046109_1_online.pdf';
  assert.equal(await f.invoke('aipFileIdentity',f.storage.managed[7],file),true);
  assert.equal(await f.invoke('aipFileIdentity',f.storage.managed[7],file.replace('/046109/','/046110/')),false);
  assert.equal(await f.invoke('aipFileIdentity',f.storage.managed[7],file.replace('pubs.aip.org','pubs.aip.org.evil.example')),false);
  assert.equal(await f.invoke('aipFileIdentity',f.storage.managed[7],'https://pubs.aip.org/aip/rsi/article-pdf/doi/10.1063/1.3581223/353538/file.pdf'),true);
  assert.equal(await f.invoke('aipFileIdentity',f.storage.managed[7],'https://pubs.aip.org/aip/rsi/article-pdf/doi/10.1063/1.3581224/353538/file.pdf'),false);
  await f.invoke('observePdfResponse',f.details(file));assert.equal(f.state.complete,true);assert.equal(f.calls.some(x=>x.chromeDownload),false);count++;
 }
 {
  const f=fixture(),job={session_id:SID,index:0,doi:'10.1063/1.3581223',identity_verified:true,article_page:'https://pubs.aip.org/aip/rsi/article-abstract/82/4/046109/353538/title'};
  f.storage.managed[7]=job;f.state.mime='text/html';f.state.body=new TextEncoder().encode('<html>Sign in or buy this article</html>');
  await f.invoke('startDownload',7,job,'https://pubs.aip.org/aip/rsi/article-pdf/82/4/046109/353538/046109_1_online.pdf');
  assert.equal(f.state.complete,false);assert.equal(f.calls.some(x=>x.chromeDownload),false);assert.equal(f.storage.lastFailure.code,'FETCH_PDF');count++;
 }
 console.log(JSON.stringify({status:'PASS',checks:count,scope:'real extension functions with mocked Chrome/network; actual no-dialog download still pending'}));
})().catch(error=>{console.error(error);process.exitCode=1;});
