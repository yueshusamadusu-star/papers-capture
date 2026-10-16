(() => {
 const meta=(n)=>document.querySelector('meta[name="'+n+'" i]')?.content || '';
 const body=(document.body?.innerText||'').slice(0,180000);
 const heading=(document.title+" "+Array.from(document.querySelectorAll('h1,h2')).map(e=>e.innerText||"").join(" ")).slice(0,4000);
 const ieeeNetworkError=location.hostname==="ieeexplore.ieee.org"&&/(?:\b(?:error|http|status(?:\s+code)?)\s*[:=-]?\s*418\b|\b418\b\s*(?:error|i.?m\s+a\s+teapot))/i.test(heading);
 const doi=meta('citation_doi') || meta('dc.Identifier') || meta('DC.Identifier.DOI');
 const links=Array.from(document.querySelectorAll('a[href]')).filter(a=>a.getClientRects().length);
 const pdf=links.filter(a=>/pdf|download.*full|full.*download|下载全文/i.test((a.innerText||'')+' '+a.getAttribute('aria-label')) && !/purchase|buy|sign.?in|log.?in|get access|购买/i.test(a.innerText||''));
 const auth=links.filter(a=>/institutional sign|access through.*institution|sign.?in|log.?in|机构登录|学校登录/i.test(a.innerText||''));
 const declared=meta('citation_pdf_url');
 const buttons=Array.from(document.querySelectorAll('button')).filter(a=>a.getClientRects().length && /(?:download|view|下载|查看).*pdf|^pdf$/i.test(a.innerText||'') && !/purchase|buy|购买/i.test(a.innerText||''));
 return {doi, ieee_network_error:ieeeNetworkError, pdf_links:[...(declared?[new URL(declared,location.href).href]:[]), ...pdf.map(a=>a.href)].slice(0,6), pdf_controls:pdf.length+buttons.length,
  viewer_pdf_links:Array.from(document.querySelectorAll('iframe[src],embed[src],object[data]')).map(e=>e.src||e.data||'').filter(u=>/pdf/i.test(u)).slice(0,4),
  auth_links:auth.map(a=>a.href).slice(0,4), password_form:Array.from(document.querySelectorAll('input[type=password]')).some(e=>e.getClientRects().length && getComputedStyle(e).visibility!=='hidden'),
  institution_recognized:/brought to you by|access provided by|provided by.*university|access through.*zhejiang|浙江大学图书馆/i.test(body),
  no_access:/purchase (?:this |the )?(?:article|pdf)|buy (?:article|pdf)|get access|do not have access|not included in.*subscription|access through another organization|无访问权限|未订购/i.test(body),
  challenge:/verify (?:you are|that you are) human|checking your browser|captcha|验证码|安全验证|access denied|unusual traffic/i.test(body)};
})();
