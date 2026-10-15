"""本人登录的专用浏览器任务。认证信息只由浏览器保管，不导出Cookie/口令。"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

from literature_helper import LiteratureHelper, HelperError, MAX_PDF, PdfResponseError, normalize_doi
from collection_workflow import CollectionManager, TERMINAL, atomic_json, now

PUBLISHERS = {"sciencedirect.com", "elsevier.com", "ieee.org", "scitepress.org", "mdpi.com", "mdpi-res.com", "arxiv.org", "ncbi.nlm.nih.gov", "springer.com", "springerlink.com", "nature.com", "wiley.com", "tandfonline.com", "acm.org", "cambridge.org", "oup.com", "sagepub.com", "iop.org", "aps.org", "aip.org"}


def publisher_host(host):
    return any(host == domain or host.endswith("." + domain) for domain in PUBLISHERS)


def public_url(url, test_origin=None):
    u = urlsplit(url)
    if test_origin and url.startswith(test_origin + "/"):
        return url
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.port not in (None, 443):
        raise HelperError("只允许公开HTTPS论文/认证页面")
    host = u.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".localhost", ".internal")):
        raise HelperError("拒绝本机与内部网址")
    import ipaddress
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise HelperError("拒绝内部IP网址")
    return url


def redacted_url(url):
    u = urlsplit(url)
    return urlunsplit((u.scheme, u.netloc, u.path if publisher_host(u.hostname or "") else "", "", ""))


def classify(snapshot, expected_doi):
    if snapshot.get("challenge"):
        return "CHALLENGE_REQUIRED"
    try:
        matched = normalize_doi(snapshot.get("doi", "")) == normalize_doi(expected_doi)
    except HelperError:
        matched = False
    if not matched:
        return "NEED_USER_AUTHENTICATION" if snapshot.get("password_form") else "PAPER_IDENTITY_UNKNOWN"
    if snapshot.get("pdf_links") or snapshot.get("pdf_controls"):
        return "PDF_CANDIDATE"
    if snapshot.get("password_form"):
        return "NEED_USER_AUTHENTICATION"
    if snapshot.get("institution_recognized") and snapshot.get("no_access"):
        return "NO_ACCESS"
    if snapshot.get("auth_links") or snapshot.get("no_access"):
        return "NEED_USER_AUTHENTICATION"
    return "ACCESS_UNKNOWN"


SNAPSHOT_SCRIPT = r"""() => {
 const meta=(n)=>document.querySelector('meta[name="'+n+'" i]')?.content || '';
 const body=(document.body?.innerText||'').slice(0,180000);
 const doi=meta('citation_doi') || meta('dc.Identifier') || meta('DC.Identifier.DOI');
 const links=Array.from(document.querySelectorAll('a[href]')).filter(a=>a.getClientRects().length);
 const pdf=links.filter(a=>/pdf|download.*full|full.*download|下载全文/i.test((a.innerText||'')+' '+a.getAttribute('aria-label')) && !/purchase|buy|sign.?in|log.?in|get access|购买/i.test(a.innerText||''));
 const auth=links.filter(a=>/institutional sign|access through.*institution|sign.?in|log.?in|机构登录|学校登录/i.test(a.innerText||''));
 const declared=meta('citation_pdf_url');
 const buttons=Array.from(document.querySelectorAll('button')).filter(a=>a.getClientRects().length && /(?:download|view|下载|查看).*pdf|^pdf$/i.test(a.innerText||'') && !/purchase|buy|购买/i.test(a.innerText||''));
 return {doi, pdf_links:[...(declared?[new URL(declared,location.href).href]:[]), ...pdf.map(a=>a.href)].slice(0,6), pdf_controls:pdf.length+buttons.length,
  viewer_pdf_links:Array.from(document.querySelectorAll('iframe[src],embed[src],object[data]')).map(e=>e.src||e.data||'').filter(u=>/pdf/i.test(u)).slice(0,4),
  auth_links:auth.map(a=>a.href).slice(0,4), password_form:Array.from(document.querySelectorAll('input[type=password]')).some(e=>e.getClientRects().length && getComputedStyle(e).visibility!=='hidden'),
  institution_recognized:/brought to you by|access provided by|provided by.*university|access through.*zhejiang|浙江大学图书馆/i.test(body),
  no_access:/purchase (?:this |the )?(?:article|pdf)|buy (?:article|pdf)|get access|do not have access|not included in.*subscription|access through another organization|无访问权限|未订购/i.test(body),
  challenge:/verify (?:you are|that you are) human|checking your browser|captcha|验证码|安全验证|access denied|unusual traffic/i.test(body)};
}"""


@contextmanager
def profile_lock(directory):
    directory.mkdir(parents=True, exist_ok=True)
    stream = (directory / "profile.lock").open("a+b")
    stream.seek(0)
    if stream.read(1) == b"":
        stream.write(b"0"); stream.flush()
    stream.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        stream.close()
        raise HelperError("BROWSER_BUSY")
    try:
        yield
    finally:
        stream.close()


class BrowserProcessor:
    def __init__(self, context, helper, test_origin=None):
        self.context, self.helper, self.test_origin = context, helper, test_origin

    def inspect(self, page, doi):
        host = urlsplit(page.url).hostname or ""
        if not publisher_host(host) and not (self.test_origin and page.url.startswith(self.test_origin + "/")):
            auth = host == "doi.org" or bool(re.search(r"login|sign.?in|auth|sso|shib|carsi|zju\.edu\.cn", page.url, re.I))
            return {"status": "NEED_USER_AUTHENTICATION" if auth else "UNSUPPORTED_PUBLISHER", "doi": "", "pdf_links": [], "note": "本人完成认证后回到原论文；其他出版商暂列待适配"}
        snapshot = page.evaluate(SNAPSHOT_SCRIPT)
        snapshot["status"] = classify(snapshot, doi)
        return snapshot

    def download(self, page, doi, url):
        from playwright.sync_api import Error as BrowserError
        url = public_url(urljoin(page.url, url), self.test_origin)
        host = urlsplit(url).hostname or ""
        if not publisher_host(host) and not (self.test_origin and url.startswith(self.test_origin + "/")):
            return {"status": "UNSUPPORTED_PDF_HOST"}
        for _ in range(4):
            # 请求在浏览器自己的上下文内完成；不读取、复制或返回Cookie。
            try:
                response = self.context.request.get(url, timeout=20000, max_redirects=0)
            except BrowserError:
                return {"status": "REQUEST_ERROR", "reason": "浏览器PDF请求未完成；不认定无订阅"}
            try:
                if response.status == 429:
                    return {"status": "RATE_LIMITED"}
                if response.status in {301, 302, 303, 307, 308}:
                    url = public_url(urljoin(url, response.headers.get("location", "")), self.test_origin)
                    if not publisher_host(urlsplit(url).hostname or "") and not (self.test_origin and url.startswith(self.test_origin + "/")):
                        return {"status": "NEED_USER_AUTHENTICATION"}
                    continue
                if response.status in {401, 403}:
                    return {"status": "NEED_USER_AUTHENTICATION"}
                if response.status != 200:
                    return {"status": "PDF_UNAVAILABLE", "http_status": response.status}
                length = response.headers.get("content-length", "0") or "0"
                if not length.isdigit():
                    return {"status": "PDF_RESPONSE_INVALID"}
                if int(length) > MAX_PDF:
                    return {"status": "PDF_TOO_LARGE"}
                body = response.body()
                try:
                    saved = self.helper._save_pdf(body, doi, {"origin": "user_authenticated_browser", "url": redacted_url(url),
                                "paper_identity": "DOI_MATCHED_ON_PUBLISHER_PAGE", "entitlement_evidence": "THIS_PDF_RETURNED_HTTP_200_AND_VALID_PDF",
                                "note": "不由学校名称推断订阅范围；只证明当前会话取得本篇PDF，URL查询参数已移除"})
                    return saved
                except PdfResponseError:
                    return {"status": "NEED_USER_AUTHENTICATION", "reason": "响应不是完整PDF，可能为登录/验证页"}
            finally:
                response.dispose()
        return {"status": "ACCESS_UNKNOWN", "reason": "重定向超过上限"}

    def click_pdf(self, page, doi):
        """只点当前已匹配论文的可见PDF控件；不点击购买或认证提交。"""
        from playwright.sync_api import Error as BrowserError
        name = re.compile(r"^(?:view |download |full.text |查看|下载)?\s*pdf(?:\b|$)", re.I)
        control = page.get_by_role("link", name=name).or_(page.get_by_role("button", name=name)).first
        if control.count() == 0:
            return {"status": "ACCESS_UNKNOWN"}
        existing = list(self.context.pages)
        try:
            with page.expect_download(timeout=7000) as event:
                control.click(timeout=5000)
            download = event.value
            if download.failure():
                return {"status": "ACCESS_UNKNOWN"}
            path = Path(download.path())
            with path.open("rb") as f:
                body = f.read(MAX_PDF+1)
            return self.helper._save_pdf(body, doi, {"origin": "user_browser_download_event", "url": redacted_url(download.url),
                         "paper_identity": "DOI_MATCHED_BEFORE_PDF_CLICK", "entitlement_evidence": "BROWSER_DOWNLOAD_EVENT_AND_VALID_PDF"})
        except (BrowserError, PdfResponseError):
            # 部分平台打开内嵌PDF而不触发下载事件；只查本篇控件打开后的公开PDF框架。
            for tab in [page] + [p for p in self.context.pages if p not in existing]:
                if tab.is_closed():
                    continue
                for frame in tab.locator('iframe[src], embed[src], object[data]').all()[:3]:
                    url = frame.get_attribute("src") or frame.get_attribute("data") or ""
                    if url and "pdf" in url.lower():
                        try:
                            result = self.download(tab, doi, url)
                            if result["status"] in {"SAVED", "ALREADY_EXISTS", "RATE_LIMITED"}:
                                return result
                        except HelperError:
                            continue
            return {"status": "ACCESS_UNKNOWN"}


def run_browser(manager, state, context, timeout_seconds=900, test_origin=None):
    """先检查全部候选，再等待本人认证；一篇验证/超时不挡其他论文。"""
    from playwright.sync_api import Error as BrowserError
    processor = BrowserProcessor(context, manager.helper, test_origin)
    dashboard = context.new_page()
    dashboard.goto((manager.directory(state["session_id"]) / "index.html").as_uri())
    pages, attempts = {}, {}
    for index, paper in enumerate(state["papers"]):
        if paper["status"] in TERMINAL:
            continue
        state["status"], state["current_index"] = "BROWSER_CHECKING", index
        manager.save(state)
        page = context.new_page()
        pages[index] = page
        attempts[index] = {"signature": None, "count": 0, "institution": False, "resumes": 0}
        try:
            page.goto(public_url(paper["article_url"], test_origin), wait_until="domcontentloaded", timeout=30000)
        except BrowserError:
            paper["status"] = "ACCESS_UNKNOWN"
            paper["reason"] = "论文页面尚未加载完成，不认定无订阅"
    deadline = time.monotonic()+timeout_seconds
    while time.monotonic() < deadline:
        command = manager.directory(state["session_id"]) / "command.json"
        if command.exists():
            action = json.loads(command.read_text(encoding="utf-8"))
            command.unlink(missing_ok=True)
            if action["action"] == "close":
                state["status"] = "CLOSED"; manager.save(state); return
            index = state.get("current_index")
            if index in attempts:
                if action["action"] == "skip":
                    state["papers"][index]["status"] = "SKIPPED_BY_USER"
                elif action["action"] == "resume":
                    stats = attempts[index]
                    stats["resumes"] += 1
                    if stats["resumes"] <= 2:
                        stats["signature"], stats["count"] = None, 0
                    deadline = time.monotonic()+timeout_seconds
        pending = [i for i,p in enumerate(state["papers"]) if p["status"] not in TERMINAL]
        if not pending:
            state["status"], state["current_index"] = "FINISHED", None
            manager.save(state); return
        for index in pending:
            paper, page, stats = state["papers"][index], pages[index], attempts[index]
            if page.is_closed():
                paper["status"] = "ACCESS_UNKNOWN"
                paper["reason"] = "论文标签已关闭；可跳过或另立任务，不认定无订阅"
                continue
            try:
                snapshot = processor.inspect(page, paper["doi"])
                for candidate in reversed(context.pages):
                    if candidate != page and candidate != dashboard and not candidate.is_closed():
                        other = processor.inspect(candidate, paper["doi"])
                        if other["status"] in {"PDF_CANDIDATE", "NO_ACCESS"}:
                            page, snapshot = candidate, other
                            pages[index] = page
                            break
                observed = snapshot["status"]
                paper["browser_evidence"] = {"page": redacted_url(page.url), "identity_matched": observed in {"PDF_CANDIDATE", "NO_ACCESS"},
                    "institution_recognized": bool(snapshot.get("institution_recognized")), "observed_state": observed}
                if observed == "NO_ACCESS":
                    paper["status"] = "SKIPPED_NO_ACCESS"
                    paper["reason"] = "本篇DOI匹配，页面识别机构且仅提供购买/重新获取权限；保留元数据并退避"
                    continue
                if observed == "UNSUPPORTED_PUBLISHER":
                    paper["status"] = observed
                    continue
                if observed == "PDF_CANDIDATE":
                    if snapshot.get("institution_recognized") and not stats["institution"]:
                        stats["institution"], stats["count"] = True, 0
                    signature = (page.url, bool(snapshot.get("institution_recognized")), tuple(snapshot["pdf_links"]))
                    if signature != stats["signature"] and stats["count"] < 3:
                        stats["signature"] = signature
                        results = []
                        for pdf in snapshot["pdf_links"][:max(0,2-stats["count"])]:
                            stats["count"] += 1
                            result = processor.download(page, paper["doi"], pdf)
                            results.append(result)
                            if result["status"] in {"SAVED", "ALREADY_EXISTS", "RATE_LIMITED"}:
                                break
                        if (not results or results[-1]["status"] not in {"SAVED", "ALREADY_EXISTS", "RATE_LIMITED"}) and stats["count"] < 3 and snapshot.get("pdf_controls"):
                            stats["count"] += 1
                            results.append(processor.click_pdf(page, paper["doi"]))
                        if results:
                            result = results[-1]
                            if result["status"] in {"SAVED", "ALREADY_EXISTS"}:
                                paper["status"], paper["file"] = result["status"], result
                                manager.save(state)
                                continue
                            if result["status"] == "RATE_LIMITED":
                                paper["status"], state["status"] = "RATE_LIMITED", "STOPPED_RATE_LIMIT"
                                manager.save(state); return
                            observed = result["status"]
                paper["status"] = observed if observed in {"NEED_USER_AUTHENTICATION", "CHALLENGE_REQUIRED"} else "ACCESS_UNKNOWN"
            except BrowserError:
                paper["status"] = "ACCESS_UNKNOWN"
                paper["reason"] = "页面跳转或请求未完成；继续处理其他论文"
            except HelperError:
                paper["status"] = "ERROR"
                paper["reason"] = "候选地址/文件校验不通过，保留原文件并继续其他论文"
        pending = [i for i,p in enumerate(state["papers"]) if p["status"] not in TERMINAL]
        if not pending:
            state["status"], state["current_index"] = "FINISHED", None
            manager.save(state); return
        # 优先提示可登录的页面，验证循环页保留待处理，不使整个批次停摆。
        index = next((i for i in pending if state["papers"][i]["status"] == "NEED_USER_AUTHENTICATION"), pending[0])
        state["current_index"], state["status"] = index, state["papers"][index]["status"]
        manager.save(state)
        live = next((p for p in context.pages if not p.is_closed()), None)
        if live is None:
            break
        live.wait_for_timeout(3000)
    state["status"] = "TIMED_OUT"
    manager.save(state)


def worker(manager, sid):
    state = manager.load(sid)
    try:
        atomic_json(manager.directory(sid) / "started.json", {"pid": os.getpid(), "started_at": now()})
        if not manager.run_public(state):
            return
        if all(p["status"] in TERMINAL for p in state["papers"]):
            state["status"] = "FINISHED"; manager.save(state); return
        if not state["use_browser"]:
            state["status"] = "NEED_BROWSER"; manager.save(state); return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            state["status"] = "BROWSER_UNAVAILABLE"
            state["reason"] = "安装 browser 可选依赖后再resume"
            manager.save(state); return
        with profile_lock(manager.browser_dir):
            with sync_playwright() as pw:
                context = pw.chromium.launch_persistent_context(str(manager.browser_dir / "profile"),
                    channel=os.environ.get("LIT_BROWSER_CHANNEL", "msedge" if os.name == "nt" else "chromium"),
                    headless=False, accept_downloads=True, timeout=30000)
                try:
                    run_browser(manager, state, context)
                finally:
                    context.close()
    except Exception as exc:
        state["status"] = "BROWSER_BUSY" if str(exc) == "BROWSER_BUSY" else "WORKER_ERROR"
        state["reason"] = "浏览器任务未完成；没有据此认定无权限，可resume重试。错误类型：" + type(exc).__name__
        manager.save(state)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--session", required=True); p.add_argument("--output", required=True); p.add_argument("--browser-dir", required=True)
    args = p.parse_args()
    manager = CollectionManager(LiteratureHelper(args.output), args.browser_dir)
    worker(manager, args.session)
