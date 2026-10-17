"use strict";
const fs=require("node:fs"),vm=require("node:vm"),path=require("node:path"),assert=require("node:assert/strict");
const EXT=path.join(__dirname,"../browser-extension"),SID="a".repeat(32),DOI="10.1109/access.2022.3181725";
const RAW="https://ieeexplore.ieee.org/ielx7/6287639/9668973/09792260.pdf";
function fixture(){
 const job={session_id:SID,index:0,doi:DOI,identity_verified:true,identity_source:"IEEE_ARTICLE_URL",ieee_article_id:"9792260",native_until:Date.now()+600000};
 const storage={token:"fixture-token",activeSessionId:SID,managed:{7:job},downloads:{}};
 const calls=[],callbacks={},state={history:[],security:false,failDownload:false,complete:false,downloadState:"in_progress"};
 const chrome={permissions:{contains:async()=>false},storage:{local:{get:async()=>structuredClone(storage),set:async v=>Object.assign(storage,structuredClone(v)),remove:async k=>{delete storage[k];}}},
  action:{setBadgeText:async()=>{}},runtime:{id:"fixture-extension",getManifest:()=>({version:"0.5.0"}),onMessage:{addListener:()=>{}}},
  tabs:{get:async()=>({url:"https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber=9792260"}),query:async()=>[{id:7}],onUpdated:{addListener:()=>{}},create:async()=>({id:9})},
  scripting:{executeScript:async()=>[{result:{}}]},webRequest:{onHeadersReceived:{addListener:(fn,filter,extra)=>{callbacks.network={fn,filter,extra};}}},
  downloads:{download:async options=>{calls.push({download:structuredClone(options)});if(state.failDownload)throw Error("fixture failure");return 12;},
   search:async query=>query.id?[{id:query.id,state:state.downloadState,byExtensionId:"fixture-extension",filename:"C:/Downloads/papers-capture/"+SID+"/0.pdf"}]:state.history,
   onDeterminingFilename:{addListener:fn=>{callbacks.filename=fn;}},onChanged:{addListener:()=>{}},cancel:async()=>{}}};
 const sandbox={chrome,URL,setTimeout:()=>{},console,fetch:async(url,options)=>{
  const data=options?.body?JSON.parse(options.body):null;calls.push({api:String(url).split("/").pop(),data});
  if(String(url).endsWith("/complete"))state.complete=true;
  return {ok:true,json:async()=>String(url).endsWith("/complete")?{papers:[{status:"SAVED",title:"Fixture"}]}:
   {tasks:state.complete?[]:[{session_id:SID,papers:[{doi:DOI,status:"NEED_BROWSER_SAVE",browser_evidence:state.security?{failure_code:"DOWNLOAD_SECURITY"}:{}}]}]}};
 }};
 sandbox.importScripts=(...files)=>files.forEach(file=>vm.runInContext(fs.readFileSync(path.join(EXT,file),"utf8"),sandbox));
 vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path.join(EXT,"background.js"),"utf8"),sandbox);
 const invoke=(name,...args)=>vm.runInContext(name,sandbox)(...args);
 const details=(url=RAW)=>({tabId:7,statusCode:200,url,responseHeaders:[{name:"Content-Type",value:"application/pdf"}]});
 return {storage,calls,state,callbacks,invoke,details,sandbox};
}
(async()=>{
 let count=0;
 {
  const f=fixture();assert.deepEqual(Array.from(f.callbacks.network.filter.urls),["https://ieeexplore.ieee.org/*","https://pdf.sciencedirectassets.com/*"]);assert.deepEqual(Array.from(f.callbacks.network.extra),["responseHeaders"]);count++;
 }
 {
  const f=fixture();await f.invoke("observePdfResponse",f.details());
  assert.equal(f.calls.filter(x=>x.download).length,1);assert.equal(f.calls.find(x=>x.download).download.saveAs,false);
  assert.equal(f.calls.find(x=>x.api==="observe").data.download_trigger,"PDF_RESPONSE");
  await f.invoke("observePdfResponse",{...f.details(),statusCode:206});assert.equal(f.calls.filter(x=>x.download).length,1);
  f.state.downloadState="complete";await f.invoke("completedDownload",12);
  const completion=f.calls.find(x=>x.api==="complete").data;
  assert.equal(completion.download_method,"EXTENSION_REQUEST");assert.equal(completion.extension_initiated,true);assert.equal(completion.download_trigger,"PDF_RESPONSE");
  assert.match(f.storage.lastSuccess.summary,/自动下载/);count++;
 }
 {
  const f=fixture();for(const url of [RAW.replace("09792260","09792261"),RAW+"?arnumber=9792261",RAW.replace("https:","http:"),RAW.replace("ieeexplore.ieee.org","ieeexplore.ieee.org.evil.example")])await f.invoke("observePdfResponse",f.details(url));
  assert.equal(f.calls.filter(x=>x.download).length,0);count++;
 }
 {
  const f=fixture();await f.invoke("observePdfResponse",{...f.details(),responseHeaders:[{name:"Content-Type",value:"text/html"}]});
  for(const statusCode of [401,403,418,429])await f.invoke("observePdfResponse",{...f.details(),statusCode});
  await f.invoke("observePdfResponse",{...f.details(),tabId:8});await f.invoke("observePdfResponse",{...f.details(),tabId:-1});
  assert.equal(f.calls.filter(x=>x.download).length,0);count++;
 }
 {
  const f=fixture();f.storage.managed[7].identity_verified=false;await f.invoke("observePdfResponse",f.details());assert.equal(f.calls.filter(x=>x.download).length,0);count++;
 }
 {
  const f=fixture();f.state.security=true;await f.invoke("observePdfResponse",f.details());assert.equal(f.calls.filter(x=>x.download).length,0);count++;
 }
 {
  const f=fixture();f.state.history=[{url:RAW,finalUrl:RAW,mime:"application/pdf",state:"complete",filename:"C:/old/manual.pdf"}];
  await f.invoke("retryKnownIeeeFile",7,f.storage.managed[7]);
  assert.equal(f.calls.find(x=>x.download).download.url,RAW);assert.equal(f.calls.find(x=>x.api==="observe").data.download_trigger,"MATCHED_DOWNLOAD_URL");
  assert.equal(f.calls.some(x=>x.data?.download_path==="C:/old/manual.pdf"),false);count++;
 }
 {
  const f=fixture();f.storage.managed[7]={session_id:SID,index:0,doi:"10.1016/j.fixture",identity_verified:true,expected_pii:"S0263224124013708"};
  const signed="https://pdf.sciencedirectassets.com/a/1-s2.0-S0263224124013708/main.pdf?X-Amz-Signature=fixture-secret";
  await f.invoke("observePdfResponse",f.details(signed));assert.equal(f.calls.filter(x=>x.download).length,1);
  assert.equal(JSON.stringify(f.storage).includes("fixture-secret"),false);count++;
 }
 {
  const f=fixture();f.state.failDownload=true;await f.invoke("observePdfResponse",f.details());await f.invoke("observePdfResponse",f.details());
  assert.equal(f.calls.filter(x=>x.download).length,1);assert.equal(f.storage.managed[7].auto_pdf_started,false);count++;
 }
 {
  const f=fixture();await new Promise(resolve=>f.callbacks.filename({byExtensionId:"fixture-extension",url:RAW,mime:"application/pdf"},()=>resolve()));
  assert.equal(f.calls.some(x=>x.data?.download_method==="BROWSER_NATIVE"),false);count++;
 }
 {
  const f=fixture();await new Promise(resolve=>f.callbacks.filename({id:31,url:RAW,mime:"application/pdf"},()=>resolve()));
  assert.equal(f.storage.downloads[31].transfer_method,"BROWSER_NATIVE");count++;
 }
 console.log(JSON.stringify({status:"PASS",checks:count,scope:"actual extension functions with mocked Chrome APIs; real automatic file validation still required"}));
})().catch(error=>{console.error(error);process.exitCode=1;});
