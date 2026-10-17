"use strict";
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const EXT=path.join(__dirname,'../browser-extension'),SID='b'.repeat(32),DOI='10.1016/j.measurement.2019.07.014',PII='S0263224119306359';
const ARTICLE='https://www.sciencedirect.com/science/article/pii/'+PII,PDF='https://pdf.sciencedirectassets.com/a/1-s2.0-'+PII+'/main.pdf?X-Amz-Signature=fixture-private';
function fixture(){
 const storage={token:'fixture',activeSessionId:SID,managed:{},downloads:{}},calls=[],callbacks={};
 const state={complete:false,binding:true,clicked:true,tabUrl:PDF,metadataDoi:DOI,snapshot:{doi:DOI,pdf_links:[],auth_links:[],pdf_controls:1,institution_recognized:false,password_form:false,no_access:false}};
 const paper={doi:DOI,status:'ACCESS_UNKNOWN',article_url:'https://doi.org/'+DOI};
 const chrome={storage:{local:{get:async()=>structuredClone(storage),set:async x=>Object.assign(storage,structuredClone(x)),remove:async k=>delete storage[k]}},
  runtime:{id:'fixture',getManifest:()=>({version:'0.5.3'}),onMessage:{addListener:f=>callbacks.message=f}},action:{setBadgeText:async()=>{}},
  tabs:{get:async id=>({id,url:state.tabUrl,status:'complete'}),onUpdated:{addListener:f=>callbacks.updated=f},onActivated:{addListener:f=>callbacks.activated=f},query:async()=>[{id:9}],create:async()=>{calls.push('create');return {id:10};}},
  scripting:{executeScript:async o=>{calls.push({script:o.files?.[0]});return [{result:o.func?{clicked:state.clicked}:structuredClone(state.snapshot)}];}},
  downloads:{search:async()=>[],onDeterminingFilename:{addListener:()=>{}},onChanged:{addListener:()=>{}}},
  webRequest:{onHeadersReceived:{addListener:()=>{}}}};
 const sandbox={chrome,URL,setTimeout:()=>{},clearTimeout,AbortController,Uint8Array,TextDecoder,console,fetch:async(url,options)=>{
  if(String(url).startsWith('https://')){calls.push({remote:String(url)});const r=new Response('%PDF-1.4\nfixture\n%%EOF',{headers:{'Content-Type':'application/pdf'}});Object.defineProperty(r,'url',{value:String(url)});return r;}
  const endpoint=String(url).split('/').pop(),data=options?.body&&endpoint!=='pdf-bytes'?JSON.parse(options.body):null;calls.push({endpoint,data});
  if(endpoint==='pdf-bytes'){state.complete=true;return {ok:true,json:async()=>({papers:[{status:'SAVED',title:'Fixture',file:{saved_path:'D:/论文/Fixture.pdf'}}]})};}
  return {ok:true,json:async()=>endpoint==='paper-binding'?(state.binding?{status:'BOUND',doi:state.metadataDoi,source:'Crossref',publisher_pii:PII,publisher_article_url:ARTICLE}:{status:'UNKNOWN'}):{tasks:state.complete?[]:[{session_id:SID,current_index:0,papers:[paper]}]}};
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
 console.log(JSON.stringify({status:'PASS',checks,scope:'selected ScienceDirect identity recovery, auth return, new PDF tab; mocked Chrome/network'}));
})().catch(e=>{console.error(e);process.exitCode=1;});
