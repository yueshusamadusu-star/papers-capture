"use strict";
const fs=require("node:fs"),vm=require("node:vm"),assert=require("node:assert/strict");
const path=require("node:path");
const storage={activeSessionId:"a".repeat(32),token:"fixture-token",managed:{7:{session_id:"a".repeat(32),index:0,doi:"10.1000/test",attempted:""}},downloads:{}};
let nativeRequired=false,taskPaper={},networkRoute={policy_enabled:true,direct_rule_present:true,status:'DIRECT_RULE_CONFIGURED'};const calls=[];let tabUrl="https://www.sciencedirect.com/article/test",clicked=false,controlClicks=0;
let snapshot={doi:"10.1000/test",pdf_links:["https://www.sciencedirect.com/a.pdf"],auth_links:[],institution_recognized:true,no_access:false,challenge:false,password_form:false};
const chrome={storage:{local:{get:async()=>structuredClone(storage),set:async d=>Object.assign(storage,structuredClone(d)),remove:async k=>{delete storage[k];}}},action:{setBadgeText:async data=>calls.push({badge:data})},
 tabs:{get:async()=>({url:tabUrl}),update:async(id,options)=>{calls.push({navigate:options});return {id};},query:async()=>[{id:7}],create:async options=>{calls.push({created:options});return {id:8};},onUpdated:{addListener:()=>{}}},
 downloads:{download:async options=>{calls.push({download:options});return 12;},search:async()=>[{state:"in_progress"}],onDeterminingFilename:{addListener:()=>{}},onChanged:{addListener:()=>{}}},
 scripting:{executeScript:async options=>options.func?[{result:options.func(...options.args)}]:[{result:structuredClone(snapshot)}]},runtime:{getManifest:()=>({version:"0.4.5"}),onMessage:{addListener:()=>{}}}};
const sandbox={importScripts:(...files)=>files.forEach(file=>vm.runInContext(fs.readFileSync(path.join(__dirname,"../browser-extension",file),"utf8"),sandbox)),chrome,URL,AbortController,Uint8Array,TextDecoder,clearTimeout,console,document:{querySelector:()=>({content:snapshot.doi}),querySelectorAll:()=>clicked?[{innerText:"View PDF",getClientRects:()=>[{}],getAttribute:()=>"",click:()=>{controlClicks++;}}]:[]},getComputedStyle:()=>({visibility:"visible"}),setTimeout:()=>{},fetch:async(url,opts)=>{
 if(String(url).startsWith('https://')){calls.push({directFetch:String(url)});return {status:200,url:String(url),headers:{get:()=>"application/pdf"},arrayBuffer:async()=>new TextEncoder().encode('%PDF-1.4\nfixture\n%%EOF').buffer};}
 if(String(url).endsWith('/pdf-bytes')){calls.push({directSave:true});return {ok:true,json:async()=>({papers:[{status:'SAVED',title:'Fixture',file:{saved_path:'D:/论文/Fixture.pdf'}}]})};}
 calls.push({url,opts});return {ok:true,json:async()=>String(url).endsWith("/ieee-network")?networkRoute:({tasks:[{session_id:"a".repeat(32),papers:[{...taskPaper,native_save_required:nativeRequired}]}]})};}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path.join(__dirname,"../browser-extension/background.js"),"utf8"),sandbox);
(async()=>{
 assert.equal(vm.runInContext('allowed("https://www.sciencedirect.com/a.pdf")',sandbox),true);
 for(const u of ["http://www.sciencedirect.com/a.pdf","https://sciencedirect.com.evil.example/a.pdf","https://127.0.0.1/a.pdf","https://user:pass@www.sciencedirect.com/a.pdf"]){assert.equal(vm.runInContext(`allowed(${JSON.stringify(u)})`,sandbox),false);}
 await vm.runInContext('checkTab(7)',sandbox);
 assert.equal(calls.filter(c=>c.download).length,1);assert.equal(calls.find(c=>c.download).download.filename,'papers-capture/'+"a".repeat(32)+'/0.pdf');
 await vm.runInContext('checkTab(7)',sandbox);assert.equal(calls.filter(c=>c.download).length,1);
 snapshot={...snapshot,password_form:true};await vm.runInContext('checkTab(7,true)',sandbox);assert.equal(calls.filter(c=>c.download).length,2);
 snapshot={...snapshot,password_form:false,doi:"10.1000/test",pdf_links:["https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber=123"]};await vm.runInContext('checkTab(7,true)',sandbox);
 assert.equal(calls.filter(c=>c.navigate).length,1);assert.equal(calls.filter(c=>c.download).length,2);
 snapshot={...snapshot,pdf_links:["https://www.sciencedirect.com/science/article/pii/S123/pdfft?download=true"]};await vm.runInContext('checkTab(7,true)',sandbox);
 assert.equal(calls.filter(c=>c.navigate).length,2);assert.equal(calls.filter(c=>c.download).length,2);
 const native=await vm.runInContext('nativeDownloadJob({url:"https://www.sciencedirect.com/science/article/pii/S123/pdfft?download=true",referrer:"https://www.sciencedirect.com/article/test",filename:"paper.pdf"})',sandbox);
 assert.equal(native.doi,"10.1000/test");
 assert.equal(await vm.runInContext('nativeDownloadJob({url:"https://www.sciencedirect.com/other.pdf",referrer:"https://evil.example/",filename:"other.pdf"})',sandbox),undefined);
 snapshot={...snapshot,doi:"10.1000/wrong"};await vm.runInContext('checkTab(7,true)',sandbox);assert.equal(calls.filter(c=>c.download).length,2);
 snapshot={...snapshot,doi:"10.1000/test",challenge:true};await vm.runInContext('checkTab(7,true)',sandbox);assert.equal(calls.filter(c=>c.download).length,2);
 snapshot={...snapshot,challenge:false,pdf_links:[],no_access:true};await vm.runInContext('checkTab(7,true)',sandbox);
 assert(calls.some(c=>c.opts?.body&&JSON.parse(c.opts.body).status==="SKIPPED_NO_ACCESS"));
 tabUrl="https://www.sciencedirect.com/science/article/pii/S0263224124013708";clicked=true;
 snapshot={...snapshot,no_access:false,pdf_links:[tabUrl+"/pdfft?download=true"]};
 await vm.runInContext('checkTab(7,true)',sandbox);assert.equal(calls.filter(c=>c.navigate).length,2);assert.equal(calls.filter(c=>c.download).length,2);assert.equal(controlClicks,1);
 assert.equal(await vm.runInContext('clickArticlePdf(7,"10.1000/wrong")',sandbox),false);assert.equal(controlClicks,1);
 const final="https://pdf.sciencedirectassets.com/271454/issue/1-s2.0-S0263224124013708/main.pdf?X-Amz-Signature=fixture-private-signature&pii=S0263224124013708";
 tabUrl=final;await vm.runInContext('checkTab(7)',sandbox);assert.equal(calls.filter(c=>c.download).length,2);assert.equal(calls.filter(c=>c.directSave).length,1);
 assert.equal(JSON.stringify(storage).includes("fixture-private-signature"),false);
 nativeRequired=true;await vm.runInContext('checkTab(7,true)',sandbox);assert.equal(calls.filter(c=>c.download).length,2);
 assert(calls.some(c=>c.opts?.body&&JSON.parse(c.opts.body).status==="NEED_BROWSER_SAVE"));
 const browserSave=await vm.runInContext('nativeDownloadJob({url:"https://pdf.sciencedirectassets.com/a/1-s2.0-S0263224124013708/main.pdf",referrer:"",filename:"main.pdf",mime:"application/pdf"})',sandbox);
 assert.equal(browserSave.doi,"10.1000/test");
 const cached=await vm.runInContext('nativeDownloadJob({url:"blob:https://pdf.sciencedirectassets.com/fixture-id",referrer:"",filename:"main.pdf",mime:"application/pdf"})',sandbox);assert.equal(cached.doi,"10.1000/test");
 const originalUrl=tabUrl;tabUrl=tabUrl.replaceAll('S0263224124013708','S0263224124013709');
 assert.equal(await vm.runInContext('nativeDownloadJob({url:"blob:https://pdf.sciencedirectassets.com/fixture-id",referrer:"",filename:"main.pdf",mime:"application/pdf"})',sandbox),undefined);tabUrl=originalUrl;
 assert.equal(await vm.runInContext('nativeDownloadJob({url:"https://pdf.sciencedirectassets.com/a/1-s2.0-S0263224124013709/main.pdf",referrer:"",filename:"main.pdf"})',sandbox),undefined);
 nativeRequired=false;
 await vm.runInContext('checkTab(7)',sandbox);assert.equal(calls.filter(c=>c.download).length,2);
 tabUrl=final.replaceAll('S0263224124013708','S0263224124013709');await vm.runInContext('checkTab(7,true)',sandbox);assert.equal(calls.filter(c=>c.download).length,2);
 assert.equal(vm.runInContext('assetPii("https://pdf.sciencedirectassets.com.evil.example/a/1-s2.0-S0263224124013708/main.pdf")',sandbox),"");
 await vm.runInContext('reportFailure("NOT_PDF")',sandbox);assert.equal(storage.lastFailure.code,"NOT_PDF");assert.equal(calls.at(-1).badge.text,"!");
 await vm.runInContext('clearFailure()',sandbox);assert.equal(storage.lastFailure,undefined);assert.equal(calls.at(-1).badge.text,"");
 const ieeeDoi="10.1109/access.2022.3181725",ieeePage="https://ieeexplore.ieee.org/document/9792260";
 assert.equal(vm.runInContext('doi("DOI: 10.1109/ACCESS.2022.3181725")',sandbox),ieeeDoi);
 assert.equal(vm.runInContext('ieeeArticleId("https://ieeexplore.ieee.org/document/9792260/")',sandbox),"9792260");
 for(const u of ["http://ieeexplore.ieee.org/document/9792260","https://ieeexplore.ieee.org.evil.example/document/9792260","https://user:password@ieeexplore.ieee.org/document/9792260"]){
  assert.equal(vm.runInContext("ieeeArticleId("+JSON.stringify(u)+")",sandbox),"");
 }
 storage.managed[7]={session_id:"a".repeat(32),index:0,doi:ieeeDoi,attempted:""};
 taskPaper={doi:ieeeDoi,article_url:ieeePage,publisher_article_url:ieeePage};
 tabUrl=ieeePage;const previewsBefore=calls.filter(c=>c.navigate).length;
 snapshot={doi:"9792260",pdf_links:["https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber=9792260"],auth_links:[],institution_recognized:true,no_access:false,challenge:false,password_form:false};
 await vm.runInContext('checkTab(7,true)',sandbox);
 assert.equal(calls.filter(c=>c.navigate).length,previewsBefore+1);
 assert.equal(storage.managed[7].ieee_article_id,"9792260");
 assert(calls.some(c=>c.opts?.body&&JSON.parse(c.opts.body).identity_source==="IEEE_ARTICLE_URL"));
 tabUrl=ieeePage.replace("9792260","9792261");snapshot={...snapshot,doi:""};
 await vm.runInContext('checkTab(7,true)',sandbox);assert.equal(calls.filter(c=>c.navigate).length,previewsBefore+1);
 tabUrl=ieeePage;snapshot={...snapshot,doi:"10.1109/access.wrong"};
 await vm.runInContext('checkTab(7,true)',sandbox);assert.equal(calls.filter(c=>c.navigate).length,previewsBefore+1);
 snapshot={...snapshot,doi:"",pdf_links:["https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber=9792261"]};
 await vm.runInContext('checkTab(7,true)',sandbox);assert.equal(calls.filter(c=>c.navigate).length,previewsBefore+1);
 const ieeeNative=await vm.runInContext('nativeDownloadJob({url:"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?arnumber=9792260",referrer:"",filename:"paper.pdf",mime:"application/pdf"})',sandbox);
 assert.equal(ieeeNative.doi,ieeeDoi);
 assert.equal(await vm.runInContext('nativeDownloadJob({url:"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?arnumber=9792261",referrer:"https://ieeexplore.ieee.org/document/9792260",filename:"wrong.pdf",mime:"application/pdf"})',sandbox),undefined);

 tabUrl=ieeePage;snapshot={...snapshot,ieee_network_error:true,challenge:true,no_access:true};
 const downloadCount=calls.filter(c=>c.download).length,navigationCount=calls.filter(c=>c.navigate).length;
 await vm.runInContext('checkTab(7,true)',sandbox);
 assert.equal(calls.filter(c=>c.download).length,downloadCount);
 assert.equal(calls.filter(c=>c.navigate).length,navigationCount);
 assert(calls.some(c=>c.opts?.body&&JSON.parse(c.opts.body).status==="NEED_IEEE_NETWORK_ROUTE"&&JSON.parse(c.opts.body).failure_code==="IEEE_HTTP_418"));
 tabUrl="https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber=9792260";
 storage.managed[7].viewer_url=tabUrl;
 snapshot={doi:"",pdf_links:[],viewer_pdf_links:[],auth_links:[],institution_recognized:false,no_access:false,password_form:false,challenge:false,ieee_network_error:false};
 await vm.runInContext('checkTab(7,true)',sandbox);
 assert.equal(storage.managed[7].native_until>Date.now()+500000,true);
 assert(calls.some(c=>c.opts?.body&&JSON.parse(c.opts.body).status==="NEED_BROWSER_SAVE"&&JSON.parse(c.opts.body).identity_source==="VERIFIED_PDF_VIEWER"));

 networkRoute={policy_enabled:true,direct_rule_present:false,status:"NEED_IEEE_DIRECT_RULE"};
 const openedBefore=calls.filter(c=>c.created).length;
 const routePaused=await vm.runInContext('openNext("a".repeat(32))',sandbox);
 assert.match(routePaused.status,/IEEE直连规则/);assert.equal(calls.filter(c=>c.created).length,openedBefore);
 networkRoute={policy_enabled:true,direct_rule_present:true,status:"DIRECT_RULE_CONFIGURED"};
 await vm.runInContext('openNext("a".repeat(32))',sandbox);
 assert.equal(calls.filter(c=>c.created).length,openedBefore+1);assert.equal(calls.filter(c=>c.created).at(-1).created.url,ieeePage);

 console.log(JSON.stringify({status:"PASS",checks:["trusted_pdf_host","download_filename_scope","no_duplicate_download","pdf_precedes_login_widget","ieee_preview_navigation","sd_preparation_navigation","native_download_referrer_scope","wrong_doi_rejected","challenge_pauses","no_access_falls_back","click_official_pdf_control","resolved_cdn_identity","signed_url_not_persisted","resolved_cdn_deduplication","readable_failure_and_clear","security_response_stops_direct_retry","native_viewer_save_scope","cached_pdf_active_identity","ieee_canonical_article_binding","ieee_wrong_record_rejected","ieee_conflicting_doi_rejected","ieee_wrong_pdf_rejected","ieee_native_download_article_scope","ieee_418_pauses_as_network","ieee_viewer_native_save_prompt","ieee_missing_direct_rule_pauses_open","ieee_ready_direct_rule_continues"],scope:"mock Chrome API; real extension installation/authentication still required"}));
})().catch(error=>{console.error(error);process.exitCode=1;});
