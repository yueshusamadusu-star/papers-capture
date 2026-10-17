"use strict";
const DIRECT_PDF_LIMIT=25*1024*1024;
function saveError(code,reason="PDF_INCOMPLETE"){const error=new Error(code);error.saveCode=code;error.pdfReason=reason;return error;}
function mimeKind(value){return /^application\/pdf(?:\s*;|$)/i.test(value||"")?"PDF":/^text\/html(?:\s*;|$)/i.test(value||"")?"HTML":/^application\/octet-stream(?:\s*;|$)/i.test(value||"")?"BINARY":value?"OTHER":"UNKNOWN";}
function signedLinkState(value,at=Date.now()){
 try{const u=new URL(value);if(!assetPii(value))return "UNKNOWN";
  const date=u.searchParams.get("X-Amz-Date")?.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/),ttl=Number(u.searchParams.get("X-Amz-Expires"));
  if(!date||!Number.isInteger(ttl)||ttl<=0||ttl>604800)return "UNKNOWN";
  const start=Date.UTC(+date[1],+date[2]-1,+date[3],+date[4],+date[5],+date[6]);return at>=start+ttl*1000?"EXPIRED":"LIVE";
 }catch{return "UNKNOWN";}
}
async function recordTransfer(job,result,detail={}){
 try{await api("/extension-diagnostic",{extension_version:chrome.runtime.getManifest().version,chosen_session:job.session_id,
  expected_pii:job.expected_pii||articlePii(job.article_page),result,...detail});}catch{}
}
async function refreshExpiredFile(tabId,job){
 if(!job.attempt_id)return null;
 const result=await api("/download-attempt",{session_id:job.session_id,index:job.index,attempt_id:job.attempt_id,action:"refresh-link"});
 if(result.status!=="READY"||!sdArticle(result.article_url)||articlePii(result.article_url)!==job.expected_pii)return null;
 const {managed={},pdfAttempts={}}=await chrome.storage.local.get(["managed","pdfAttempts"]);
 for(const id of Object.keys(managed))if(transferKey(managed[id])===transferKey(job))managed[id]={...managed[id],auto_pdf_started:false,auto_pdf_attempted:false,attempted:"",control_clicked:false};
 managed[tabId]={...job,auto_pdf_started:false,auto_pdf_attempted:false,attempted:"",control_clicked:false};
 delete pdfAttempts[job.attempt_id];await chrome.storage.local.set({managed,pdfAttempts});
 await recordTransfer(job,"LINK_REFRESH",{phase:"RENEW",link_state:"EXPIRED",reason:"SIGNED_URL_EXPIRED"});
 await chrome.tabs.update(tabId,{url:result.article_url});
 return {status:"旧PDF临时链接已过期，已返回同篇官网更新一次，正在接续"};
}
async function pdfResponseBytes(response,detail={}){
 if(response.status!==200)throw saveError("FETCH_PDF","HTTP_ERROR");
 // 缺少格式头时仍检查有界完整内容；明确声明HTML等格式时保持拒绝。
 const kind=mimeKind(response.headers.get("content-type"));if(!["PDF","BINARY","UNKNOWN"].includes(kind))throw saveError("FETCH_PDF","MIME_NOT_PDF");
 const advertised=Number(response.headers.get("content-length"));if(advertised>DIRECT_PDF_LIMIT)throw saveError("FETCH_PDF","SIZE_LIMIT");
 let bytes;
 if(response.body?.getReader){
  const reader=response.body.getReader(),parts=[];let total=0;
  try{while(true){const {done,value}=await reader.read();if(done)break;total+=value.byteLength;if(total>DIRECT_PDF_LIMIT){await reader.cancel();throw saveError("FETCH_PDF","SIZE_LIMIT");}parts.push(value);}}finally{reader.releaseLock();}
  bytes=new Uint8Array(total);let offset=0;for(const part of parts){bytes.set(part,offset);offset+=part.byteLength;}
 }else bytes=new Uint8Array(await response.arrayBuffer());
 if(bytes.byteLength>DIRECT_PDF_LIMIT)throw saveError("FETCH_PDF","SIZE_LIMIT");
 detail.body_bytes=bytes.byteLength;
 const prefix=new TextDecoder().decode(bytes.slice(0,256));
 detail.body_kind=!bytes.byteLength?"EMPTY":prefix.startsWith("%PDF-")?"PDF":/^\s*(?:<!doctype\s+html\b|<html\b|<head\b|<body\b)/i.test(prefix)?"HTML":"OTHER";
 if(detail.body_kind==="EMPTY")throw saveError("FETCH_PDF","EMPTY_RESPONSE");
 if(detail.body_kind==="HTML")throw saveError("FETCH_PDF","HTML_RESPONSE");
 if(detail.body_kind!=="PDF")throw saveError("FETCH_PDF","NOT_PDF_CONTENT");
 if(bytes.byteLength<12||!new TextDecoder().decode(bytes.slice(-2048)).includes("%%EOF"))throw saveError("FETCH_PDF","PDF_INCOMPLETE");
 return bytes;
}
async function savePdfDirect(tabId,job,url){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),25000);
 const detail={phase:"FETCH",link_state:signedLinkState(url)};
 try{
  if(!job.identity_verified||!fileResponseIdentity(job,url))throw saveError("FETCH_PDF","FINAL_IDENTITY");
  if(detail.link_state==="EXPIRED")throw saveError("FETCH_PDF","SIGNED_URL_EXPIRED");
  await recordTransfer(job,"TRANSFER_STARTED",detail);
  const response=await fetch(url,{credentials:"include",signal:controller.signal});
  detail.http_status=response.status;detail.mime_kind=mimeKind(response.headers.get("content-type"));
  await recordTransfer(job,"TRANSFER_HTTP",detail);
  if(response.status!==200)throw saveError("FETCH_PDF","HTTP_ERROR");
  if(!fileResponseIdentity(job,response.url))throw saveError("FETCH_PDF","FINAL_IDENTITY");
  detail.phase="BODY";const bytes=await pdfResponseBytes(response,detail);
  await recordTransfer(job,"TRANSFER_BODY",detail);
  const {token}=await chrome.storage.local.get("token");if(!token)throw saveError("SAVE_DIRECTORY","MISSING_PAIRING");
  detail.phase="LOCAL";
  const saved=await fetch(ORIGIN+"/pdf-bytes",{method:"POST",headers:{Authorization:"Bearer "+token,"Content-Type":"application/pdf",
   "X-Papers-Session":job.session_id,"X-Papers-Index":String(job.index),"X-Papers-Trigger":job.download_trigger,...(job.attempt_id?{"X-Papers-Attempt":job.attempt_id}:{})},body:bytes,signal:controller.signal});
  if(!saved.ok){detail.http_status=saved.status;throw saveError("SAVE_DIRECTORY","LOCAL_REJECTED");}
  const state=await saved.json(),paper=state.papers[job.index];if(!["SAVED","ALREADY_EXISTS"].includes(paper?.status))throw saveError("SAVE_DIRECTORY","LOCAL_REJECTED");
  await recordTransfer(job,"TRANSFER_SAVED",{phase:"DONE"});
  await chrome.storage.local.set({lastSuccess:{summary:"自动保存："+(paper.file?.saved_path||paper.title||job.doi)}});
  await stopAutomaticTransfer(job);await clearFailure();await openNext(job.session_id);
  return {status:"已自动保存PDF",saved_path:paper.file?.saved_path};
 }catch(error){
  await stopAutomaticTransfer(job);
  const reason=error.pdfReason||(error.name==="AbortError"?"TIMEOUT":"NETWORK");
  await recordTransfer(job,"TRANSFER_FAILED",{...detail,reason});
  if(reason==="SIGNED_URL_EXPIRED"){
   try{const renewed=await refreshExpiredFile(tabId,job);if(renewed)return renewed;}catch{}
  }
  const code=error.saveCode||(detail.phase==="LOCAL"?"SAVE_DIRECTORY":"FETCH_PDF");
  await reportFailure(code,job);
  const messages={HTTP_ERROR:"文件服务器返回HTTP "+(detail.http_status||"未知"),NETWORK:"浏览器网络请求失败",TIMEOUT:"获取文件超时",FINAL_IDENTITY:"最终文件身份不一致",MIME_NOT_PDF:"服务器返回了网页或其他格式",PDF_INCOMPLETE:"PDF文件内容不完整",EMPTY_RESPONSE:"服务器返回空内容",HTML_RESPONSE:"收到网页内容，尚未取得论文PDF",NOT_PDF_CONTENT:"收到的内容不是PDF",SIZE_LIMIT:"文件超过25MB",LOCAL_REJECTED:"本机保存接口拒绝文件",MISSING_PAIRING:"本机配对信息缺失",SIGNED_URL_EXPIRED:"临时链接已过期，本次自动更新次数已用完"};
  const summary=detail.phase==="LOCAL"&&reason==="NETWORK"?"本机保存接口连接失败":messages[reason]||"文件校验失败";
  await chrome.storage.local.set({lastFailure:{code,summary,when:new Date().toISOString()}});
  return {status:"自动保存未完成："+summary+"；未计入全文"};
 }finally{clearTimeout(timer);}
}
