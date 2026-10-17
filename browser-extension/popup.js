const status=document.getElementById("status");
function showPreferences(p){document.getElementById("save-directory").value=p.save_directory;}

async function send(message){const result=await chrome.runtime.sendMessage(message);if(result.error)throw Error(result.error);return result;}
send({action:"tasks"}).then(({tasks,last_failure,last_success})=>{document.getElementById("diagnostics").textContent=[last_success?"最近保存："+last_success.summary:"",last_failure?"历史失败提示："+last_failure.summary:""].filter(Boolean).join("；");const select=document.getElementById("task");for(const task of tasks){const option=document.createElement("option");option.value=task.session_id;option.textContent=task.original_prompt;select.append(option);}status.textContent=tasks.length?"选择任务后开始；IEEE遇418先核对校园网直连，机构认证由本人完成。":"尚无待接续任务，先请agent创建任务。";}).catch(e=>status.textContent=e.message);
for(const action of ["start","auth","check","skip","ieee-direct","ieee-restore"]){document.getElementById(action).onclick=()=>send({action,session_id:document.getElementById("task").value}).then(result=>status.textContent=[result.route_note,result.title||result.status].filter(Boolean).join("；")).catch(e=>status.textContent=e.message);}

// Chrome不允许proxy作为optional_permissions；扩展更新时声明权限，按钮只启用设置。
for(const action of ["chrome-ieee-inspect","chrome-ieee-enable","chrome-ieee-restore"]){
 document.getElementById(action).onclick=()=>send({action}).then(result=>status.textContent=result.status).catch(error=>status.textContent=error.message);
}

send({action:"preferences"}).then(showPreferences).catch(e=>document.getElementById("save-note").textContent=e.message);
document.getElementById("save-settings").onclick=()=>send({action:"save-preferences",save_directory:document.getElementById("save-directory").value}).then(p=>{showPreferences(p);document.getElementById("save-note").textContent="已保存。后续PDF直接以论文题名写入此目录，不弹另存为。";}).catch(e=>document.getElementById("save-note").textContent=e.message);
