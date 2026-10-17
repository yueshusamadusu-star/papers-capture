"use strict";
const terminalPaper=p=>["SAVED","ALREADY_EXISTS","SKIPPED_NO_ACCESS","SKIPPED_BY_USER","ERROR","UNSUPPORTED_PUBLISHER"].includes(p?.status);
const sdArticle=value=>{try{const u=new URL(value);return u.protocol==="https:"&&["www.sciencedirect.com","sciencedirect.com"].includes(u.hostname)&&!u.username&&!u.password&&Boolean(articlePii(value));}catch{return false;}};
const restoringTabs=new Map();
function paperJob(session,index,paper){
 const binding=paper.publisher_binding;
 const trusted=binding?.source==="Crossref"&&doi(binding.doi)===doi(paper.doi)&&/^S[0-9X]{16}$/.test(binding.publisher_pii||"");
 return {session_id:session,index,doi:paper.doi,attempted:"",ieee_article_id:ieeeArticleId(paper.publisher_article_url||paper.article_url),
  ...(trusted?{expected_pii:binding.publisher_pii,article_page:binding.publisher_article_url}: {})};
}
function pendingIndex(task){return Number.isInteger(task.current_index)?task.current_index:task.papers.findIndex(p=>!terminalPaper(p));}
function registeredPii(paper){
 const b=paper?.publisher_binding;
 return b?.source==="Crossref"&&doi(b.doi)===doi(paper.doi)&&b.publisher_pii===articlePii(b.publisher_article_url)&&sdArticle(b.publisher_article_url)?b.publisher_pii:"";
}
function chooseSdTask(tasks,tab,active,requested=""){
 const pii=assetPii(tab.url)||articlePii(tab.url);
 const matches=tasks.filter(t=>{const p=t.papers[pendingIndex(t)];return p&&!terminalPaper(p)&&registeredPii(p)===pii&&Boolean(pii);});
 const selected=matches.find(t=>t.session_id===requested)||matches.find(t=>t.session_id===active);
 if(selected)return {task:selected};
 if(matches.length===1)return {task:matches[0]};
 if(matches.length>1)return {reason:"AMBIGUOUS_TASK"};
 const fallback=tasks.find(t=>t.session_id===requested)||tasks.find(t=>t.session_id===active);
 return fallback?{task:fallback}:{reason:"NO_TASK"};
}
const resumeMessages={NO_TASK:"没有找到本页面所属的待处理任务",AMBIGUOUS_TASK:"多份任务包含同一论文，请在插件选择要保存的任务",PII_MISMATCH:"当前PDF编号与待处理论文不同",NO_OFFICIAL_BINDING:"尚未取得这篇论文的官方对应",DOI_CONFLICT:"页面DOI与任务登记冲突",UNRELATED_PAGE:"当前不是可对应的ScienceDirect论文页"};
async function recordResume(tab,result,context={}){
 const observed=assetPii(tab.url)||articlePii(tab.url);
 const version=chrome.runtime.getManifest().version;
 const summary=result==="BOUND"?"已恢复当前论文对应":resumeMessages[result]||"当前页面任务检查";
 await chrome.storage.local.set({lastResume:{code:result,summary,version,expected_pii:context.expected_pii||"",observed_pii:observed}});
 try{await api("/extension-diagnostic",{extension_version:version,page_kind:assetPii(tab.url)?"SD_PDF":sdArticle(tab.url)?"SD_ARTICLE":"OTHER",result,observed_pii:observed,...context});}catch{}
}
async function popupTaskContext(tasks){
 const {activeSessionId}=await chrome.storage.local.get("activeSessionId");
 const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
 const choice=tab&&(assetPii(tab.url)||sdArticle(tab.url))?chooseSdTask(tasks,tab,activeSessionId):{};
 if(tab&&(assetPii(tab.url)||sdArticle(tab.url)))await recordResume(tab,"POPUP",{active_session:activeSessionId,chosen_session:choice.task?.session_id});
 return {active_session_id:activeSessionId,recommended_session_id:choice.task?.session_id,extension_version:chrome.runtime.getManifest().version};
}
async function restoreScienceDirect(tab,requestedSession=""){
 if(!assetPii(tab.url)&&!sdArticle(tab.url))return false;
 if(restoringTabs.has(tab.id))return restoringTabs.get(tab.id);
 const operation=(async()=>{
  const {activeSessionId,managed={}}=await chrome.storage.local.get(["activeSessionId","managed"]);
  const {tasks}=await api("/tasks"),choice=chooseSdTask(tasks,tab,activeSessionId,requestedSession),task=choice.task;
  const context={active_session:activeSessionId,requested_session:requestedSession,chosen_session:task?.session_id};
  const reject=async reason=>{await recordResume(tab,reason,context);return false;};
  if(!task)return reject(choice.reason||"NO_TASK");
  const index=pendingIndex(task),paper=task.papers[index];if(!paper||terminalPaper(paper))return reject("NO_TASK");
  const pii=assetPii(tab.url)||articlePii(tab.url),old=managed[tab.id],session=task.session_id;
  let job=paperJob(session,index,paper);
  const parent=Object.values(managed).find(j=>j.session_id===session&&j.index===index&&doi(j.doi)===doi(paper.doi)&&j.identity_verified&&(j.expected_pii||articlePii(j.article_page))===pii);
  if(!job.expected_pii&&parent)job={...parent};
  if(!job.expected_pii){
   const binding=await api("/paper-binding",{session_id:session,index});
   if(binding.status!=="BOUND"||doi(binding.doi)!==doi(paper.doi)||binding.source!=="Crossref")return reject("NO_OFFICIAL_BINDING");
   job={...job,expected_pii:binding.publisher_pii,article_page:binding.publisher_article_url,identity_source:"CROSSREF_PII"};
  }
  context.expected_pii=job.expected_pii;
  if(job.expected_pii!==pii)return reject("PII_MISMATCH");
  if(sdArticle(tab.url)){
   const snapshot=await inspect(tab.id);
   if(validDoi(snapshot?.doi)&&doi(snapshot.doi)!==doi(paper.doi))return reject("DOI_CONFLICT");
  }
  if(old&&old.session_id===session&&old.index===index)job={...old,...job,attempted:old.attempted||""};
  job.identity_verified=true;job.identity_source=job.identity_source||"CROSSREF_PII";
  const latest=await chrome.storage.local.get("managed");
  latest.managed=latest.managed||{};latest.managed[tab.id]=job;await chrome.storage.local.set({managed:latest.managed,activeSessionId:session});
  await recordResume(tab,"BOUND",context);
  return true;
 })();
 restoringTabs.set(tab.id,operation);
 try{return await operation;}finally{restoringTabs.delete(tab.id);}
}
async function watchScienceDirect(tabId){
 try{await chrome.scripting.executeScript({target:{tabId},files:["watch_article.js"]});}catch{}
}

async function resetArticleNavigation(tabId){
 const {managed={}}=await chrome.storage.local.get("managed");
 if(!managed[tabId])return;
 managed[tabId].control_clicked=false;delete managed[tabId].control_context;
 await chrome.storage.local.set({managed});
}
