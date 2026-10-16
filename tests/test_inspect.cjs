"use strict";
const vm=require("node:vm"),fs=require("node:fs"),assert=require("node:assert/strict"),path=require("node:path");
const script=fs.readFileSync(path.join(__dirname,"../browser-extension/inspect.js"),"utf8");
function inspect(title,body,host="ieeexplore.ieee.org"){
 const sandbox={URL,location:{hostname:host,href:"https://"+host+"/document/9792260"},getComputedStyle:()=>({visibility:"visible"}),
 document:{title,body:{innerText:body},querySelector:()=>null,querySelectorAll:q=>q==="h1,h2"?[{innerText:title}]:[]}};
 return vm.runInNewContext(script,sandbox);
}
assert.equal(inspect("Error 418","Request blocked").ieee_network_error,true);
assert.equal(inspect("Error Estimation With 418 Samples","References mention Error 418").ieee_network_error,false);
assert.equal(inspect("Error 418","Request blocked","www.sciencedirect.com").ieee_network_error,false);
console.log(JSON.stringify({status:"PASS",checks:["ieee_418_heading_detected","article_body_not_error_page","other_publishers_not_misclassified"]}));
