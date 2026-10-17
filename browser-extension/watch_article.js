(() => {
 // 只在已选论文的ScienceDirect文章页安装；不进入学校登录域或读取输入值。
 if(globalThis.__papersCaptureWatcher)return;
 globalThis.__papersCaptureWatcher=true;
 let timer,notices=0,last="";
 const fingerprint=()=>{
  const body=document.body?.innerText||"";
  const labels=Array.from(document.querySelectorAll('a,button,[role="button"]')).filter(e=>e.getClientRects().length).map(e=>(e.innerText||e.getAttribute('aria-label')||"").trim()).filter(t=>/^(view|download).*pdf/i.test(t)).slice(0,6).join("|");
  return JSON.stringify([document.querySelector('meta[name="citation_doi" i]')?.content||"",labels,/brought to you by|access provided by|浙江大学图书馆/i.test(body),/verify.*human|captcha|checking your browser/i.test(body),/purchase.*article|buy.*article|do not have access/i.test(body)]);
 };
 last=fingerprint();
 const observer=new MutationObserver(()=>{
  clearTimeout(timer);timer=setTimeout(()=>{
   const next=fingerprint();if(next===last)return;last=next;
   if(++notices>20){observer.disconnect();return;}
   chrome.runtime.sendMessage({action:"article-ready"}).catch(()=>{});
  },800);
 });
 observer.observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:["class","style","content","aria-label","href"]});
 setTimeout(()=>{observer.disconnect();clearTimeout(timer);},600000);
})();
