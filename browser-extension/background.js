"use strict";
const ORIGIN="http://127.0.0.1:8766";
const domains=["sciencedirect.com","elsevier.com","ieee.org","scitepress.org","mdpi.com","mdpi-res.com","arxiv.org","ncbi.nlm.nih.gov","springer.com","springerlink.com","nature.com","wiley.com","tandfonline.com","acm.org","cambridge.org","oup.com","sagepub.com","iop.org","aps.org","aip.org"];
const allowed=value=>{try{const u=new URL(value);return u.protocol==="https:"&&!u.username&&!u.password&&domains.some(d=>u.hostname===d||u.hostname.endsWith("."+d));}catch{return false;}};
const samePage=(a,b)=>{try{const x=new URL(a),y=new URL(b);return x.origin===y.origin&&x.pathname===y.pathname;}catch{return false;}};
const safePage=value=>{const u=new URL(value);return u.origin+u.pathname;};
const articlePii=value=>{try{return new URL(value).pathname.match(/\/pii\/(S[0-9X]{16})(?:\/|$)/i)?.[1]?.toUpperCase()||"";}catch{return "";}};
const assetPii=value=>{try{const u=new URL(value);if(u.protocol!=="https:"||u.hostname!=="pdf.sciencedirectassets.com"||u.username||u.password)return "";const id=u.pathname.match(/\/1-s2\.0-(S[0-9X]{16})\/main\.pdf$/i)?.[1]?.toUpperCase()||"";return u.searchParams.has("pii")&&u.searchParams.get("pii").toUpperCase()!==id?"":id;}catch{return "";}};
const doi=value=>String(value||"").trim().replace(/^doi:\s*/i,"").replace(/^https?:\/\/(?:dx\.)?doi\.org\//i,"").toLowerCase();
const validDoi=value=>/^10\.\d{4,9}\/\S+$/i.test(doi(value));
const ieeeArticleId=value=>{try{const u=new URL(value);if(u.protocol!=="https:"||u.hostname!=="ieeexplore.ieee.org"||u.username||u.password)return "";return u.pathname.match(/^\/(?:abstract\/)?document\/([0-9]+)\/?$/)?.[1]||(/^\/(?:stamp\/stamp\.jsp|stampPDF\/getPDF\.jsp)$/i.test(u.pathname)&&/^[0-9]+$/.test(u.searchParams.get("arnumber")||"")?u.searchParams.get("arnumber"):"");}catch{return "";}};
const ieeeArticlePage=value=>{try{return /^\/(?:abstract\/)?document\/[0-9]+\/?$/.test(new URL(value).pathname)&&Boolean(ieeeArticleId(value));}catch{return false;}};
const checking=new Set(),completing=new Set(),opening=new Set(),transfers=new Set();
const failureMessages={DOWNLOAD_SECURITY:"网站拦下了扩展下载；请在已打开PDF的阅读器点下载",NOT_PDF:"网站返回了网页，尚未取得论文PDF",LOCAL_API:"本机接续或下载目录校验失败",BROWSER_OPERATION:"浏览器操作失败，请返回原论文页再检查"};
async function reportFailure(code,job){
 const key=code in failureMessages?code:"BROWSER_OPERATION";
 await chrome.storage.local.set({lastFailure:{code:key,summary:failureMessages[key],when:new Date().toISOString()}});
 await chrome.action.setBadgeText({text:"!"});
 if(job)try{await progress(job,key==="DOWNLOAD_SECURITY"?"NEED_BROWSER_SAVE":"DOWNLOAD_ERROR",true,{failure_code:key});}catch{}
}
async function clearFailure(){await chrome.storage.local.remove("lastFailure");await chrome.action.setBadgeText({text:""});}

async function api(path,data){
 const {token}=await chrome.storage.local.get("token");if(!token)throw Error("请先刷新本机配对页");
 const response=await fetch(ORIGIN+path,{method:data?"POST":"GET",headers:{Authorization:"Bearer "+token,...(data?{"Content-Type":"application/json"}:{})},...(data?{body:JSON.stringify(data)}:{})});
 if(!response.ok)throw Error("本机接续未完成，请查看任务状态或下载目录设置");return response.json();
}
async function progress(job,status,identity=false,s={}){return api("/observe",{session_id:job.session_id,index:job.index,status,identity_matched:identity,
 institution_recognized:Boolean(s.institution_recognized),visible_auth_form:Boolean(s.password_form),pdf_candidates:s.pdf_links?.length||0,extension_version:chrome.runtime.getManifest().version,...(s.failure_code?{failure_code:s.failure_code}:{}),...(s.download_method?{download_method:s.download_method}:{}),...((s.identity_source||job.identity_source)?{identity_source:s.identity_source||job.identity_source}:{})});}
async function openNext(sessionId){
 if(opening.has(sessionId))return {status:"OPENING"};opening.add(sessionId);
 try{
  const {tasks}=await api("/tasks"),task=tasks.find(t=>t.session_id===sessionId);if(!task)return {status:"FINISHED"};
  const terminal=["SAVED","ALREADY_EXISTS","SKIPPED_NO_ACCESS","SKIPPED_BY_USER","ERROR","UNSUPPORTED_PUBLISHER"];
  const index=task.papers.findIndex(p=>!terminal.includes(p.status));if(index<0)return {status:"FINISHED"};
  const paper=task.papers[index];await chrome.storage.local.set({activeSessionId:sessionId});
  const tab=await chrome.tabs.create({url:paper.article_url});const {managed={}}=await chrome.storage.local.get("managed");
  managed[tab.id]={session_id:sessionId,index,doi:paper.doi,attempted:"",ieee_article_id:ieeeArticleId(paper.publisher_article_url||paper.article_url)};await chrome.storage.local.set({managed});
  if((await chrome.tabs.get(tab.id)).status==="complete")await checkTab(tab.id);
  return {status:"OPENED",title:paper.title};
 }finally{opening.delete(sessionId);}
}
async function inspect(tabId){const results=await chrome.scripting.executeScript({target:{tabId},files:["inspect.js"]});return results[0]?.result;}
async function clickArticlePdf(tabId,expected){
 const results=await chrome.scripting.executeScript({target:{tabId},args:[expected],func:(wanted)=>{
  const normalize=v=>String(v||"").trim().replace(/^https?:\/\/(?:dx\.)?doi\.org\//i,"").toLowerCase();
  const current=document.querySelector('meta[name="citation_doi" i]')?.content||document.querySelector('meta[name="dc.Identifier" i]')?.content;
  if(normalize(current)!==normalize(wanted))return {clicked:false};
  const candidates=Array.from(document.querySelectorAll('a,button,[role="button"]')).filter(e=>e.getClientRects().length&&getComputedStyle(e).visibility!=="hidden");
  const control=candidates.find(e=>/^(?:view|download)(?:\s+full[- ]?text)?\s+pdf$/i.test((e.innerText||e.getAttribute('aria-label')||"").trim()));
  if(!control)return {clicked:false};control.click();return {clicked:true};
 }});return results[0]?.result?.clicked===true;
}
async function startDownload(tabId,job,url,snapshot={},force=false){
 const key=job.session_id+":"+job.index,asset=assetPii(url),signature=asset?"resolved:"+asset:url;
 if(asset&&asset!==(job.expected_pii||articlePii(job.article_page)))return {status:"最终PDF与原论文身份不一致，未下载"};
 if(transfers.has(key)||(!force&&job.attempted===signature))return {status:"等待下载结果"};
 transfers.add(key);
 try{
  job.attempted=signature;const {managed={}}=await chrome.storage.local.get("managed");managed[tabId]=job;await chrome.storage.local.set({managed});
  await progress(job,"DOWNLOADING",true,{...snapshot,download_method:"EXTENSION_REQUEST"});
  const id=await chrome.downloads.download({url,filename:`papers-capture/${job.session_id}/${job.index}.pdf`,conflictAction:"uniquify",saveAs:false});
  const {downloads={}}=await chrome.storage.local.get("downloads");downloads[id]=job;await chrome.storage.local.set({downloads});
  const items=await chrome.downloads.search({id});if(items[0]?.state==="complete")await completedDownload(id);
  return {status:"正在下载并校验PDF"};
 }finally{transfers.delete(key);}
}
async function adoptCurrent(tab){
 if(!allowed(tab.url)&&!assetPii(tab.url))throw Error("请先完成机构认证并返回论文页面");
 const {managed={},activeSessionId}=await chrome.storage.local.get(["managed","activeSessionId"]);
 if(managed[tab.id])return;
 if(!activeSessionId)throw Error("请先在扩展选择并开始一个文献任务");
 const {tasks}=await api("/tasks"),task=tasks.find(t=>t.session_id===activeSessionId);if(!task)throw Error("当前任务已结束，请先选择任务");
 if(assetPii(tab.url)){
  const source=Object.values(managed).find(j=>j.session_id===activeSessionId&&j.identity_verified&&(j.expected_pii||articlePii(j.article_page))===assetPii(tab.url));
  if(!source)throw Error("此PDF未与本任务原论文对应，请返回原论文页");
  managed[tab.id]={...source,expected_pii:assetPii(tab.url)};await chrome.storage.local.set({managed});return;
 }
 const s=await inspect(tab.id);const index=task.papers.findIndex(p=>doi(p.doi)===doi(s?.doi) ||
  (!validDoi(s?.doi)&&ieeeArticlePage(tab.url)&&ieeeArticleId(tab.url)===ieeeArticleId(p.publisher_article_url||p.article_url)));
 if(index<0)throw Error("当前页面身份未匹配本任务；请返回原论文页");
 managed[tab.id]={session_id:activeSessionId,index,doi:task.papers[index].doi,attempted:"",ieee_article_id:ieeeArticleId(task.papers[index].publisher_article_url||task.papers[index].article_url)};await chrome.storage.local.set({managed});
}
async function checkTab(tabId,force=false){
 if(checking.has(tabId))return {status:"CHECKING"};checking.add(tabId);
 try{
  const {managed={}}=await chrome.storage.local.get("managed"),job=managed[tabId];if(!job)return {status:"NOT_TRACKED"};
  const tab=await chrome.tabs.get(tabId);
  // 为升级前已打开的任务补上已登记的出版方文章编号，不从当前页面猜对应。
  if(!job.ieee_article_id&&ieeeArticleId(tab.url)){
   const {tasks}=await api("/tasks"),paper=tasks.find(t=>t.session_id===job.session_id)?.papers[job.index];
   const bound=ieeeArticleId(paper?.publisher_article_url||paper?.article_url);
   if(bound){job.ieee_article_id=bound;managed[tabId]=job;await chrome.storage.local.set({managed});}
  }
  if(assetPii(tab.url)){
   const expected=job.expected_pii||articlePii(job.article_page);
   if(!job.identity_verified||expected!==assetPii(tab.url))return {status:"最终PDF与原论文身份不一致，未下载"};
   const {tasks}=await api("/tasks"),paper=tasks.find(t=>t.session_id===job.session_id)?.papers[job.index];
   if(paper?.native_save_required){
    job.native_save_required=true;job.native_until=Date.now()+600000;managed[tabId]=job;await chrome.storage.local.set({managed});
    await progress(job,"NEED_BROWSER_SAVE",true,{failure_code:"DOWNLOAD_SECURITY"});
    return {status:"请点当前PDF阅读器右上角的下载按钮，工具将接收并归档"};
   }
   return startDownload(tabId,job,tab.url,{},force);
  }
  if(!allowed(tab.url))return {status:"请本人完成认证后返回论文页"};
  const s=await inspect(tabId);if(!s)return {status:"ACCESS_UNKNOWN"};
  if(s.challenge){await progress(job,"CHALLENGE_REQUIRED",false,s);return {status:"请本人完成网站验证"};}
  const doiMatched=doi(s.doi)===doi(job.doi);
  const recordMatched=Boolean(!validDoi(s.doi)&&job.ieee_article_id&&ieeeArticlePage(tab.url)&&ieeeArticleId(tab.url)===job.ieee_article_id);
  const matched=doiMatched||recordMatched,viewer=Boolean(job.identity_verified&&job.viewer_url===tab.url);
  if(matched||viewer){job.identity_source=doiMatched?"PAGE_DOI":recordMatched?"IEEE_ARTICLE_URL":"VERIFIED_PDF_VIEWER";s.identity_source=job.identity_source;}
  if(!matched&&!viewer){await progress(job,s.password_form?"NEED_USER_AUTHENTICATION":"ACCESS_UNKNOWN",false,s);return {status:"请返回本篇论文页后再次检查"};}
  // 已匹配论文的PDF候选优先于旁边的个人登录组件；隐藏表单不算认证页面。
  const pdf=(matched?s.pdf_links:(s.viewer_pdf_links||[])).find(u=>(allowed(u)||assetPii(u))&&(!job.ieee_article_id||ieeeArticleId(u)===job.ieee_article_id));
  if(matched&&articlePii(tab.url)){
   job.identity_verified=true;job.expected_pii=articlePii(tab.url);job.article_page=safePage(tab.url);
   if(!force&&job.control_clicked)return {status:"等待官网生成的最终PDF"};
   if(force||!job.control_clicked){
    job.native_until=Date.now()+180000;job.attempted="";job.control_clicked=true;managed[tabId]=job;await chrome.storage.local.set({managed});
    if(await clickArticlePdf(tabId,job.doi)){await progress(job,"ACCESS_UNKNOWN",true,s);return {status:"已点击官网View PDF，正在等待本篇最终文件"};}
    job.control_clicked=false;managed[tabId]=job;await chrome.storage.local.set({managed});
   }
  }
  if(pdf){
   const signature=pdf+"|"+Boolean(s.institution_recognized);if(!force&&job.attempted===signature)return {status:"等待下载或本人授权"};
   job.identity_verified=true;job.article_page=safePage(tab.url);
   if(!viewer&&/\/stamp\/stamp\.jsp(?:\?|$)|\/epdf(?:\/|\?|$)|\/pdfft(?:\?|$)/i.test(pdf)){
    job.attempted=signature;job.viewer_url=pdf;job.native_until=Date.now()+180000;managed[tabId]=job;await chrome.storage.local.set({managed});await progress(job,"ACCESS_UNKNOWN",true,s);
    await chrome.tabs.update(tabId,{url:pdf});setTimeout(()=>checkTab(tabId).catch(()=>{}),3000);return {status:"正在打开本篇PDF预览/下载准备页"};
   }
   return startDownload(tabId,job,pdf,s,force);
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
  if(["SAVED","ALREADY_EXISTS"].includes(state.papers[job.index].status)){await clearFailure();await openNext(job.session_id);}
  else await reportFailure(state.papers[job.index].native_save_required?"DOWNLOAD_SECURITY":"NOT_PDF",job);
 }finally{completing.delete(id);}
}
async function reconcileDownloads(){
 const {downloads={}}=await chrome.storage.local.get("downloads");
 for(const key of Object.keys(downloads))try{await completedDownload(Number(key));}catch{await reportFailure("LOCAL_API");}
}
async function nativeDownloadJob(item){
 const {managed={},activeSessionId}=await chrome.storage.local.get(["managed","activeSessionId"]);
 let activePii="";
 if(/^blob:https:\/\/pdf\.sciencedirectassets\.com\//i.test(item.url||"")&&/^application\/pdf/i.test(item.mime||"")){
  const [active]=await chrome.tabs.query({active:true,currentWindow:true});if(active)activePii=assetPii((await chrome.tabs.get(active.id)).url);
 }
 return Object.values(managed).find(job=>job.session_id===activeSessionId&&job.identity_verified&&job.native_until>Date.now()&&
  (!job.ieee_article_id||[item.url,item.finalUrl].some(u=>ieeeArticleId(u)===job.ieee_article_id))&&(
  (job.ieee_article_id&&[item.url,item.finalUrl].some(u=>ieeeArticleId(u)===job.ieee_article_id))||

  ((job.expected_pii||articlePii(job.article_page))&&([item.url,item.finalUrl].some(u=>assetPii(u)===(job.expected_pii||articlePii(job.article_page)))||activePii===(job.expected_pii||articlePii(job.article_page))))||
  (allowed(item.referrer)&&[job.viewer_url,job.article_page].some(u=>u&&samePage(item.referrer,u))&&
   (samePage(item.url,job.viewer_url)||/\.pdf(?:[?#]|$)/i.test(item.url)||/\.pdf$/i.test(item.filename||"")))));
}
chrome.downloads.onDeterminingFilename.addListener((item,suggest)=>{
 (async()=>{
  const job=await nativeDownloadJob(item);if(!job){suggest();return;}
  if(/^text\/html/i.test(item.mime||"")){await chrome.downloads.cancel(item.id);await reportFailure("DOWNLOAD_SECURITY",job);suggest();return;}
  const {downloads={}}=await chrome.storage.local.get("downloads");downloads[item.id]=job;await chrome.storage.local.set({downloads});
  await progress(job,"DOWNLOADING",true,{download_method:"BROWSER_NATIVE"});suggest({filename:`papers-capture/${job.session_id}/${job.index}.pdf`,conflictAction:"uniquify"});
 })().catch(()=>suggest());return true;
});
chrome.downloads.onChanged.addListener(delta=>{if(delta.state)completedDownload(delta.id).catch(()=>reportFailure("LOCAL_API"));});
async function handleTabReady(id){
 const tab=await chrome.tabs.get(id);const {managed={}}=await chrome.storage.local.get("managed");
 if(!managed[id]&&assetPii(tab.url)){try{await adoptCurrent(tab);}catch{return;}}
 return checkTab(id);
}
chrome.tabs.onUpdated.addListener((id,change)=>{if(change.status==="complete")handleTabReady(id).catch(()=>reportFailure("BROWSER_OPERATION"));});
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
 (async()=>{
  if(message.action==="pair"){
   if(!sender.url?.startsWith(ORIGIN+"/pair")||!/^[-_a-zA-Z0-9]{40,60}$/.test(message.token||""))throw Error("配对来源无效");
   await chrome.storage.local.set({token:message.token});await api("/health");return {status:"PAIRED"};
  }
  if(message.action==="tasks"){const result=await api("/tasks");const {lastFailure}=await chrome.storage.local.get("lastFailure");return {...result,last_failure:lastFailure};}
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
 })().then(reply).catch(async error=>{await reportFailure("BROWSER_OPERATION");reply({error:error.message});});return true;
});
