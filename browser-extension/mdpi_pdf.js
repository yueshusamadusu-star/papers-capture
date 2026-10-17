"use strict";
// MDPI逐篇绑定：先核对原网页DOI，再核对卷/期/文章号与官方文件路径。
function mdpiArticleRecord(value){
 try{
  const u=new URL(value);
  if(u.protocol!=="https:"||u.port||u.username||u.password||!["mdpi.com","www.mdpi.com"].includes(u.hostname))return null;
  const m=u.pathname.match(/^\/(\d{4}-\d{3}[\dX])\/([1-9]\d{0,4})\/([1-9]\d{0,3})\/([1-9]\d{0,6})(?:\/pdf)?\/?$/i);
  return m?{path:"/"+m.slice(1).join("/"),volume:m[2],issue:m[3],number:m[4]}:null;
 }catch{return null;}
}
function mdpiPdfLocation(value){
 try{const u=new URL(value);return u.protocol==="https:"&&!u.username&&!u.password&&!u.port&&
  ((["mdpi.com","www.mdpi.com"].includes(u.hostname)&&Boolean(mdpiArticleRecord(value))&&/\/pdf$/.test(u.pathname))||
   (u.hostname==="mdpi-res.com"&&/\.pdf$/.test(u.pathname)));}catch{return false;}
}
function mdpiBinding(job){
 if(!job.identity_verified)return null;
 const record=mdpiArticleRecord(job.article_page);
 if(!record||!/^10\.3390\//.test(doi(job.doi)))return null;
 const tail=record.volume+record.issue.padStart(2,"0")+record.number.padStart(4,"0"),suffix=doi(job.doi).slice(8);
 if(!suffix.endsWith(tail))return null;
 const journal=suffix.slice(0,-tail.length);if(!/^[a-z][a-z0-9]*$/.test(journal))return null;
 return {...record,journal,slug:journal+"-"+record.volume.padStart(2,"0")+"-"+record.number.padStart(5,"0")};
}
function mdpiFileIdentity(job,value){
 try{
  const b=mdpiBinding(job),u=new URL(value);if(!b||u.protocol!=="https:"||u.port||u.username||u.password)return false;
  if(["mdpi.com","www.mdpi.com"].includes(u.hostname))return u.pathname===b.path+"/pdf";
  return u.hostname==="mdpi-res.com"&&u.pathname===`/d_attachment/${b.journal}/${b.slug}/article_deploy/${b.slug}.pdf`;
 }catch{return false;}
}
async function restoreMdpiFile(tab,requestedSession=""){
 const {managed={},activeSessionId}=await chrome.storage.local.get(["managed","activeSessionId"]);
 const selected=requestedSession||activeSessionId;
 const candidates=Object.values(managed).filter(j=>j.session_id===selected&&mdpiFileIdentity(j,tab.url));
 const keys=new Set(candidates.map(transferKey));if(keys.size!==1)return false;
 const parent=candidates[0],{tasks}=await api("/tasks"),paper=tasks.find(t=>t.session_id===selected)?.papers[parent.index];
 if(!paper||terminalPaper(paper)||doi(paper.doi)!==doi(parent.doi)||(paper.active_attempt?.id||"")!==(parent.attempt_id||""))return false;
 managed[tab.id]={...parent};await chrome.storage.local.set({managed});return true;
}
