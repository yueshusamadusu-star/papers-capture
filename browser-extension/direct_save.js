"use strict";
// 浏览器只向已配对的环回服务发送本篇PDF字节，不发送Cookie或临时文件URL。
const DIRECT_PDF_LIMIT=25*1024*1024;
function saveError(code){const error=new Error(code);error.saveCode=code;return error;}
async function pdfResponseBytes(response){
 if(response.status!==200)throw saveError("FETCH_PDF");
 const type=response.headers.get("content-type")||"";
 if(!/^application\/(?:pdf|octet-stream)(?:\s*;|$)/i.test(type))throw saveError("FETCH_PDF");
 const advertised=Number(response.headers.get("content-length"));
 if(advertised>DIRECT_PDF_LIMIT)throw saveError("FETCH_PDF");
 let bytes;
 if(response.body?.getReader){
  const reader=response.body.getReader(),parts=[];let total=0;
  try{
   while(true){const {done,value}=await reader.read();if(done)break;total+=value.byteLength;
    if(total>DIRECT_PDF_LIMIT){await reader.cancel();throw saveError("FETCH_PDF");}parts.push(value);}
  }finally{reader.releaseLock();}
  bytes=new Uint8Array(total);let offset=0;for(const part of parts){bytes.set(part,offset);offset+=part.byteLength;}
 }else bytes=new Uint8Array(await response.arrayBuffer());
 if(bytes.byteLength>DIRECT_PDF_LIMIT||bytes.byteLength<12||new TextDecoder().decode(bytes.slice(0,5))!=="%PDF-"||!new TextDecoder().decode(bytes.slice(-2048)).includes("%%EOF"))throw saveError("FETCH_PDF");
 return bytes;
}
async function savePdfDirect(tabId,job,url){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),25000);
 try{
  if(!job.identity_verified||!fileResponseIdentity(job,url))throw saveError("FETCH_PDF");
  // 使用浏览器现有会话；不设置Cookie/Authorization请求头，不向Python转交登录材料。
  const response=await fetch(url,{credentials:"include",signal:controller.signal});
  if(!fileResponseIdentity(job,response.url))throw saveError("FETCH_PDF");
  const bytes=await pdfResponseBytes(response);
  const {token}=await chrome.storage.local.get("token");if(!token)throw saveError("SAVE_DIRECTORY");
  const saved=await fetch(ORIGIN+"/pdf-bytes",{method:"POST",headers:{Authorization:"Bearer "+token,"Content-Type":"application/pdf",
   "X-Papers-Session":job.session_id,"X-Papers-Index":String(job.index),"X-Papers-Trigger":job.download_trigger},body:bytes,signal:controller.signal});
  if(!saved.ok)throw saveError("SAVE_DIRECTORY");
  const state=await saved.json(),paper=state.papers[job.index];
  if(!["SAVED","ALREADY_EXISTS"].includes(paper?.status))throw saveError("SAVE_DIRECTORY");
  await chrome.storage.local.set({lastSuccess:{summary:"自动保存："+(paper.file?.saved_path||paper.title||job.doi)}});
  await stopAutomaticTransfer(job);await clearFailure();await openNext(job.session_id);
  return {status:"已自动保存PDF",saved_path:paper.file?.saved_path};
 }catch(error){
  await stopAutomaticTransfer(job);await reportFailure(error.saveCode||"FETCH_PDF",job);
  return {status:"自动保存未完成，请查看插件提示；未弹另存为或计入全文"};
 }finally{clearTimeout(timer);}
}
