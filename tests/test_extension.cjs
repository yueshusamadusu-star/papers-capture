"use strict";
const fs=require("node:fs"),vm=require("node:vm"),assert=require("node:assert/strict");
const path=require("node:path");
const storage={token:"fixture-token",managed:{7:{session_id:"a".repeat(32),index:0,doi:"10.1000/test",attempted:""}},downloads:{}};
const calls=[];
let snapshot={doi:"10.1000/test",pdf_links:["https://www.sciencedirect.com/a.pdf"],auth_links:[],institution_recognized:true,no_access:false,challenge:false,password_form:false};
const chrome={storage:{local:{get:async()=>structuredClone(storage),set:async d=>Object.assign(storage,structuredClone(d))}},action:{setBadgeText:()=>{}},
 tabs:{get:async()=>({url:"https://www.sciencedirect.com/article/test"}),update:async(id,options)=>{calls.push({navigate:options});return {id};},query:async()=>[{id:7}],create:async()=>({id:8}),onUpdated:{addListener:()=>{}}},
 downloads:{download:async options=>{calls.push({download:options});return 12;},search:async()=>[{state:"in_progress"}],onDeterminingFilename:{addListener:()=>{}},onChanged:{addListener:()=>{}}},
 scripting:{executeScript:async()=>[{result:structuredClone(snapshot)}]},runtime:{onMessage:{addListener:()=>{}}}};
const sandbox={chrome,URL,console,setTimeout:()=>{},fetch:async(url,opts)=>{calls.push({url,opts});return {ok:true,json:async()=>({tasks:[]})};}};
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
 console.log(JSON.stringify({status:"PASS",checks:["trusted_pdf_host","download_filename_scope","no_duplicate_download","pdf_precedes_login_widget","ieee_preview_navigation","sd_preparation_navigation","native_download_referrer_scope","wrong_doi_rejected","challenge_pauses","no_access_falls_back"],scope:"mock Chrome API; real extension installation/authentication still required"}));
})().catch(error=>{console.error(error);process.exitCode=1;});
