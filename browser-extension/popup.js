const status=document.getElementById("status");
async function send(message){const result=await chrome.runtime.sendMessage(message);if(result.error)throw Error(result.error);return result;}
send({action:"tasks"}).then(({tasks,last_failure})=>{document.getElementById("diagnostics").textContent=last_failure?"上次失败："+last_failure.summary:"";const select=document.getElementById("task");for(const task of tasks){const option=document.createElement("option");option.value=task.session_id;option.textContent=task.original_prompt;select.append(option);}status.textContent=tasks.length?"选择任务后开始；IEEE遇418先核对校园网直连，机构认证由本人完成。":"尚无待接续任务，先请agent创建任务。";}).catch(e=>status.textContent=e.message);
for(const action of ["start","auth","check","skip","ieee-direct","ieee-restore"]){document.getElementById(action).onclick=()=>send({action,session_id:document.getElementById("task").value}).then(result=>status.textContent=[result.route_note,result.title||result.status].filter(Boolean).join("；")).catch(e=>status.textContent=e.message);}

// Chrome不允许proxy作为optional_permissions；扩展更新时声明权限，按钮只启用设置。
for(const action of ["chrome-ieee-inspect","chrome-ieee-enable","chrome-ieee-restore"]){
 document.getElementById(action).onclick=()=>send({action}).then(result=>status.textContent=result.status).catch(error=>status.textContent=error.message);
}
