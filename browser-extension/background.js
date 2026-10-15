"use strict";
const ORIGIN="http://127.0.0.1:8766";
const domains=["sciencedirect.com","elsevier.com","ieee.org","scitepress.org","mdpi.com","mdpi-res.com","arxiv.org","ncbi.nlm.nih.gov","springer.com","springerlink.com","nature.com","wiley.com","tandfonline.com","acm.org","cambridge.org","oup.com","sagepub.com","iop.org","aps.org","aip.org"];
const allowed=value=>{try{const u=new URL(value);return u.protocol==="https:"&&!u.username&&!u.password&&domains.some(d=>u.hostname===d||u.hostname.endsWith("."+d));}catch{return false;}};
const samePage=(a,b)=>{try{const x=new URL(a),y=new URL(b);return x.origin===y.origin&&x.pathname===y.pathname;}catch{return false;}};
const doi=value=>String(value||"").trim().replace(/^https?:\/\/(?:dx\.)?doi\.org\//i,"").toLowerCase();
const checking=new Set(),completing=new Set(),opening=new Set();
async function api(path,data){
 const {token}=await chrome.storage.local.get("token");if(!token)throw Error("请先刷新本机配对页");
 const response=await fetch(ORIGIN+path,{method:data?"POST":"GET",headers:{Authorization:"Bearer "+token,...(data?{"Content-Type":"application/json"}:{})},...(data?{body:JSON.stringify(data)}:{})});
 if(!response.ok)throw Error("本机接续未完成，请查看任务状态或下载目录设置");return response.json();
}
async function progress(job,status,identity=false,s={}){return api("/observe",{session_id:job.session_id,index:job.index,status,identity_matched:identity,
 institution_recognized:Boolean(s.institution_recognized),visible_auth_form:Boolean(s.password_form),pdf_candidates:s.pdf_links?.length||0});}
async function openNext(sessionId){
 if(opening.has(sessionId))return {status:"OPENING"};opening.add(sessionId);
 try{
  const {tasks}=await api("/tasks"),task=tasks.find(t=>t.session_id===sessionId);if(!task)return {status:"FINISHED"};
  const terminal=["SAVED","ALREADY_EXISTS","SKIPPED_NO_ACCESS","SKIPPED_BY_USER","ERROR","UNSUPPORTED_PUBLISHER"];
  const index=task.papers.findIndex(p=>!terminal.includes(p.status));if(index<0)return {status:"FINISHED"};
  const paper=task.papers[index];await chrome.storage.local.set({activeSessionId:sessionId});
  const tab=await chrome.tabs.create({url:paper.article_url});const {managed={}}=await chrome.storage.local.get("managed");
  managed[tab.id]={session_id:sessionId,index,doi:paper.doi,attempted:""};await chrome.storage.local.set({managed});
  if((await chrome.tabs.get(tab.id)).status==="complete")await checkTab(tab.id);
  return {status:"OPENED",title:paper.title};
 }finally{opening.delete(sessionId);}
}
async function inspect(tabId){const results=await chrome.scripting.executeScript({target:{tabId},files:["inspect.js"]});return results[0]?.result;}
async function adoptCurrent(tab){
 if(!allowed(tab.url))throw Error("请先完成机构认证并返回论文页面");
 const {managed={},activeSessionId}=await chrome.storage.local.get(["managed","activeSessionId"]);
 if(managed[tab.id])return;
 if(!activeSessionId)throw Error("请先在扩展选择并开始一个文献任务");
 const {tasks}=await api("/tasks"),task=tasks.find(t=>t.session_id===activeSessionId);if(!task)throw Error("当前任务已结束，请先选择任务");
 const s=await inspect(tab.id);const index=task.papers.findIndex(p=>doi(p.doi)===doi(s?.doi));
 if(index<0)throw Error("当前页面身份未匹配本任务；请返回原论文页");
 managed[tab.id]={session_id:activeSessionId,index,doi:task.papers[index].doi,attempted:""};await chrome.storage.local.set({managed});
}
async function checkTab(tabId,force=false){
 if(checking.has(tabId))return {status:"CHECKING"};checking.add(tabId);
 try{
  const {managed={}}=await chrome.storage.local.get("managed"),job=managed[tabId];if(!job)return {status:"NOT_TRACKED"};
  const tab=await chrome.tabs.get(tabId);if(!allowed(tab.url))return {status:"请本人完成认证后返回论文页"};
  const s=await inspect(tabId);if(!s)return {status:"ACCESS_UNKNOWN"};
  if(s.challenge){await progress(job,"CHALLENGE_REQUIRED",false,s);return {status:"请本人完成网站验证"};}
  const matched=doi(s.doi)===doi(job.doi),viewer=Boolean(job.identity_verified&&job.viewer_url===tab.url);
  if(!matched&&!viewer){await progress(job,s.password_form?"NEED_USER_AUTHENTICATION":"ACCESS_UNKNOWN",false,s);return {status:"请返回本篇论文页后再次检查"};}
  // 已匹配论文的PDF候选优先于旁边的个人登录组件；隐藏表单不算认证页面。
  const pdf=(matched?s.pdf_links:(s.viewer_pdf_links||[])).find(allowed);
  if(pdf){
   const signature=pdf+"|"+Boolean(s.institution_recognized);if(!force&&job.attempted===signature)return {status:"等待下载或本人授权"};
   job.attempted=signature;job.identity_verified=true;job.article_page=tab.url;
   if(!viewer&&/\/stamp\/stamp\.jsp(?:\?|$)|\/epdf(?:\/|\?|$)|\/pdfft(?:\?|$)/i.test(pdf)){
    job.viewer_url=pdf;job.native_until=Date.now()+180000;managed[tabId]=job;await chrome.storage.local.set({managed});await progress(job,"ACCESS_UNKNOWN",true,s);
    await chrome.tabs.update(tabId,{url:pdf});setTimeout(()=>checkTab(tabId).catch(()=>{}),3000);return {status:"正在打开本篇PDF预览/下载准备页"};
   }
   managed[tabId]=job;await chrome.storage.local.set({managed});await progress(job,"DOWNLOADING",true,s);
   const id=await chrome.downloads.download({url:pdf,filename:`papers-capture/${job.session_id}/${job.index}.pdf`,conflictAction:"uniquify",saveAs:false});
   const {downloads={}}=await chrome.storage.local.get("downloads");downloads[id]=job;await chrome.storage.local.set({downloads});
   const items=await chrome.downloads.search({id});if(items[0]?.state==="complete")await completedDownload(id);
   return {status:"正在下载并校验PDF"};
  }
  if(s.institution_recognized&&s.no_access){await progress(job,"SKIPPED_NO_ACCESS",true,s);await openNext(job.session_id);return {status:"本篇无权限，已退避"};}
  const status=s.password_form||s.auth_links.length||s.no_access?"NEED_USER_AUTHENTICATION":"ACCESS_UNKNOWN";
  await progress(job,status,true,s);return {status:status==="NEED_USER_AUTHENTICATION"?"请在官网完成机构认证后返回本篇":"权限暂不确定，请查看官网提示"};
 }finally{checking.delete(tabId);}
}
async function completedDownload(id){
 if(completing.has(id))return;completing.add(id);
 try{
  const {downloads={}}=await chrome.storage.local.get("downloads"),job=downloads[id];if(!job)return;
  const items=await chrome.downloads.search({id}),item=items[0];if(!item)return;
  if(item.state==="interrupted"){await progress(job,"DOWNLOAD_ERROR",true);delete downloads[id];await chrome.storage.local.set({downloads});return;}
  if(item.state!=="complete")return;
  const state=await api("/complete",{session_id:job.session_id,index:job.index,download_path:item.filename});delete downloads[id];await chrome.storage.local.set({downloads});
  if(["SAVED","ALREADY_EXISTS"].includes(state.papers[job.index].status))await openNext(job.session_id);
 }finally{completing.delete(id);}
}
async function reconcileDownloads(){
 const {downloads={}}=await chrome.storage.local.get("downloads");
 for(const key of Object.keys(downloads))await completedDownload(Number(key));
}
async function nativeDownloadJob(item){
 const {managed={}}=await chrome.storage.local.get("managed");
 return Object.values(managed).find(job=>job.identity_verified&&job.native_until>Date.now()&&allowed(item.referrer)&&
  [job.viewer_url,job.article_page].some(u=>u&&samePage(item.referrer,u))&&
  (samePage(item.url,job.viewer_url)||/\.pdf(?:[?#]|$)/i.test(item.url)||/\.pdf$/i.test(item.filename||"")));
}
chrome.downloads.onDeterminingFilename.addListener((item,suggest)=>{
 (async()=>{
  const job=await nativeDownloadJob(item);if(!job){suggest();return;}
  const {downloads={}}=await chrome.storage.local.get("downloads");downloads[item.id]=job;await chrome.storage.local.set({downloads});
  await progress(job,"DOWNLOADING",true);suggest({filename:`papers-capture/${job.session_id}/${job.index}.pdf`,conflictAction:"uniquify"});
 })().catch(()=>suggest());return true;
});
chrome.downloads.onChanged.addListener(delta=>{if(delta.state)completedDownload(delta.id).catch(()=>chrome.action.setBadgeText({text:"!"}));});
chrome.tabs.onUpdated.addListener((id,change)=>{if(change.status==="complete")checkTab(id).catch(()=>chrome.action.setBadgeText({text:"!"}));});
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
 (async()=>{
  if(message.action==="pair"){
   if(!sender.url?.startsWith(ORIGIN+"/pair")||!/^[-_a-zA-Z0-9]{40,60}$/.test(message.token||""))throw Error("配对来源无效");
   await chrome.storage.local.set({token:message.token});await api("/health");return {status:"PAIRED"};
  }
  if(message.action==="tasks")return api("/tasks");
  if(message.action==="start")return openNext(message.session_id);
  if(message.action==="auth"){await chrome.tabs.create({url:"https://ds.carsi.edu.cn/"});return {status:"请在CARSI选择浙江大学，并选择IEEE或Elsevier SD"};}
  if(message.action==="check"){
   await reconcileDownloads();
   const [tab]=await chrome.tabs.query({active:true,currentWindow:true});await adoptCurrent(tab);return checkTab(tab.id,true);
  }
  if(message.action==="skip"){
   const [tab]=await chrome.tabs.query({active:true,currentWindow:true});const {managed={}}=await chrome.storage.local.get("managed"),job=managed[tab.id];if(!job)throw Error("当前不是本任务打开的论文标签");
   await progress(job,"SKIPPED_BY_USER");return openNext(job.session_id);
  }
  throw Error("未知操作");
 })().then(reply).catch(error=>reply({error:error.message}));return true;
});
