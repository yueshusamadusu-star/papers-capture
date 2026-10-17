"use strict";
// 仅处理本人已选任务中、身份已核对的IEEE/ScienceDirect文件响应。
const capturedPdfResponses=new Map(),autoPdfStarting=new Set();
const transferKey=job=>job.session_id+":"+job.index;
function fileResponseIdentity(job,url){
 if(job.ieee_article_id)return ieeeArticleId(url)===job.ieee_article_id;
 if(aipFileIdentity(job,url))return true;
 const expected=job.expected_pii||articlePii(job.article_page);
 return Boolean(expected&&assetPii(url)===expected);
}
async function autoPdfAllowed(job){
 const {tasks}=await api("/tasks"),paper=tasks.find(t=>t.session_id===job.session_id)?.papers[job.index];
 return Boolean(paper&&!['SAVED','ALREADY_EXISTS','SKIPPED_NO_ACCESS','SKIPPED_BY_USER'].includes(paper.status)&&paper.browser_evidence?.failure_code!=="DOWNLOAD_SECURITY");
}
async function beginObservedPdf(tabId,job,url,trigger){
 const key=transferKey(job);
 if(autoPdfStarting.has(key)||job.auto_pdf_started)return {status:"正在自动下载并校验PDF"};
 if(job.auto_pdf_attempted)return {status:"本次自动下载已尝试，保留结果而不循环请求"};
 if(!job.identity_verified||!fileResponseIdentity(job,url))return {status:"文件身份尚未匹配，未发起下载"};
 autoPdfStarting.add(key);
 try{
  if(!await autoPdfAllowed(job))return {status:"当前任务无需下载或需本人处理网站验证"};
  job.auto_pdf_started=true;job.auto_pdf_attempted=true;
  const {managed={}}=await chrome.storage.local.get("managed");managed[tabId]=job;await chrome.storage.local.set({managed});
  return await startDownload(tabId,job,url,{download_trigger:trigger});
 }catch(error){
  job.auto_pdf_started=false;
  const {managed={}}=await chrome.storage.local.get("managed");managed[tabId]=job;await chrome.storage.local.set({managed});
  await reportFailure(error.saveCode||"BROWSER_OPERATION",job);
  return {status:"自动下载未完成，请查看当前任务提示"};
 }finally{autoPdfStarting.delete(key);}
}
async function observePdfResponse(details){
 if(details.tabId<0||![200,206].includes(details.statusCode))return;
 const mime=details.responseHeaders?.find(h=>h.name.toLowerCase()==="content-type")?.value||"";
 if(!/^application\/pdf(?:\s*;|$)/i.test(mime))return;
 let {managed={}}=await chrome.storage.local.get("managed"),job=managed[details.tabId];
 if((!job?.identity_verified||!fileResponseIdentity(job,details.url))&&assetPii(details.url)){
  if(!await restoreScienceDirect({id:details.tabId,url:details.url}))return;
  ({managed={}}=await chrome.storage.local.get("managed"));job=managed[details.tabId];
 }
 if(!job?.identity_verified||!fileResponseIdentity(job,details.url))return;
 // 临时文件链接仅保存在服务工作者内存，不写任务、配置或日志。
 capturedPdfResponses.set(transferKey(job),{url:details.url,at:Date.now()});
 return beginObservedPdf(details.tabId,job,details.url,"PDF_RESPONSE");
}
async function retryKnownIeeeFile(tabId,job){
 if(!job.ieee_article_id||!/^[0-9]+$/.test(job.ieee_article_id)||!job.identity_verified)return null;
 const captured=capturedPdfResponses.get(transferKey(job));
 if(captured&&Date.now()-captured.at<240000)return beginObservedPdf(tabId,job,captured.url,"PDF_RESPONSE");
 // 只检索所选文章编号的浏览器下载记录，不导出通用浏览历史或原文件地址。
 const number=job.ieee_article_id;
 const regex="^https://ieeexplore\\.ieee\\.org/(?:iel(?:x)?7/[0-9]+/[0-9]+/0*"+number+"\\.pdf(?:[?#]|$)|stampPDF/getPDF\\.jsp\\?[^#]*arnumber="+number+"(?:&|$))";
 const items=await chrome.downloads.search({urlRegex:regex,orderBy:["-startTime"],limit:5});
 const source=items.find(item=>item.state==="complete"&&/^application\/pdf(?:\s*;|$)/i.test(item.mime||"")&&[item.url,item.finalUrl].some(url=>fileResponseIdentity(job,url)));
 const url=source&&[source.finalUrl,source.url].find(url=>fileResponseIdentity(job,url));
 return url?beginObservedPdf(tabId,job,url,"MATCHED_DOWNLOAD_URL"):null;
}
if(chrome.webRequest?.onHeadersReceived){
 chrome.webRequest.onHeadersReceived.addListener(details=>{observePdfResponse(details).catch(()=>reportFailure("BROWSER_OPERATION"));},
  {urls:["https://ieeexplore.ieee.org/*","https://pdf.sciencedirectassets.com/*","https://pubs.aip.org/*"]},["responseHeaders"]);
}

async function stopAutomaticTransfer(job){
 const {managed={}}=await chrome.storage.local.get("managed");
 for(const id of Object.keys(managed))if(transferKey(managed[id])===transferKey(job))managed[id]={...managed[id],auto_pdf_started:false};
 await chrome.storage.local.set({managed});
}
