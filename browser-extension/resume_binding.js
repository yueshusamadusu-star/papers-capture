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
async function restoreScienceDirect(tab){
 if(!assetPii(tab.url)&&!sdArticle(tab.url))return false;
 if(restoringTabs.has(tab.id))return restoringTabs.get(tab.id);
 const operation=(async()=>{
  const {activeSessionId,managed={}}=await chrome.storage.local.get(["activeSessionId","managed"]);
  if(!activeSessionId)return false;
  const {tasks}=await api("/tasks"),task=tasks.find(t=>t.session_id===activeSessionId);if(!task)return false;
  const index=Number.isInteger(task.current_index)?task.current_index:task.papers.findIndex(p=>!terminalPaper(p));
  const paper=task.papers[index];if(!paper||terminalPaper(paper))return false;
  const pii=assetPii(tab.url)||articlePii(tab.url),old=managed[tab.id];
  let job=paperJob(activeSessionId,index,paper);
  // 兼容同次已核对DOI的父标签；丢失父标签时必须恢复官方登记，不能信当前文件自报。
  const parent=Object.values(managed).find(j=>j.session_id===activeSessionId&&j.index===index&&doi(j.doi)===doi(paper.doi)&&j.identity_verified&&(j.expected_pii||articlePii(j.article_page))===pii);
  if(!job.expected_pii&&parent)job={...parent};
  if(!job.expected_pii){
   const binding=await api("/paper-binding",{session_id:activeSessionId,index});
   if(binding.status!=="BOUND"||doi(binding.doi)!==doi(paper.doi)||binding.source!=="Crossref")return false;
   job={...job,expected_pii:binding.publisher_pii,article_page:binding.publisher_article_url,identity_source:"CROSSREF_PII"};
  }
  if(job.expected_pii!==pii)return false;
  if(sdArticle(tab.url)){
   const snapshot=await inspect(tab.id);
   if(validDoi(snapshot?.doi)&&doi(snapshot.doi)!==doi(paper.doi))return false;
  }
  if(old&&old.session_id===activeSessionId&&old.index===index)job={...old,...job,attempted:old.attempted||""};
  job.identity_verified=true;job.identity_source=job.identity_source||"CROSSREF_PII";
  const latest=await chrome.storage.local.get("managed");
  latest.managed=latest.managed||{};latest.managed[tab.id]=job;await chrome.storage.local.set({managed:latest.managed});
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
