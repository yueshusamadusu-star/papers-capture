"use strict";
const fs=require("node:fs"),vm=require("node:vm"),assert=require("node:assert/strict");
const path=require("node:path");
const storage={activeSessionId:"a".repeat(32),token:"fixture-token",managed:{7:{session_id:"a".repeat(32),index:0,doi:"10.1000/test",attempted:""}},downloads:{}};
let nativeRequired=false;const calls=[];let tabUrl="https://www.sciencedirect.com/article/test",clicked=false,controlClicks=0;
let snapshot={doi:"10.1000/test",pdf_links:["https://www.sciencedirect.com/a.pdf"],auth_links:[],institution_recognized:true,no_access:false,challenge:false,password_form:false};
const chrome={storage:{local:{get:async()=>structuredClone(storage),set:async d=>Object.assign(storage,structuredClone(d)),remove:async k=>{delete storage[k];}}},action:{setBadgeText:async data=>calls.push({badge:data})},
 tabs:{get:async()=>({url:tabUrl}),update:async(id,options)=>{calls.push({navigate:options});return {id};},query:async()=>[{id:7}],create:async()=>({id:8}),onUpdated:{addListener:()=>{}}},
 downloads:{download:async options=>{calls.push({download:options});return 12;},search:async()=>[{state:"in_progress"}],onDeterminingFilename:{addListener:()=>{}},onChanged:{addListener:()=>{}}},
 scripting:{executeScript:async options=>options.func?[{result:options.func(...options.args)}]:[{result:structuredClone(snapshot)}]},runtime:{getManifest:()=>({version:"0.4.2"}),onMessage:{addListener:()=>{}}}};
const sandbox={chrome,URL,console,document:{querySelector:()=>({content:snapshot.doi}),querySelectorAll:()=>clicked?[{innerText:"View PDF",getClientRects:()=>[{}],getAttribute:()=>"",click:()=>{controlClicks++;}}]:[]},getComputedStyle:()=>({visibility:"visible"}),setTimeout:()=>{},fetch:async(url,opts)=>{calls.push({url,opts});return {ok:true,json:async()=>({tasks:[{session_id:"a".repeat(32),papers:[{native_save_required:nativeRequired}]}]})};}};
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
 tabUrl=final;await vm.runInContext('checkTab(7)',sandbox);assert.equal(calls.filter(c=>c.download).length,3);
 assert.equal(JSON.stringify(storage).includes("fixture-private-signature"),false);
 nativeRequired=true;await vm.runInContext('checkTab(7,true)',sandbox);assert.equal(calls.filter(c=>c.download).length,3);
 assert(calls.some(c=>c.opts?.body&&JSON.parse(c.opts.body).status==="NEED_BROWSER_SAVE"));
 const browserSave=await vm.runInContext('nativeDownloadJob({url:"https://pdf.sciencedirectassets.com/a/1-s2.0-S0263224124013708/main.pdf",referrer:"",filename:"main.pdf",mime:"application/pdf"})',sandbox);
 assert.equal(browserSave.doi,"10.1000/test");
 const cached=await vm.runInContext('nativeDownloadJob({url:"blob:https://pdf.sciencedirectassets.com/fixture-id",referrer:"",filename:"main.pdf",mime:"application/pdf"})',sandbox);assert.equal(cached.doi,"10.1000/test");
 const originalUrl=tabUrl;tabUrl=tabUrl.replaceAll('S0263224124013708','S0263224124013709');
 assert.equal(await vm.runInContext('nativeDownloadJob({url:"blob:https://pdf.sciencedirectassets.com/fixture-id",referrer:"",filename:"main.pdf",mime:"application/pdf"})',sandbox),undefined);tabUrl=originalUrl;
 assert.equal(await vm.runInContext('nativeDownloadJob({url:"https://pdf.sciencedirectassets.com/a/1-s2.0-S0263224124013709/main.pdf",referrer:"",filename:"main.pdf"})',sandbox),undefined);
 nativeRequired=false;
 await vm.runInContext('checkTab(7)',sandbox);assert.equal(calls.filter(c=>c.download).length,3);
 tabUrl=final.replaceAll('S0263224124013708','S0263224124013709');await vm.runInContext('checkTab(7,true)',sandbox);assert.equal(calls.filter(c=>c.download).length,3);
 assert.equal(vm.runInContext('assetPii("https://pdf.sciencedirectassets.com.evil.example/a/1-s2.0-S0263224124013708/main.pdf")',sandbox),"");
 await vm.runInContext('reportFailure("NOT_PDF")',sandbox);assert.equal(storage.lastFailure.code,"NOT_PDF");assert.equal(calls.at(-1).badge.text,"!");
 await vm.runInContext('clearFailure()',sandbox);assert.equal(storage.lastFailure,undefined);assert.equal(calls.at(-1).badge.text,"");
 console.log(JSON.stringify({status:"PASS",checks:["trusted_pdf_host","download_filename_scope","no_duplicate_download","pdf_precedes_login_widget","ieee_preview_navigation","sd_preparation_navigation","native_download_referrer_scope","wrong_doi_rejected","challenge_pauses","no_access_falls_back","click_official_pdf_control","resolved_cdn_identity","signed_url_not_persisted","resolved_cdn_deduplication","readable_failure_and_clear","security_response_stops_direct_retry","native_viewer_save_scope","cached_pdf_active_identity"],scope:"mock Chrome API; real extension installation/authentication still required"}));
})().catch(error=>{console.error(error);process.exitCode=1;});
