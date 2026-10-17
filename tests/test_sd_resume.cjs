"use strict";
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const EXT=path.join(__dirname,'../browser-extension'),SID='b'.repeat(32),DOI='10.1016/j.measurement.2019.07.014',PII='S0263224119306359';
const ARTICLE='https://www.sciencedirect.com/science/article/pii/'+PII,PDF='https://pdf.sciencedirectassets.com/a/1-s2.0-'+PII+'/main.pdf?X-Amz-Signature=fixture-private';
function fixture(){
 const storage={token:'fixture',activeSessionId:SID,managed:{},downloads:{}},calls=[],callbacks={};
 const state={attemptCounter:0,remoteStatus:200,mime:"application/pdf",body:"%PDF-1.4\nfixture\n%%EOF",complete:false,binding:true,clicked:true,tabUrl:PDF,metadataDoi:DOI,snapshot:{doi:DOI,pdf_links:[],auth_links:[],pdf_controls:1,institution_recognized:false,password_form:false,no_access:false}};
 const paper={doi:DOI,status:'ACCESS_UNKNOWN',article_url:'https://doi.org/'+DOI};
 const chrome={storage:{local:{get:async()=>structuredClone(storage),set:async x=>Object.assign(storage,structuredClone(x)),remove:async k=>delete storage[k]}},
  runtime:{id:'fixture',getManifest:()=>({version:'0.5.5'}),onMessage:{addListener:f=>callbacks.message=f}},action:{setBadgeText:async()=>{}},
  tabs:{get:async id=>({id,url:state.tabUrl,status:'complete'}),onUpdated:{addListener:f=>callbacks.updated=f},onActivated:{addListener:f=>callbacks.activated=f},query:async()=>[{id:9,url:state.tabUrl}],update:async(id,options)=>{calls.push({navigate:options.url});return {id};},create:async()=>{calls.push('create');return {id:10};}},
  scripting:{executeScript:async o=>{calls.push({script:o.files?.[0]});return [{result:o.func?{clicked:state.clicked}:structuredClone(state.snapshot)}];}},
  downloads:{search:async()=>[],onDeterminingFilename:{addListener:()=>{}},onChanged:{addListener:()=>{}}},
  webRequest:{onHeadersReceived:{addListener:()=>{}}}};
 const sandbox={chrome,URL,setTimeout:()=>{},clearTimeout,AbortController,Uint8Array,TextDecoder,console,fetch:async(url,options)=>{
  if(String(url).startsWith('https://')){calls.push({remote:String(url)});if(state.networkError)throw Error('network fixture with private URL');const r=new Response(state.body,{status:state.remoteStatus,headers:{'Content-Type':state.mime}});Object.defineProperty(r,'url',{value:String(url)});return r;}
  const endpoint=String(url).split('/').pop(),data=options?.body&&endpoint!=='pdf-bytes'?JSON.parse(options.body):null;calls.push({endpoint,data});
  if(endpoint==='download-attempt'){
   if(data.action==='begin'){
    if(state.busy)return {ok:true,json:async()=>({status:'BUSY',attempt:paper.active_attempt})};
    paper.active_attempt={id:String(++state.attemptCounter).padStart(32,'0'),link_refreshes:0};
   }else if(data.action==='refresh-link'){
    if(paper.active_attempt?.link_refreshes)return {ok:true,json:async()=>({status:'EXHAUSTED'})};
    paper.active_attempt.link_refreshes=1;
   }
   return {ok:true,json:async()=>({status:'READY',attempt:paper.active_attempt,...(data.action==='refresh-link'?{article_url:ARTICLE}:{})})};
  }
  if(endpoint==='pdf-bytes'){state.complete=true;return {ok:true,json:async()=>({papers:[{status:'SAVED',title:'Fixture',file:{saved_path:'D:/论文/Fixture.pdf'}}]})};}
  return {ok:true,json:async()=>endpoint==='paper-binding'?(state.binding?{status:'BOUND',doi:state.metadataDoi,source:'Crossref',publisher_pii:PII,publisher_article_url:ARTICLE}:{status:'UNKNOWN'}):{tasks:state.complete?[]:(state.tasks||[{session_id:SID,current_index:0,papers:[paper]}])}};
 }};
 sandbox.importScripts=(...files)=>files.forEach(f=>vm.runInContext(fs.readFileSync(path.join(EXT,f),'utf8'),sandbox));vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path.join(EXT,'background.js'),'utf8'),sandbox);
 return {storage,calls,callbacks,state,paper,invoke:(fn,...args)=>vm.runInContext(fn,sandbox)(...args)};
}
(async()=>{
 let checks=0;
 {const f=fixture();await f.invoke('adoptCurrent',{id:9,url:PDF});assert.equal(f.storage.managed[9].expected_pii,PII);await f.invoke('checkTab',9,true);assert(f.state.complete);assert.equal(f.calls.filter(x=>x.remote).length,1);assert(!JSON.stringify(f.storage).includes('fixture-private'));checks++;}
 {const f=fixture();f.state.tabUrl=PDF.replace(PII,'S0263224119306358');await assert.rejects(f.invoke('adoptCurrent',{id:9,url:f.state.tabUrl}));assert.equal(f.calls.filter(x=>x.remote).length,0);checks++;}
 {const f=fixture();f.state.binding=false;await assert.rejects(f.invoke('adoptCurrent',{id:9,url:PDF}));assert.equal(f.calls.filter(x=>x.remote).length,0);checks++;}
 {const f=fixture();f.state.metadataDoi='10.1000/wrong';await assert.rejects(f.invoke('adoptCurrent',{id:9,url:PDF}));assert(!f.state.complete);checks++;}
 {const f=fixture();await f.invoke('handleTabReady',9);assert(f.state.complete);assert.equal(f.calls.filter(x=>x.remote).length,1);checks++;}
 {const f=fixture();await f.invoke('observePdfResponse',{tabId:9,statusCode:200,url:PDF,responseHeaders:[{name:'Content-Type',value:'application/pdf'}]});assert(f.state.complete);assert.equal(f.calls.find(x=>x.endpoint==='observe').data.identity_source,'CROSSREF_PII');checks++;}
 {const f=fixture();f.state.tabUrl=ARTICLE;await f.invoke('handleTabReady',9);assert(f.storage.managed[9].control_clicked);assert(f.calls.some(x=>x.script==='watch_article.js'));assert(!f.state.complete);checks++;}
 {const f=fixture();f.state.tabUrl=ARTICLE;f.state.snapshot.doi='10.1000/conflict';await f.invoke('handleTabReady',9);assert.equal(f.storage.managed[9],undefined);checks++;}
 {const f=fixture();f.state.tabUrl=ARTICLE;await f.invoke('handleTabReady',9);const before=f.calls.filter(x=>x.endpoint==='observe').length;await f.invoke('handleTabReady',9);assert.equal(f.calls.filter(x=>x.endpoint==='observe').length,before);f.state.snapshot.institution_recognized=true;await f.invoke('handleTabReady',9);assert.equal(f.calls.filter(x=>x.endpoint==='observe').length,before+1);checks++;}
 {const f=fixture();f.paper.status='SKIPPED_BY_USER';await f.invoke('handleTabReady',9);assert.equal(f.calls.filter(x=>x.remote||x.endpoint==='paper-binding').length,0);checks++;}
 {const f=fixture();f.paper.publisher_binding={source:'Crossref',doi:DOI,publisher_pii:PII,publisher_article_url:ARTICLE};await f.invoke('handleTabReady',9);assert(f.state.complete);assert.equal(f.calls.filter(x=>x.endpoint==='paper-binding').length,0);checks++;}
 {const f=fixture();f.state.tabUrl='https://www.sciencedirect.com/unrelated';await f.invoke('handleTabReady',9);assert.equal(f.calls.filter(x=>x.endpoint||x.remote||x.script).length,0);checks++;}
 {const f=fixture();f.state.tabUrl=ARTICLE;const reply=await new Promise(resolve=>f.callbacks.message({action:'article-ready'},{tab:{id:9},url:ARTICLE},resolve));assert.match(reply.status,/View PDF/);assert(f.storage.managed[9]);checks++;}
 {
  let mutate,debounced,label='View PDF',body='',sent=0;
  const sandbox={document:{body:{get innerText(){return body;}},documentElement:{},querySelector:()=>({content:DOI}),querySelectorAll:()=>[{innerText:label,getClientRects:()=>[{}],getAttribute:()=>''}]},
   MutationObserver:class{constructor(f){mutate=f;}observe(){}disconnect(){}},clearTimeout:()=>{},setTimeout:(f,delay)=>{if(delay===800)debounced=f;},chrome:{runtime:{sendMessage:async message=>{assert.equal(message.action,'article-ready');assert.deepEqual(Object.keys(message),['action']);sent++;}}}};
  vm.createContext(sandbox);const code=fs.readFileSync(path.join(EXT,'watch_article.js'),'utf8');vm.runInContext(code,sandbox);
  mutate();debounced();assert.equal(sent,0);body='Brought to you by Zhejiang University Library';mutate();debounced();assert.equal(sent,1);
  mutate();debounced();assert.equal(sent,1);label='Download PDF';mutate();debounced();assert.equal(sent,2);checks++;
 }
 {const f=fixture();f.state.tabUrl=ARTICLE;f.state.snapshot.doi='';await f.invoke('handleTabReady',9);assert(f.storage.managed[9].control_clicked);assert.equal(f.calls.find(x=>x.endpoint==='observe').data.identity_source,'CROSSREF_PII');checks++;}
 {const f=fixture();f.state.tabUrl=ARTICLE;await f.invoke('handleTabReady',9);assert(f.storage.managed[9].control_clicked);await f.invoke('resetArticleNavigation',9);assert.equal(f.storage.managed[9].control_clicked,false);await f.invoke('handleTabReady',9);assert(f.storage.managed[9].control_clicked);checks++;}
 function enrolled(f,sid=SID,pii=PII){return {session_id:sid,current_index:0,papers:[{...f.paper,publisher_binding:{source:'Crossref',doi:DOI,publisher_pii:pii,publisher_article_url:ARTICLE.replace(PII,pii)}}]};}
 {const f=fixture();f.storage.activeSessionId='c'.repeat(32);f.state.tasks=[enrolled(f)];await f.invoke('handleTabReady',9);assert(f.state.complete);assert.equal(f.storage.activeSessionId,SID);checks++;}
 {const f=fixture();const old='c'.repeat(32);f.storage.activeSessionId=old;f.state.tasks=[enrolled(f,old,'S0263224119306358'),enrolled(f)];await f.invoke('handleTabReady',9);assert(f.state.complete);assert.equal(f.storage.managed[9].session_id,SID);checks++;}
 {const f=fixture();f.storage.activeSessionId='c'.repeat(32);const reply=await new Promise(resolve=>f.callbacks.message({action:'check',session_id:SID},{url:'chrome-extension://fixture/popup.html'},resolve));assert.match(reply.status,/已自动保存PDF/);assert(f.state.complete);checks++;}
 {const f=fixture();const other='c'.repeat(32);f.storage.activeSessionId='d'.repeat(32);f.state.tasks=[enrolled(f),enrolled(f,other)];assert.equal(await f.invoke('restoreScienceDirect',{id:9,url:PDF}),false);assert.equal(f.storage.lastResume.code,'AMBIGUOUS_TASK');assert.equal(f.calls.filter(x=>x.remote).length,0);assert(await f.invoke('restoreScienceDirect',{id:9,url:PDF},other));assert.equal(f.storage.managed[9].session_id,other);checks++;}
 {const f=fixture();const old='c'.repeat(32);f.storage.activeSessionId=old;f.state.tasks=[enrolled(f,old,'S0263224119306358'),enrolled(f)];const context=await f.invoke('popupTaskContext',f.state.tasks);assert.equal(context.recommended_session_id,SID);assert.equal(context.extension_version,'0.5.5');const trace=f.calls.find(x=>x.endpoint==='extension-diagnostic');assert(trace);assert(!JSON.stringify(trace.data).includes('fixture-private'));assert(!JSON.stringify(trace.data).includes('https://'));checks++;}
 {const f=fixture();f.state.tabUrl=PDF.replace(PII,'S0263224119306358');await assert.rejects(f.invoke('adoptCurrent',{id:9,url:f.state.tabUrl}),/预期 S0263224119306359，当前 S0263224119306358/);assert.equal(f.storage.lastResume.code,'PII_MISMATCH');assert.equal(f.calls.filter(x=>x.remote).length,0);checks++;}
 async function manual(f){return new Promise(resolve=>f.callbacks.message({action:'check',session_id:SID},{url:'chrome-extension://fixture/popup.html'},resolve));}
 {const f=fixture();f.state.remoteStatus=403;let reply=await manual(f);assert.match(reply.status,/HTTP 403/);const first=f.paper.active_attempt.id;f.state.remoteStatus=200;reply=await manual(f);assert.match(reply.status,/已自动保存PDF/);assert.notEqual(f.paper.active_attempt.id,first);assert.equal(f.calls.filter(x=>x.remote).length,2);checks++;}
 {const f=fixture();f.paper.publisher_binding={source:'Crossref',doi:DOI,publisher_pii:PII,publisher_article_url:ARTICLE};f.storage.managed[9]={session_id:SID,index:0,doi:DOI,expected_pii:PII,identity_verified:true,auto_pdf_started:true,auto_pdf_attempted:true,attempt_id:'f'.repeat(32),attempted:'resolved:'+PII};await f.invoke('openNext',SID);assert(f.state.complete);assert.equal(f.calls.filter(x=>x.remote).length,1);assert.notEqual(f.paper.active_attempt.id,'f'.repeat(32));checks++;}
 {const f=fixture();f.state.remoteStatus=403;await manual(f);await f.invoke('handleTabReady',10);assert.equal(f.calls.filter(x=>x.remote).length,1);assert(f.calls.some(x=>x.endpoint==='extension-diagnostic'&&x.data.result==='WAIT_DUPLICATE'));checks++;}
 {const f=fixture();f.state.tabUrl=PDF+'&X-Amz-Date=20000101T000000Z&X-Amz-Expires=300';let reply=await manual(f);assert.match(reply.status,/已过期/);assert(f.calls.some(x=>x.navigate===ARTICLE));assert.equal(f.calls.filter(x=>x.remote).length,0);assert.equal(f.paper.active_attempt.link_refreshes,1);reply=await f.invoke('checkTab',9,true);assert.match(reply.status,/更新次数已用完/);assert.equal(f.paper.active_attempt.link_refreshes,1);assert.equal(f.calls.filter(x=>x.remote).length,0);checks++;}
 {const f=fixture();f.state.remoteStatus=403;f.state.tabUrl=PDF+'&X-Amz-Date=20990101T000000Z&X-Amz-Expires=300';const reply=await manual(f);assert.match(reply.status,/HTTP 403/);assert.equal(f.calls.filter(x=>x.data?.action==='refresh-link').length,0);const trace=f.calls.find(x=>x.data?.result==='TRANSFER_FAILED').data;assert.equal(trace.http_status,403);assert.equal(trace.reason,'HTTP_ERROR');assert(!JSON.stringify(trace).includes('fixture-private'));checks++;}
 {const f=fixture();f.state.networkError=true;const reply=await manual(f);assert.match(reply.status,/网络请求失败/);const trace=f.calls.find(x=>x.data?.result==='TRANSFER_FAILED').data;assert.equal(trace.reason,'NETWORK');assert.equal(trace.phase,'FETCH');assert(!JSON.stringify(trace).includes('private URL'));checks++;}
 {const f=fixture();f.state.mime='text/html';f.state.body='<html>Sign in</html>';const reply=await manual(f);assert.match(reply.status,/网页或其他格式/);const trace=f.calls.find(x=>x.data?.result==='TRANSFER_FAILED').data;assert.equal(trace.http_status,200);assert.equal(trace.mime_kind,'HTML');assert.equal(trace.reason,'MIME_NOT_PDF');assert(!f.state.complete);checks++;}
 {const f=fixture();f.state.busy=true;const reply=await manual(f);assert.match(reply.status,/正在下载/);assert.equal(f.calls.filter(x=>x.remote).length,0);checks++;}
 {const f=fixture();assert.equal(f.invoke('signedLinkState',PDF+'&X-Amz-Date=20261017T000000Z&X-Amz-Expires=300',Date.UTC(2026,9,17,0,5)), 'EXPIRED');assert.equal(f.invoke('signedLinkState',PDF+'&X-Amz-Date=20261017T000000Z&X-Amz-Expires=300',Date.UTC(2026,9,17,0,4)), 'LIVE');assert.equal(f.invoke('signedLinkState',PDF+'&X-Amz-Date=bad&X-Amz-Expires=300'), 'UNKNOWN');checks++;}
 console.log(JSON.stringify({status:'PASS',checks,scope:'selected ScienceDirect identity recovery, auth return, new PDF tab; mocked Chrome/network'}));
})().catch(e=>{console.error(e);process.exitCode=1;});
