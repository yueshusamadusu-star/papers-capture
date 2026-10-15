if(location.origin==="http://127.0.0.1:8766"&&location.pathname==="/pair"){
 const token=location.hash.slice(1);
 if(token)chrome.runtime.sendMessage({action:"pair",token}).then(result=>{document.getElementById("status").textContent=result.error||"已连接本机文献工具。现在点浏览器工具栏的papers-capture图标，选择任务并开始。";if(!result.error)history.replaceState(null,"","/pair");});
}
