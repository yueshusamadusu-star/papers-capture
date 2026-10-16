"use strict";
// proxy是Chrome必需声明的权限；只有本人点设置按钮才修改配置。
globalThis.chromeIeeeRoute=(()=>{
 const KEY="chromeIeeeRoute",RULES=["ieee.org","*.ieee.org"];
 const clone=value=>JSON.parse(JSON.stringify(value));
 const sorted=value=>Array.isArray(value)?value.map(sorted):value&&typeof value==="object"?Object.fromEntries(Object.keys(value).sort().map(k=>[k,sorted(value[k])])):value;
 const fingerprint=value=>JSON.stringify(sorted(value));
 function normalize(value){
  if(value?.mode!=="fixed_servers"||!value.rules)throw Error("只支持保留已有固定代理；PAC或自动代理请在原软件设置IEEE直连");
  const rules=clone(value.rules);
  for(const key of ["singleProxy","proxyForHttp","proxyForHttps","proxyForFtp","fallbackProxy"]){
   if(!rules[key])continue;
   const server=rules[key],scheme=server.scheme||"http";
   if(!["http","https","quic","socks4","socks5"].includes(scheme)||typeof server.host!=="string"||!server.host||/[@/?#\s]/.test(server.host))throw Error("代理配置格式未知，未修改");
   const port=server.port??({http:80,https:443,quic:443,socks4:1080,socks5:1080}[scheme]);
   if(!Number.isInteger(port)||port<1||port>65535)throw Error("代理端口无效，未修改");
   rules[key]={...server,scheme,port};
  }
  if(!["singleProxy","proxyForHttp","proxyForHttps","proxyForFtp","fallbackProxy"].some(k=>rules[k]))throw Error("没有可保留的代理地址，未修改");
  if(rules.bypassList&&!Array.isArray(rules.bypassList))throw Error("代理例外格式未知，未修改");
  return {mode:"fixed_servers",rules};
 }
 async function permitted(){return Boolean(chrome.permissions&&await chrome.permissions.contains({permissions:["proxy"]}));}
 async function read(){
  const {[KEY]:saved}=await chrome.storage.local.get(KEY);
  if(!await permitted())return {status:"NEED_PROXY_PERMISSION",enabled:Boolean(saved?.enabled),mode:"unknown",level:"unknown",rule_present:false,configuration_verified:false,exit_verified:false};
  const current=await chrome.proxy.settings.get({incognito:false});
  let exact=false;
  try{exact=Boolean(saved?.enabled&&fingerprint(normalize(current.value))===fingerprint(saved.applied));}catch{}
  const bypass=current.value?.rules?.bypassList||[];
  const present=RULES.every(r=>bypass.some(v=>String(v).toLowerCase()===r));
  const verified=exact&&current.levelOfControl==="controlled_by_this_extension";
  return {status:verified?"BROWSER_RULE_CONFIGURED":"BROWSER_ROUTE_UNCONFIRMED",enabled:Boolean(saved?.enabled),mode:current.value?.mode||"unknown",level:current.levelOfControl||"unknown",rule_present:present,configuration_verified:verified,exit_verified:false};
 }
 async function enable(templateProvider){
  if(!await permitted())throw Error("请更新并确认Chrome代理权限；未修改设置");
  const current=await chrome.proxy.settings.get({incognito:false});
  const {[KEY]:saved}=await chrome.storage.local.get(KEY);
  if(saved?.enabled){const state=await read();if(state.configuration_verified)return state;throw Error("已有IEEE浏览器规则被改变，请先撤销再检查原代理；未覆盖");}
  if(!["controllable_by_this_extension","controlled_by_this_extension"].includes(current.levelOfControl))throw Error("Chrome代理由策略或另一个扩展控制；未覆盖，请在原控制方配置IEEE直连");
  if(current.levelOfControl==="controlled_by_this_extension")throw Error("当前扩展代理缺少对应记录，请先撤销本扩展的代理控制");
  if(current.value?.mode==="direct")return {status:"ALREADY_DIRECT",enabled:false,mode:"direct",configuration_verified:false,exit_verified:false};
  let base=current.value;
  if(base?.mode==="system"){
   const template=await templateProvider();
   if(template.status!=="MANUAL_LOOPBACK_PROXY_TEMPLATE")throw Error("系统不是可核对的本机手动代理；未修改，请在代理软件配置IEEE直连");
   base=template.config;
  }
  const applied=normalize(base),bypass=applied.rules.bypassList||[];
  applied.rules.bypassList=[...bypass,...RULES.filter(r=>!bypass.some(v=>String(v).toLowerCase()===r))];
  // 只记录本扩展设置；clear恢复下层最新配置，不把旧系统地址重新覆盖回去。
  await chrome.storage.local.set({[KEY]:{enabled:true,applied}});
  try{
   await chrome.proxy.settings.set({value:applied,scope:"regular"});
   const state=await read();
   if(!state.configuration_verified)throw Error("Chrome未采用本扩展的IEEE规则，已撤销；未确认出口");
   return state;
  }catch(error){await chrome.proxy.settings.clear({scope:"regular"});await chrome.storage.local.remove(KEY);throw error;}
 }
 async function restore(){
  if(!await permitted())throw Error("缺少Chrome代理权限；可停用扩展撤销其Chrome代理控制");
  await chrome.proxy.settings.clear({scope:"regular"});
  await chrome.storage.local.remove(KEY);
  return {status:"BROWSER_OVERRIDE_CLEARED",enabled:false,configuration_verified:false,exit_verified:false};
 }
 return {read,enable,restore};
})();
