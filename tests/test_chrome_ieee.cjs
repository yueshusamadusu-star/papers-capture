"use strict";
const vm=require("node:vm"),fs=require("node:fs"),path=require("node:path"),assert=require("node:assert/strict");
const script=fs.readFileSync(path.join(__dirname,"../browser-extension/chrome_ieee.js"),"utf8");
function fixture(value={mode:"system"},level="controllable_by_this_extension"){
 const storage={},calls=[];
 const state={value:structuredClone(value),level,permitted:true,rejectSet:false,ignoreSet:false};
 const chrome={permissions:{contains:async()=>state.permitted},storage:{local:{get:async()=>structuredClone(storage),set:async data=>Object.assign(storage,structuredClone(data)),remove:async key=>{delete storage[key];}}},
  proxy:{settings:{get:async()=>({value:structuredClone(state.value),levelOfControl:state.level}),
   set:async options=>{calls.push({set:structuredClone(options)});if(state.rejectSet)throw Error("fixture failure");if(!state.ignoreSet){state.value=structuredClone(options.value);state.level="controlled_by_this_extension";}},
   clear:async options=>{calls.push({clear:options});state.value={mode:"system"};state.level="controllable_by_this_extension";}}}};
 const sandbox={chrome};vm.createContext(sandbox);vm.runInContext(script,sandbox);
 const template={status:"MANUAL_LOOPBACK_PROXY_TEMPLATE",config:{mode:"fixed_servers",rules:{singleProxy:{scheme:"http",host:"127.0.0.1",port:8001},bypassList:["<local>","existing.edu"]}}};
 return {route:sandbox.chromeIeeeRoute,state,calls,storage,provider:async()=>structuredClone(template),template};
}
(async()=>{
 let count=0;
 const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,"../browser-extension/manifest.json"),"utf8"));
 assert(manifest.permissions.includes("proxy"));assert(!(manifest.optional_permissions||[]).includes("proxy"));count++;

 {
  const f=fixture();f.state.permitted=false;
  assert.equal((await f.route.read()).status,"NEED_PROXY_PERMISSION");await assert.rejects(f.route.enable(f.provider));assert.equal(f.calls.length,0);count++;
 }
 {
  const f=fixture();const result=await f.route.enable(f.provider);
  assert.equal(result.status,"BROWSER_RULE_CONFIGURED");assert.equal(result.configuration_verified,true);assert.equal(result.exit_verified,false);
  assert(!JSON.stringify(result).includes("127.0.0.1"));
  assert.deepEqual(f.state.value.rules.singleProxy,f.template.config.rules.singleProxy);
  assert.deepEqual(f.state.value.rules.bypassList,["<local>","existing.edu","ieee.org","*.ieee.org"]);
  const routes=host=>host==="ieee.org"||host.endsWith(".ieee.org")?"DIRECT":f.state.value.rules.singleProxy;
  for(const host of ["chatgpt.com","api.openai.com","ieee.org.evil.example","not-ieee.org"]){assert.deepEqual(routes(host),f.template.config.rules.singleProxy);}
  assert.equal(routes("ieeexplore.ieee.org"),"DIRECT");
  await f.route.enable(f.provider);assert.equal(f.calls.filter(c=>c.set).length,1);
  await f.route.restore();assert.equal(f.calls.filter(c=>c.clear).length,1);assert.equal(f.storage.chromeIeeeRoute,undefined);count++;
 }
 {
  const base={mode:"fixed_servers",rules:{proxyForHttp:{host:"127.0.0.1",port:8001},proxyForHttps:{scheme:"socks5",host:"localhost",port:8002},bypassList:["private.edu"]}};
  const f=fixture(base);await f.route.enable(async()=>{throw Error("must not use system template");});
  assert.equal(f.state.value.rules.proxyForHttps.port,8002);assert.equal(f.state.value.rules.proxyForHttps.scheme,"socks5");assert.equal(f.state.value.rules.proxyForHttp.scheme,"http");count++;
 }
 for(const level of ["not_controllable","controlled_by_other_extensions"]){
  const f=fixture({mode:"system"},level);await assert.rejects(f.route.enable(f.provider));assert.equal(f.calls.length,0);count++;
 }
 {
  const f=fixture({mode:"pac_script",pacScript:{url:"https://example.invalid/private-pac"}});
  await assert.rejects(f.route.enable(f.provider));assert.equal(f.calls.length,0);assert(!JSON.stringify(await f.route.read()).includes("private-pac"));count++;
 }
 {
  const f=fixture();await assert.rejects(f.route.enable(async()=>({status:"UNSUPPORTED_SYSTEM_PROXY"})));assert.equal(f.calls.length,0);count++;
 }
 for(const failure of ["rejectSet","ignoreSet"]){
  const f=fixture();f.state[failure]=true;await assert.rejects(f.route.enable(f.provider));assert.equal(f.calls.filter(c=>c.clear).length,1);assert.equal(f.storage.chromeIeeeRoute,undefined);count++;
 }
 {
  const f=fixture();await f.route.enable(f.provider);f.state.value.rules.singleProxy.port=9000;
  assert.equal((await f.route.read()).configuration_verified,false);await assert.rejects(f.route.enable(f.provider));assert.equal(f.calls.filter(c=>c.set).length,1);
  f.state.permitted=false;assert.equal((await f.route.read()).configuration_verified,false);count++;
 }
 {
  const f=fixture({mode:"direct"});assert.equal((await f.route.enable(f.provider)).status,"ALREADY_DIRECT");assert.equal(f.calls.length,0);count++;
 }
 console.log(JSON.stringify({status:"PASS",checks:count,note:"mocked Chrome API; not actual IEEE access or IP verification"}));
})().catch(error=>{console.error(error);process.exitCode=1;});
