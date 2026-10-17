"use strict";
importScripts("chrome_ieee.js","direct_save.js","auto_pdf.js","resume_binding.js");
const ORIGIN="http://127.0.0.1:8766";
const domains=["sciencedirect.com","elsevier.com","ieee.org","scitepress.org","mdpi.com","mdpi-res.com","arxiv.org","ncbi.nlm.nih.gov","springer.com","springerlink.com","nature.com","wiley.com","tandfonline.com","acm.org","cambridge.org","oup.com","sagepub.com","iop.org","aps.org","aip.org"];
const allowed=value=>{try{const u=new URL(value);return u.protocol==="https:"&&!u.username&&!u.password&&domains.some(d=>u.hostname===d||u.hostname.endsWith("."+d));}catch{return false;}};
const samePage=(a,b)=>{try{const x=new URL(a),y=new URL(b);return x.origin===y.origin&&x.pathname===y.pathname;}catch{return false;}};
const safePage=value=>{const u=new URL(value);return u.origin+u.pathname;};
const articlePii=value=>{try{return new URL(value).pathname.match(/\/pii\/(S[0-9X]{16})(?:\/|$)/i)?.[1]?.toUpperCase()||"";}catch{return "";}};
const assetPii=value=>{try{const u=new URL(value);if(u.protocol!=="https:"||u.hostname!=="pdf.sciencedirectassets.com"||u.username||u.password)return "";const id=u.pathname.match(/\/1-s2\.0-(S[0-9X]{16})\/main\.pdf$/i)?.[1]?.toUpperCase()||"";return u.searchParams.has("pii")&&u.searchParams.get("pii").toUpperCase()!==id?"":id;}catch{return "";}};
const doi=value=>String(value||"").trim().replace(/^doi:\s*/i,"").replace(/^https?:\/\/(?:dx\.)?doi\.org\//i,"").toLowerCase();
const validDoi=value=>/^10\.\d{4,9}\/\S+$/i.test(doi(value));
const ieeeArticleId=value=>{try{
 const u=new URL(value);if(u.protocol!=="https:"||u.hostname!=="ieeexplore.ieee.org"||u.username||u.password)return "";
 const file=u.pathname.match(/^\/iel(?:x)?7\/[0-9]+\/[0-9]+\/([0-9]+)\.pdf$/i)?.[1];
 const id=u.pathname.match(/^\/(?:abstract\/)?document\/([0-9]+)\/?$/)?.[1]||file?.replace(/^0+(?=[0-9])/,"")||
  (/^\/(?:stamp\/stamp\.jsp|stampPDF\/getPDF\.jsp)$/i.test(u.pathname)&&/^[0-9]+$/.test(u.searchParams.get("arnumber")||"")?u.searchParams.get("arnumber"):"");
 return id&&u.searchParams.getAll("arnumber").every(n=>/^[0-9]+$/.test(n)&&n.replace(/^0+(?=[0-9])/,"")===id)?id:"";
}catch{return "";}};
const ieeeArticlePage=value=>{try{return /^\/(?:abstract\/)?document\/[0-9]+\/?$/.test(new URL(value).pathname)&&Boolean(ieeeArticleId(value));}catch{return false;}};
const aipRecordKey=value=>{try{const u=new URL(value);if(u.protocol!=="https:"||u.hostname!=="pubs.aip.org"||u.username||u.password)return "";return u.pathname.match(/^\/aip\/([a-z0-9]+)\/article(?:-abstract|-pdf)?\/([0-9]+)\/([0-9]+)\/([a-z0-9]+)\//i)?.slice(1).join("/").toLowerCase()||"";}catch{return "";}};
function aipFileIdentity(job,value){try{
 const u=new URL(value);if(u.protocol!=="https:"||u.hostname!=="pubs.aip.org"||u.username||u.password||!/^10\.1063\//i.test(job.doi||""))return false;
 const fromDoi=u.pathname.match(/^\/aip\/[a-z0-9]+\/article-pdf\/doi\/(.+)\/[0-9]+\/[^/]+\.pdf$/i)?.[1];
 if(fromDoi)return doi(decodeURIComponent(fromDoi))===doi(job.doi);
 return /^\/aip\/[a-z0-9]+\/article-pdf\/[0-9]+\/[0-9]+\/[a-z0-9]+\/[0-9]+\/[^/]+\.pdf$/i.test(u.pathname)&&Boolean(aipRecordKey(job.article_page)&&aipRecordKey(u.href)===aipRecordKey(job.article_page));
}catch{return false;}}
const checking=new Set(),completing=new Set(),opening=new Set(),transfers=new Set();
const failureMessages={FETCH_PDF:"未取得完整PDF，已停止；请返回原论文页检查访问权限",SAVE_DIRECTORY:"PDF未保存，请检查插件中的保存目录",DOWNLOAD_SECURITY:"网站拦下了扩展下载；请在已打开PDF的阅读器点下载",NOT_PDF:"网站返回了网页，尚未取得论文PDF",LOCAL_API:"本机接续或下载目录校验失败",BROWSER_OPERATION:"浏览器操作失败，请返回原论文页再检查"};
async function reportFailure(code,job){
 const key=code in failureMessages?code:"BROWSER_OPERATION";
 await chrome.storage.local.set({lastFailure:{code:key,summary:failureMessages[key],when:new Date().toISOString()}});
 await chrome.action.setBadgeText({text:"!"});
 if(job)try{await progress(job,key==="DOWNLOAD_SECURITY"?"NEED_BROWSER_SAVE":key==="FETCH_PDF"?"ACCESS_UNKNOWN":"DOWNLOAD_ERROR",true,{failure_code:key});}catch{}
}
async function clearFailure(){await chrome.storage.local.remove("lastFailure");await chrome.action.setBadgeText({text:""});}

async function api(path,data){
 const {token}=await chrome.storage.local.get("token");if(!token)throw Error("请先刷新本机配对页");
 const response=await fetch(ORIGIN+path,{method:data?"POST":"GET",headers:{Authorization:"Bearer "+token,...(data?{"Content-Type":"application/json"}:{})},...(data?{body:JSON.stringify(data)}:{})});
 if(!response.ok)throw Error("本机接续未完成，请查看任务状态或下载目录设置");return response.json();
}
async function progress(job,status,identity=false,s={}){return api("/observe",{session_id:job.session_id,index:job.index,status,identity_matched:identity,
 institution_recognized:Boolean(s.institution_recognized),visible_auth_form:Boolean(s.password_form),pdf_candidates:s.pdf_links?.length||0,extension_version:chrome.runtime.getManifest().version,...(s.failure_code?{failure_code:s.failure_code}:{}),...(s.download_method?{download_method:s.download_method}:{}),...(s.download_trigger?{download_trigger:s.download_trigger}:{}),...((s.identity_source||job.identity_source)?{identity_source:s.identity_source||job.identity_source}:{})});}
async function openNext(sessionId){
 if(opening.has(sessionId))return {status:"OPENING"};opening.add(sessionId);
 try{
  const {tasks}=await api("/tasks"),task=tasks.find(t=>t.session_id===sessionId);if(!task)return {status:"FINISHED"};
  const terminal=["SAVED","ALREADY_EXISTS","SKIPPED_NO_ACCESS","SKIPPED_BY_USER","ERROR","UNSUPPORTED_PUBLISHER"];
  const index=task.papers.findIndex(p=>!terminal.includes(p.status));if(index<0)return {status:"FINISHED"};
  const paper=task.papers[index];await chrome.storage.local.set({activeSessionId:sessionId});
  let routeNote="";
  if(/^10\.1109\//i.test(paper.doi||"")){
   const route=await api("/ieee-network");
   const browserRoute=await chromeIeeeRoute.read();
   if(browserRoute.enabled&&!browserRoute.configuration_verified)return {status:"Chrome的IEEE规则未确认，请点“检查Chrome代理”查看原因"};
   routeNote=browserRoute.configuration_verified?"IEEE：Chrome已读回专用直连规则，实际访问仍需核对":route.direct_rule_present?"IEEE：已配置系统直连例外；418先核对网络":"IEEE：可使用校园网直连或本人机构访问入口";
   if(!browserRoute.configuration_verified&&route.policy_enabled&&!route.direct_rule_present&&route.status!=="NO_SYSTEM_PROXY"){
    await progress({session_id:sessionId,index},"NEED_IEEE_NETWORK_ROUTE",false,{failure_code:"IEEE_NETWORK_ERROR"});
    return {status:"IEEE直连规则尚未生效，请点“IEEE校园网直连”后接续"};
   }
  }
  const tab=await chrome.tabs.create({url:paper.article_url});const {managed={}}=await chrome.storage.local.get("managed");
  managed[tab.id]=paperJob(sessionId,index,paper);await chrome.storage.local.set({managed});
  if((await chrome.tabs.get(tab.id)).status==="complete")await checkTab(tab.id);
  return {status:"OPENED",title:paper.title,route_note:routeNote};
 }finally{opening.delete(sessionId);}
}
async function inspect(tabId){const results=await chrome.scripting.executeScript({target:{tabId},files:["inspect.js"]});return results[0]?.result;}
async function clickArticlePdf(tabId,expected,pii=""){
 const results=await chrome.scripting.executeScript({target:{tabId},args:[expected,pii],func:(wanted,registeredPii)=>{
  const normalize=v=>String(v||"").trim().replace(/^https?:\/\/(?:dx\.)?doi\.org\//i,"").toLowerCase();
  const current=document.querySelector('meta[name="citation_doi" i]')?.content||document.querySelector('meta[name="dc.Identifier" i]')?.content;
  if(normalize(current)!==normalize(wanted)){
   const pagePii=location.pathname.match(/\/pii\/(S[0-9X]{16})(?:\/|$)/i)?.[1]?.toUpperCase();
   if(/^10\.\d{4,9}\/\S+$/i.test(normalize(current))||!["www.sciencedirect.com","sciencedirect.com"].includes(location.hostname)||!registeredPii||pagePii!==registeredPii)return {clicked:false};
  }
  const candidates=Array.from(document.querySelectorAll('a,button,[role="button"]')).filter(e=>e.getClientRects().length&&getComputedStyle(e).visibility!=="hidden");
  const isPdf=v=>/^(?:view|download)\s*(?:full[- ]?text\s*)?pdf(?:\s*\(opens? in (?:a )?new (?:tab|window)\))?$/i.test(String(v||"").replace(/\s+/g," ").trim());
  const control=candidates.find(e=>isPdf(e.innerText)||isPdf(e.getAttribute('aria-label')));
  if(!control)return {clicked:false};control.click();return {clicked:true};
 }});return results[0]?.result?.clicked===true;
}
async function startDownload(tabId,job,url,snapshot={},force=false){
 const key=job.session_id+":"+job.index,asset=assetPii(url),ieee=ieeeArticleId(url),signature=asset?"resolved:"+asset:ieee?"ieee-file:"+ieee:aipFileIdentity(job,url)?"aip-file:"+doi(job.doi):url;
 if(asset&&asset!==(job.expected_pii||articlePii(job.article_page)))return {status:"最终PDF与原论文身份不一致，未下载"};
 if(transfers.has(key)||(!force&&job.attempted===signature))return {status:"等待下载结果"};
 transfers.add(key);
 try{
  const direct=fileResponseIdentity(job,url);
  if(new URL(url).hostname==="pubs.aip.org"&&!direct){await progress(job,"ACCESS_UNKNOWN",true,snapshot);return {status:"AIP文件身份尚未核对，未下载网页；请查看官网PDF或浙大数据库访问说明"};}
  job.attempted=signature;job.transfer_method=direct?"EXTENSION_FETCH":"EXTENSION_REQUEST";job.download_trigger=snapshot.download_trigger||"DOCUMENT_LINK";const {managed={}}=await chrome.storage.local.get("managed");managed[tabId]=job;await chrome.storage.local.set({managed});
  await progress(job,"DOWNLOADING",true,{...snapshot,download_method:job.transfer_method,download_trigger:job.download_trigger});
  if(direct)return await savePdfDirect(tabId,job,url);
  const id=await chrome.downloads.download({url,filename:`papers-capture/${job.session_id}/${job.index}.pdf`,conflictAction:"uniquify",saveAs:false});
  const {downloads={}}=await chrome.storage.local.get("downloads");downloads[id]=job;await chrome.storage.local.set({downloads});
  const items=await chrome.downloads.search({id});if(items[0]?.state==="complete")await completedDownload(id);
  return {status:"正在下载并校验PDF"};
 }finally{transfers.delete(key);}
}
async function adoptCurrent(tab){
 if((assetPii(tab.url)||sdArticle(tab.url))&&await restoreScienceDirect(tab))return;
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
  if(job.auto_pdf_started||autoPdfStarting.has(transferKey(job)))return {status:"正在自动下载并校验PDF"};
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
  if(sdArticle(tab.url))await watchScienceDirect(tabId);
  const s=await inspect(tabId);if(!s)return {status:"ACCESS_UNKNOWN"};
  if(job.ieee_article_id&&s.ieee_network_error){
   await progress(job,"NEED_IEEE_NETWORK_ROUTE",false,{...s,failure_code:"IEEE_HTTP_418"});
   return {status:"IEEE返回418，请检查Chrome代理规则或原代理软件的IEEE直连；不要反复登录，保持当前任务"};
  }
  if(s.challenge){await progress(job,"CHALLENGE_REQUIRED",false,s);return {status:"请本人完成网站验证"};}
  const doiMatched=doi(s.doi)===doi(job.doi);
  const recordMatched=Boolean(!validDoi(s.doi)&&job.ieee_article_id&&ieeeArticlePage(tab.url)&&ieeeArticleId(tab.url)===job.ieee_article_id);
  const sdMatched=Boolean(!validDoi(s.doi)&&job.identity_verified&&job.expected_pii&&sdArticle(tab.url)&&articlePii(tab.url)===job.expected_pii);
  const matched=doiMatched||recordMatched||sdMatched,viewer=Boolean(job.identity_verified&&job.viewer_url===tab.url);
  if(matched||viewer){job.identity_source=doiMatched?"PAGE_DOI":recordMatched?"IEEE_ARTICLE_URL":sdMatched?"CROSSREF_PII":"VERIFIED_PDF_VIEWER";s.identity_source=job.identity_source;}
  if(!matched&&!viewer){await progress(job,s.password_form?"NEED_USER_AUTHENTICATION":"ACCESS_UNKNOWN",false,s);return {status:"请返回本篇论文页后再次检查"};}
  // AIP摘要页也可能声明citation_pdf_url；购买页上的元标签不能证明已拿到全文。
  if(matched&&aipRecordKey(tab.url)&&s.pdf_controls===0&&(s.no_access||s.password_form)){
   job.identity_verified=true;job.article_page=safePage(tab.url);managed[tabId]=job;await chrome.storage.local.set({managed});
   if(s.institution_recognized&&s.no_access){await progress(job,"SKIPPED_NO_ACCESS",true,s);await openNext(job.session_id);return {status:"本篇无权限，已退避"};}
   await progress(job,"NEED_USER_AUTHENTICATION",true,s);return {status:"AIP当前是摘要/购买页，未取得PDF；请点浙大数据库访问说明完成可用访问路线，再回本篇检查"};
  }
  // 已匹配论文的PDF候选优先于旁边的个人登录组件；隐藏表单不算认证页面。
  const pdf=(matched?s.pdf_links:(s.viewer_pdf_links||[])).find(u=>(allowed(u)||assetPii(u))&&(!job.ieee_article_id||ieeeArticleId(u)===job.ieee_article_id));
  if(matched&&articlePii(tab.url)){
   job.identity_verified=true;job.expected_pii=articlePii(tab.url);job.article_page=safePage(tab.url);
   const context=[Boolean(s.institution_recognized),Boolean(s.password_form),Boolean(s.no_access),s.pdf_controls||0].join(":");
   if(job.control_context!==context){job.control_clicked=false;job.control_context=context;}
   if(!force&&job.control_clicked)return {status:"等待官网生成的最终PDF"};
   if(force||!job.control_clicked){
    job.native_until=Date.now()+180000;job.attempted="";job.control_clicked=true;managed[tabId]=job;await chrome.storage.local.set({managed});
    if(await clickArticlePdf(tabId,job.doi,job.expected_pii)){await progress(job,"ACCESS_UNKNOWN",true,s);return {status:"已点击官网View PDF，正在等待本篇最终文件"};}
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
  if(viewer&&job.ieee_article_id&&!pdf&&!s.no_access&&!s.password_form){
   const automatic=await retryKnownIeeeFile(tabId,job);if(automatic)return automatic;
   if(autoPdfStarting.has(transferKey(job)))return {status:"正在自动下载并校验PDF"};
   job.native_until=Date.now()+600000;managed[tabId]=job;await chrome.storage.local.set({managed});
   await progress(job,"NEED_BROWSER_SAVE",true,s);
   return {status:"已进入PDF预览，正在等待识别文件响应；尚未自动保存。若需人工保存会明确提示"};
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
  if(item.state==="interrupted"){await stopAutomaticTransfer(job);await progress(job,"DOWNLOAD_ERROR",true);delete downloads[id];await chrome.storage.local.set({downloads});return;}
  if(item.state!=="complete")return;
  if(item.byExtensionId===chrome.runtime.id)job.transfer_method="EXTENSION_REQUEST";
  let state;
  try{state=await api("/complete",{session_id:job.session_id,index:job.index,download_path:item.filename,download_method:job.transfer_method,download_trigger:job.download_trigger,...(item.byExtensionId?{extension_initiated:item.byExtensionId===chrome.runtime.id}:{})});}
  catch{await stopAutomaticTransfer(job);await reportFailure("LOCAL_API",job);return;}
  delete downloads[id];await chrome.storage.local.set({downloads});await stopAutomaticTransfer(job);
  if(["SAVED","ALREADY_EXISTS"].includes(state.papers[job.index].status)){await chrome.storage.local.set({lastSuccess:{summary:(job.transfer_method==="EXTENSION_REQUEST"?"自动下载并校验保存":"接收本人保存并归档")+"："+(state.papers[job.index].title||job.doi)}});await clearFailure();await openNext(job.session_id);}
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
  if(item.byExtensionId&&item.byExtensionId===chrome.runtime.id){suggest();return;}
  const job=await nativeDownloadJob(item);if(!job){suggest();return;}
  job.transfer_method="BROWSER_NATIVE";job.download_trigger="READER_BUTTON";
  if(/^text\/html/i.test(item.mime||"")){await chrome.downloads.cancel(item.id);await reportFailure("DOWNLOAD_SECURITY",job);suggest();return;}
  const {downloads={}}=await chrome.storage.local.get("downloads");downloads[item.id]=job;await chrome.storage.local.set({downloads});
  await progress(job,"DOWNLOADING",true,{download_method:"BROWSER_NATIVE"});suggest({filename:`papers-capture/${job.session_id}/${job.index}.pdf`,conflictAction:"uniquify"});
 })().catch(()=>suggest());return true;
});
chrome.downloads.onChanged.addListener(delta=>{if(delta.state)completedDownload(delta.id).catch(()=>reportFailure("LOCAL_API"));});
async function handleTabReady(id){
 const tab=await chrome.tabs.get(id);const {managed={}}=await chrome.storage.local.get("managed");
 if(assetPii(tab.url)||sdArticle(tab.url)){
  if(!await restoreScienceDirect(tab))return {status:"当前论文未匹配所选待处理篇"};
 }else if(!managed[id])return;
 return checkTab(id);
}
chrome.tabs.onUpdated.addListener((id,change,tab)=>{
 if(change.status==="loading"&&sdArticle(tab?.url))resetArticleNavigation(id).catch(()=>{});
 if(change.status==="complete")handleTabReady(id).catch(()=>reportFailure("BROWSER_OPERATION"));
});
chrome.tabs.onActivated?.addListener(info=>{handleTabReady(info.tabId).catch(()=>{});});
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
 (async()=>{
  if(message.action==="article-ready"){
   if(!sender.tab?.id||!sdArticle(sender.url))return {status:"IGNORED"};
   return handleTabReady(sender.tab.id);
  }
  if(message.action==="pair"){
   if(!sender.url?.startsWith(ORIGIN+"/pair")||!/^[-_a-zA-Z0-9]{40,60}$/.test(message.token||""))throw Error("配对来源无效");
   await chrome.storage.local.set({token:message.token});await api("/health");return {status:"PAIRED"};
  }
  if(message.action==="preferences")return api("/preferences");
  if(message.action==="save-preferences"){
   if(sender.url&&!sender.url.startsWith("chrome-extension://"+chrome.runtime.id+"/"))throw Error("请在插件窗口设置目录");
   return api("/preferences",{save_directory:message.save_directory});
  }
  if(message.action==="tasks"){const result=await api("/tasks");const {lastFailure,lastSuccess}=await chrome.storage.local.get(["lastFailure","lastSuccess"]);return {...result,last_failure:lastFailure,last_success:lastSuccess};}
  if(["chrome-ieee-inspect","chrome-ieee-enable","chrome-ieee-restore"].includes(message.action)){
   let result;
   if(message.action==="chrome-ieee-enable")result=await chromeIeeeRoute.enable(()=>api("/ieee-network-template"));
   else if(message.action==="chrome-ieee-restore")result=await chromeIeeeRoute.restore();
   else result=await chromeIeeeRoute.read();
   try{await api("/ieee-browser-diagnostic",{...result,extension_version:chrome.runtime.getManifest().version});}catch{}
   const notes={
    BROWSER_RULE_CONFIGURED:"Chrome已采用IEEE直连规则，其他网站保留原代理；请重新打开IEEE论文验证。尚未确认校园网出口或PDF",
    NEED_PROXY_PERMISSION:"扩展尚未取得Chrome代理权限，请更新扩展并确认权限",
    BROWSER_OVERRIDE_CLEARED:"已撤销本扩展的Chrome代理控制，恢复原代理配置",
    ALREADY_DIRECT:"Chrome设置为直连；若仍418，不能据此认定代理是原因"
   };
   return {status:notes[result.status]||("Chrome代理模式："+result.mode+"；控制来源："+result.level+"。尚未确认IEEE直连"),network:result};
  }
  if(message.action==="ieee-direct"){
   const result=await api("/ieee-network",{action:"enable"});
   return {status:result.direct_rule_present?"IEEE域名已加入系统代理直连例外；请回原论文页检查":"IEEE直连需在原代理软件中配置"};
  }
  if(message.action==="ieee-restore"){
   await api("/ieee-network",{action:"restore"});return {status:"已撤销本工具添加的IEEE例外，保留其他代理设置"};
  }
  if(message.action==="start")return openNext(message.session_id);
  if(message.action==="library-access"){
   const [tab]=await chrome.tabs.query({active:true,currentWindow:true});const {managed={}}=await chrome.storage.local.get("managed");
   const url=/^10\.1063\//i.test(managed[tab?.id]?.doi||"")?"https://libdb.zju.edu.cn/s/lib/libtb/show/490":"https://libdb.zju.edu.cn/";
   await chrome.tabs.create({url});return {status:"已打开浙大数据库访问说明；数据库订购信息不代替本篇权限核验"};
  }
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
