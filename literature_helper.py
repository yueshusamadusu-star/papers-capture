"""公开 API 文献助手：不接收校园密码；认证收集流程见collection_workflow。"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
import uuid
import webbrowser
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

VERSION = "0.5.0"
MAX_PDF = 25 * 1024 * 1024
MAX_JSON = 2 * 1024 * 1024
# 首版仅自动下载这些公共来源；其余 OA 链接返回人工处理。
PDF_HOSTS = frozenset({"arxiv.org", "export.arxiv.org", "www.mdpi.com",
                       "mdpi-res.com", "pmc.ncbi.nlm.nih.gov",
                       "www.scitepress.org", "scitepress.org"})
API_HOSTS = frozenset({"api.crossref.org", "api.unpaywall.org"})


class HelperError(ValueError):
    """可向用户展示的错误；不回显带邮箱等参数的请求地址。"""


class RateLimitError(HelperError):
    """来源限流；整个收集队列停止，不换来源规避。"""


class CandidateUnavailable(HelperError):
    """公开候选返回404/410，可检查下一个已声明的公开位置。"""


class PdfResponseError(HelperError):
    """候选不是完整PDF，不能作为已下载全文。"""


class AccessPageRequired(HelperError):
    """HTTP 401/403：需要本人核对，不断言一定是未登录。"""


def checked_url(url: str, hosts: frozenset[str]) -> str:
    p = urlsplit(url)
    try:
        port = p.port
    except ValueError as exc:
        raise HelperError("请求地址端口无效") from exc
    if (p.scheme != "https" or p.hostname not in hosts or port not in (None, 443)
            or p.username is not None or p.password is not None or p.fragment):
        raise HelperError("仅允许已支持来源的 HTTPS 地址；其他来源请手动访问")
    return url


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PublicClient:
    """串行、间隔至少3.1秒；限流即停止，不循环重试或绕过验证。"""

    def __init__(self):
        self.opener = build_opener(NoRedirect())
        self.lock = threading.Lock()
        self.last_request = 0.0

    def get(self, url: str, hosts: frozenset[str], max_bytes: int) -> tuple[bytes, str]:
        with self.lock:
            deadline = time.monotonic() + 60
            for _ in range(5):
                checked_url(url, hosts)
                delay = 3.1 - (time.monotonic() - self.last_request)
                if delay > 0:
                    time.sleep(delay)
                self.last_request = time.monotonic()
                remaining = deadline - self.last_request
                if remaining <= 0:
                    raise HelperError("请求超过60秒，停止连接")
                request = Request(url, headers={"User-Agent": "ZJULiteratureHelper/" + VERSION,
                                                "Accept": "application/json, application/pdf"})
                try:
                    response = self.opener.open(request, timeout=min(25, remaining))
                except HTTPError as exc:
                    with closing(exc):
                        if exc.code in (301, 302, 303, 307, 308):
                            location = exc.headers.get("Location")
                            if not location:
                                raise HelperError("重定向缺少地址") from None
                            url = urljoin(url, location)
                            continue
                        if exc.code in (401, 403):
                            raise AccessPageRequired(f"来源返回 HTTP {exc.code}，请在官方页面核对权限或网站限制") from None
                        if exc.code == 429:
                            raise RateLimitError("来源限流：请稍后重试，并遵守服务方 Retry-After 提示") from None
                        if exc.code in (404, 410):
                            raise CandidateUnavailable(f"公开候选返回 HTTP {exc.code}") from None
                        raise HelperError(f"来源返回 HTTP {exc.code}；请人工检查访问权限或链接") from None
                except (URLError, TimeoutError, OSError):
                    raise HelperError("网络连接失败或超时；未重试、未使用校园凭据") from None
                with closing(response):
                    checked_url(response.geturl(), hosts)
                    chunks, size = [], 0
                    try:
                        while True:
                            if time.monotonic() > deadline:
                                raise HelperError("请求超过60秒，停止读取")
                            chunk = response.read(min(65536, max_bytes + 1 - size))
                            if not chunk:
                                break
                            chunks.append(chunk)
                            size += len(chunk)
                            if size > max_bytes:
                                raise HelperError("响应超过允许大小")
                    except (TimeoutError, OSError):
                        raise HelperError("读取响应失败；没有保存不完整全文") from None
                    return b"".join(chunks), response.geturl()
            raise HelperError("重定向次数过多，转人工访问")

    def json(self, url: str) -> dict:
        body, _ = self.get(url, API_HOSTS, MAX_JSON)
        try:
            data = json.loads(body)
        except (ValueError, UnicodeError):
            raise HelperError("API 未返回有效 JSON") from None
        if not isinstance(data, dict):
            raise HelperError("API 返回结构无效")
        return data


def normalize_doi(value: str) -> str:
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value.strip(), flags=re.I)
    value = re.sub(r"^doi:\s*", "", value, flags=re.I)
    if not re.fullmatch(r"10\.\d{4,9}/\S+", value) or len(value) > 256:
        raise HelperError("请输入 DOI，例如 10.3390/metrology5040071")
    return value.lower()


def summarize(work: dict) -> dict:
    parts = (work.get("published") or {}).get("date-parts") or [[]]
    primary = ((work.get("resource") or {}).get("primary") or {}).get("URL", "")
    parsed = urlsplit(primary)
    canonical = (parsed.scheme + "://" + parsed.netloc + parsed.path
                 if parsed.scheme == "https" and parsed.hostname == "ieeexplore.ieee.org"
                 and not parsed.username and not parsed.password
                 and re.fullmatch(r"/(?:abstract/)?document/[0-9]+/?", parsed.path) else None)
    return {"doi": work.get("DOI"), **({"publisher_article_url": canonical} if canonical else {}),
            "title": (work.get("title") or [""])[0],
            "authors": [" ".join(filter(None, [a.get("given"), a.get("family"), a.get("name")]))
                        for a in work.get("author", [])],
            "year": parts[0][0] if parts and parts[0] else None,
            "venue": (work.get("container-title") or [""])[0],
            "landing_url": work.get("URL"), "source": "Crossref"}


class LiteratureHelper:
    def __init__(self, output_dir: str | Path | None = None,
                 inbox_dir: str | Path | None = None, client=None):
        self.output = Path(output_dir or os.environ.get("LIT_OUTPUT_DIR") or
                           Path(__file__).parent / "downloads").resolve()
        self.inbox = Path(inbox_dir or os.environ.get("LIT_INBOX_DIR") or
                          Path(__file__).parent / "inbox").resolve()
        self.client = client or PublicClient()
        self.save_lock = threading.Lock()

    def search(self, query: str, limit: int = 5) -> dict:
        if not query.strip() or len(query) > 500 or not 1 <= limit <= 10:
            raise HelperError("检索词长度1–500，返回篇数1–10")
        url = "https://api.crossref.org/works?" + urlencode({"query.bibliographic": query, "rows": limit})
        message = self.client.json(url).get("message") or {}
        return {"status": "METADATA_ONLY", "query": query,
                "papers": [summarize(w) for w in message.get("items", [])],
                "note": "检索结果须核对相关性；元数据不等于全文或创新排重完成"}

    def reading_list(self, query: str, limit: int = 5, open_browser: bool = False,
                     collect_fulltext: bool = False) -> dict:
        """检索清单；明确选择collect_fulltext时串行尝试全文，不弹逐篇认证页。"""
        metadata = self.search(query, limit)
        if collect_fulltext:
            seen, stopped = set(), False
            for paper in metadata["papers"]:
                if stopped:
                    paper["collection"] = {"status": "NOT_ATTEMPTED", "reason": "此前来源限流，队列已停止"}
                    continue
                try:
                    doi = normalize_doi(paper.get("doi") or "")
                    if doi in seen:
                        paper["collection"] = {"status": "DUPLICATE_SKIPPED"}
                        continue
                    seen.add(doi)
                    paper["collection"] = self.collect(doi, open_browser=False)
                except RateLimitError as exc:
                    paper["collection"] = {"status": "RATE_LIMITED", "reason": str(exc)}
                    stopped = True
                except (HelperError, OSError) as exc:
                    paper["collection"] = {"status": "ERROR", "reason": str(exc)}
            metadata["pipeline_status"] = "STOPPED_RATE_LIMIT" if stopped else "FINISHED"
            states = [p["collection"]["status"] for p in metadata["papers"]]
            metadata["collection_summary"] = {state: states.count(state) for state in sorted(set(states))}
        report_dir = self.output / "reading-lists" / uuid.uuid4().hex
        report_dir.mkdir(parents=True, exist_ok=False)
        page, manifest = report_dir / "index.html", report_dir / "results.json"
        with manifest.open("x", encoding="utf-8") as f:
            json.dump({"tool_version": VERSION, "saved_at": datetime.now(timezone.utc).isoformat(),
                       "authentication": "UNKNOWN", **metadata}, f, ensure_ascii=False, indent=2)
            f.write("\n")
        with page.open("x", encoding="utf-8") as f:
            f.write(render_reading_list(metadata))
        result = {"status": "READING_LIST_READY", "path": str(page), "manifest": str(manifest),
                  "papers": len(metadata["papers"]), "query": query,
                  "mode": "COLLECT_FULLTEXT" if collect_fulltext else "METADATA_ONLY",
                  "authentication": "UNKNOWN", "subscription_access": "UNKNOWN"}
        if collect_fulltext:
            result.update({k: metadata[k] for k in ("pipeline_status", "collection_summary")})
        if open_browser:
            result["browser"] = request_browser(page.as_uri())
        return result

    def collect(self, identifier: str, open_browser: bool = True, route: str = "article",
                access_state: str = "unknown") -> dict:
        """公开全文优先；用户报告未订阅后，不再弹相同机构登录入口。"""
        if route not in ("article", "carsi", "webvpn"):
            raise HelperError("访问路线应为 article、carsi 或 webvpn")
        if access_state not in ("unknown", "not_subscribed"):
            raise HelperError("access_state应为unknown或not_subscribed；后者只表示用户报告")
        if identifier.startswith("arxiv:"):
            return self.download(identifier)
        doi = normalize_doi(identifier)
        try:
            acquisition = self.download(doi)
        except AccessPageRequired as exc:
            acquisition = {"status": "ACCESS_CHECK_REQUIRED", "reason": str(exc)}
        if acquisition["status"] in ("SAVED", "ALREADY_EXISTS"):
            return acquisition
        fallback = {"library_document_delivery": "https://libweb.zju.edu.cn/55971/list.htm",
                    "doi_search": "https://scholar.google.com/scholar?" + urlencode({"q": '"' + doi + '"'}),
                    "note": "同一论文的开放版本优先；人工文献传递或向作者索取不自动执行。其他论文只能标为替代阅读，不能冒充本篇全文"}
        result = {"status": "MANUAL_REQUIRED" if access_state == "not_subscribed" else "USER_BROWSER_ACTION_REQUIRED",
                  "doi": doi, "open_access_result": acquisition, "fallback": fallback,
                  "authentication": "UNKNOWN",
                  "subscription_access": "NOT_SUBSCRIBED_USER_REPORTED" if access_state == "not_subscribed" else "UNKNOWN"}
        if doi.startswith("10.5220/"):
            result["publisher_account"] = {"type": "FREE_PERSONAL_ACCOUNT_IF_REQUIRED",
                                            "login_url": "https://www.scitepress.org/Login.aspx",
                                            "note": "SciTePress提供免费个人账号；无需把它解释成学校机构登录"}
        if access_state == "not_subscribed":
            result["note"] = "已记录用户报告该篇未订阅；公开检查未取得可保存PDF，不再打开机构认证页。缺少邮箱等查询前提不等于已穷尽所有开放版本"
        else:
            result["access"] = open_access_page(doi, route, open_browser)
            result["note"] = "公开检查未取得可保存PDF；官网可能需要个人账号、机构认证或其他处理，不能一概解释成未登录"
        return result

    def lookup(self, doi: str) -> dict:
        doi = normalize_doi(doi)
        url = "https://api.crossref.org/works/" + quote(doi, safe="")
        work = self.client.json(url).get("message")
        if not isinstance(work, dict):
            raise HelperError("未取得该 DOI 的 Crossref 记录")
        if normalize_doi(work.get("DOI") or "") != doi:
            raise HelperError("Crossref返回了其他DOI，停止建立论文身份对应")
        return {"status": "METADATA_ONLY", "paper": summarize(work)}

    def locate_oa(self, doi: str) -> dict:
        doi = normalize_doi(doi)
        email = os.environ.get("UNPAYWALL_EMAIL", "").strip()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            return {"status": "NEED_CONTACT_EMAIL", "doi": doi, "locations": [],
                    "note": "Unpaywall查询尚未执行；可在本机UNPAYWALL_EMAIL配置普通联系邮箱，不是校园密码"}
        url = "https://api.unpaywall.org/v2/" + quote(doi, safe="") + "?" + urlencode({"email": email})
        try:
            record = self.client.json(url)
        except CandidateUnavailable:
            return {"status": "MANUAL_REQUIRED", "doi": doi, "locations": [], "source": "Unpaywall", "note": "该DOI暂无记录"}
        if record.get("doi") and normalize_doi(record["doi"]) != doi:
            raise HelperError("Unpaywall返回了其他DOI，停止保存")
        locations, seen = [], set()
        for loc in [record.get("best_oa_location"), *(record.get("oa_locations") or [])]:
            if not isinstance(loc, dict):
                continue
            pdf = loc.get("url_for_pdf")
            if not isinstance(pdf, str) or pdf in seen:
                continue
            seen.add(pdf)
            try:
                checked_url(pdf, PDF_HOSTS)
                supported = True
            except (HelperError, ValueError):
                supported = False
            locations.append({"pdf_url": pdf, "landing_url": loc.get("url_for_landing_page"),
                              "license": loc.get("license"), "version": loc.get("version"),
                              "automatic_download_supported": supported, "source": "Unpaywall"})
        preferred = next((loc for loc in locations if loc["automatic_download_supported"]), locations[0] if locations else {})
        return {"status": "OA_FOUND" if locations else "MANUAL_REQUIRED", "doi": doi,
                "pdf_url": preferred.get("pdf_url"), "landing_url": preferred.get("landing_url"),
                "license": preferred.get("license"), "version": preferred.get("version"),
                "automatic_download_supported": bool(preferred.get("automatic_download_supported")),
                "locations": locations, "source": "Unpaywall",
                "note": "只检查当前oa_locations，不用尚在禁运中的位置；不将全文许可与再分发许可混同"}

    def _crossref_candidates(self, doi: str) -> list[dict]:
        """不用邮箱也核对公开元数据；TDM链接不自动当作开放全文。"""
        record = self.client.json("https://api.crossref.org/works/" + quote(doi, safe=""))
        work = record.get("message")
        if not isinstance(work, dict):
            return []
        if not work.get("DOI") or normalize_doi(work["DOI"]) != doi:
            raise HelperError("Crossref返回了其他DOI，停止保存")
        candidates = []
        if doi.startswith("10.5220/"):
            # SciTePress公开PDF路径约定：出版年 / DOI前8位去前导零 / 论文号.pdf。
            # 只支持16位数字后缀及可核对的官方资源域；不枚举账号或受限URL。
            suffix = doi.split("/", 1)[1]
            primary = ((work.get("resource") or {}).get("primary") or {}).get("URL", "")
            dates = (work.get("published") or {}).get("date-parts") or [[]]
            year = dates[0][0] if dates and dates[0] else None
            if (re.fullmatch(r"[0-9]{16}", suffix) and urlsplit(primary).hostname in {"www.scitepress.org", "scitepress.org"}
                    and isinstance(year, int) and 1900 <= year <= datetime.now(timezone.utc).year):
                paper_id = str(int(suffix[:8]))
                candidates.append({"pdf_url": f"https://www.scitepress.org/Papers/{year}/{paper_id}/{paper_id}.pdf",
                                   "source": "SciTePress", "landing_url": article_url(doi),
                                   "candidate_basis": "DOI与Crossref出版年对应的公开路径约定，HTTP/PDF实际检查后才记已保存",
                                   "license": "公开可读；再分发许可未核验", "version": "publishedVersion"})
        now = datetime.now(timezone.utc).date()
        licenses = {}
        for item in work.get("license") or []:
            if not isinstance(item, dict):
                continue
            u = urlsplit(item.get("URL") or "")
            if u.hostname != "creativecommons.org" or not u.path.startswith(("/licenses/", "/publicdomain/")):
                continue
            version = item.get("content-version")
            start = (item.get("start") or {}).get("date-parts") or []
            try:
                parts = start[0]
                if datetime(*parts[:3], tzinfo=timezone.utc).date() > now:
                    continue
            except (ValueError, TypeError, IndexError):
                continue
            if version in ("vor", "am"):
                licenses[version] = item["URL"]
        for item in work.get("link") or []:
            if not isinstance(item, dict) or item.get("content-type") != "application/pdf":
                continue
            version = item.get("content-version")
            if version not in licenses:
                continue
            pdf = item.get("URL") or ""
            try:
                checked_url(pdf, PDF_HOSTS)
            except (HelperError, ValueError):
                continue
            candidates.append({"pdf_url": pdf, "source": "Crossref_CC_declared",
                               "license": licenses[version], "version": version,
                               "landing_url": article_url(doi)})
        return candidates

    def download(self, identifier: str) -> dict:
        if identifier.startswith("arxiv:"):
            aid = identifier[6:].strip()
            if not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v[1-9]\d*)?", aid):
                raise HelperError("arXiv编号无效，例如 arxiv:1706.03762")
            url = "https://arxiv.org/pdf/" + aid
            body, final_url = self.client.get(url, PDF_HOSTS, MAX_PDF)
            return self._save_pdf(body, identifier, {"origin": "public_oa", "url": url, "final_url": final_url,
                        "evidence": {"provider": "arXiv", "landing_url": "https://arxiv.org/abs/" + aid,
                                     "license": "逐篇许可见arXiv；不再分发"}})
        doi = normalize_doi(identifier)
        discovery = self.locate_oa(doi)
        candidates = [loc for loc in discovery.get("locations", []) if loc.get("automatic_download_supported")]
        checks = [{"source": "Unpaywall", "status": discovery["status"]}]
        attempts, seen = [], set()
        crossref_done = False
        while True:
            for loc in candidates:
                url = loc["pdf_url"]
                if url in seen or len(attempts) >= 3:
                    continue
                seen.add(url)
                attempt = {"source": loc["source"], "url": url}
                try:
                    body, final_url = self.client.get(url, PDF_HOSTS, MAX_PDF)
                    saved = self._save_pdf(body, doi, {"origin": "public_oa", "url": url,
                                           "final_url": final_url, "evidence": loc, "checks": checks})
                except (CandidateUnavailable, AccessPageRequired, PdfResponseError) as exc:
                    attempt.update({"status": "CANDIDATE_UNAVAILABLE", "reason": str(exc)})
                    attempts.append(attempt)
                    continue
                attempts.append({**attempt, "status": saved["status"]})
                return {**saved, "doi": doi, "attempts": attempts}
            if crossref_done or len(attempts) >= 3:
                break
            try:
                candidates = self._crossref_candidates(doi)
                checks.append({"source": "Crossref_public", "status": "CHECKED", "candidates": len(candidates)})
            except (CandidateUnavailable, AccessPageRequired) as exc:
                candidates = []
                checks.append({"source": "Crossref_public", "status": "UNAVAILABLE", "reason": str(exc)})
            crossref_done = True
        return {**discovery, "status": "FULLTEXT_NOT_SAVED", "doi": doi,
                "checks": checks, "attempts": attempts,
                "note": "仅现有公开路线未取得PDF；NEED_CONTACT_EMAIL表示开放版本查询未执行，不是没有开放版本。机构订阅仍未知"}

    def import_pdf(self, filename: str, identifier: str = "manual") -> dict:
        # MCP 只能读取用户指定收件箱内的单个文件，不接受任意本机路径。
        if Path(filename).name != filename or "/" in filename or "\\" in filename or ":" in filename:
            raise HelperError("仅填写收件箱内的 PDF 文件名")
        source = (self.inbox / filename).resolve()
        if source.parent != self.inbox or source.suffix.lower() != ".pdf" or not source.is_file():
            raise HelperError("收件箱中没有该 PDF，或文件跳出了收件箱")
        with source.open("rb") as f:
            body = f.read(MAX_PDF + 1)
        return self._save_pdf(body, identifier, {"origin": "manual_import", "filename": filename,
                                               "note": "用户自行取得；工具未认证许可或论文身份"})

    def _save_pdf(self, body: bytes, identifier: str, provenance: dict) -> dict:
        if len(body) > MAX_PDF:
            raise HelperError("PDF 超过25MB限制")
        if not body.startswith(b"%PDF-") or b"%%EOF" not in body[-2048:]:
            raise PdfResponseError("没有取得完整PDF（可能是登录/验证码页面），未保存")
        digest = hashlib.sha256(body).hexdigest()
        name = digest + ".pdf"
        with self.save_lock:
            self.output.mkdir(parents=True, exist_ok=True)
            target = self.output / name
            manifest = self.output / (digest + ".json")
            if target.exists() or manifest.exists():
                if (target.is_file() and not target.is_symlink() and manifest.is_file()
                        and not manifest.is_symlink() and hashlib.sha256(target.read_bytes()).hexdigest() == digest):
                    return {"status": "ALREADY_EXISTS", "path": str(target), "sha256": digest}
                raise HelperError("目标工件已存在但不完整或内容不一致，保留原文件供人工检查")
            entry = {"tool_version": VERSION, "identifier": identifier, "sha256": digest,
                     "bytes": len(body), "saved_at": datetime.now(timezone.utc).isoformat(),
                     "provenance": provenance}
            created = []
            try:
                # 独占创建：不覆盖用户文件；失败时清理本次创建的半成品。
                with target.open("xb") as f:
                    created.append(target)
                    f.write(body)
                with manifest.open("x", encoding="utf-8") as f:
                    created.append(manifest)
                    json.dump(entry, f, ensure_ascii=False, indent=2)
                    f.write("\n")
            except BaseException:
                for path in created:
                    path.unlink(missing_ok=True)
                raise
        return {"status": "SAVED", "path": str(target), "manifest": str(manifest),
                "sha256": digest, "bytes": len(body)}


def article_url(doi: str) -> str:
    return "https://doi.org/" + quote(normalize_doi(doi), safe="/")


def request_browser(url: str) -> dict:
    """只请求系统默认浏览器打开页面，返回值不证明页面已加载或登录成功。"""
    try:
        accepted = bool(webbrowser.open(url, new=2))
    except (webbrowser.Error, OSError):
        accepted = False
    return {"status": "BROWSER_OPEN_REQUESTED" if accepted else "BROWSER_OPEN_FAILED",
            "url": url, "authentication": "UNKNOWN",
            "note": "请在浏览器中查看实际页面；需要时本人登录。工具不读取密码、Cookie或页面"}


def open_access_page(doi: str, route: str = "article", open_browser: bool = True) -> dict:
    paper = article_url(doi)
    routes = {"article": paper, "carsi": "https://ds.carsi.edu.cn/",
              "webvpn": "https://webvpn.zju.edu.cn/"}
    if route not in routes:
        raise HelperError("访问路线应为 article、carsi 或 webvpn")
    result = {"status": "USER_ACCESS_PAGE", "doi": normalize_doi(doi),
              "article_url": paper, "url": routes[route], "route": route,
              "authentication": "UNKNOWN", "subscription_access": "UNKNOWN",
              "steps": ["打开论文官网；需要时使用Institutional sign in选择学校并由本人认证",
                        "CARSI先选择浙江大学；WebVPN登录后从数据库导航进入，不拼接代理地址",
                        "回到文献清单继续逐篇查看；保存到收件箱的PDF可用import整理"]}
    if open_browser:
        result["browser"] = request_browser(routes[route])
    return result


def render_reading_list(metadata: dict) -> str:
    """静态本地页；API文本全部转义，链接只由校方入口和有效DOI生成。"""
    esc = lambda value: html.escape(str(value), quote=True)
    cards = []
    for i, paper in enumerate(metadata["papers"], 1):
        try:
            link = '<a class="button" target="_blank" rel="noopener noreferrer" href="' + esc(article_url(paper.get("doi") or "")) + '">打开论文／需要时机构登录</a>'
        except HelperError:
            link = '<span>缺少有效DOI，请在数据库按标题查找</span>'
        collection = paper.get("collection") or {}
        labels = {"SAVED": "已保存PDF", "ALREADY_EXISTS": "PDF已存在", "USER_BROWSER_ACTION_REQUIRED": "全文未保存，可能需本人访问", "MANUAL_REQUIRED": "待文献传递或其他人工获取", "NOT_ATTEMPTED": "尚未尝试", "RATE_LIMITED": "来源限流，已停止", "ERROR": "获取出错", "DUPLICATE_SKIPPED": "重复DOI，已跳过"}
        state = collection.get("status")
        extra = '<p>收集结果：' + esc(labels.get(state, state or "仅检索，未执行全文收集")) + '</p>'
        digest = collection.get("sha256", "")
        if state in ("SAVED", "ALREADY_EXISTS") and re.fullmatch(r"[0-9a-f]{64}", digest):
            extra += '<a class="button" href="../../' + digest + '.pdf">打开已保存PDF</a> '
        checks = (collection.get("open_access_result") or {}).get("checks", [])
        if any(c.get("status") == "NEED_CONTACT_EMAIL" for c in checks):
            extra += '<p>Unpaywall开放版本查询尚未执行：需在本机配置普通联系邮箱。</p>'
        if state and state not in ("SAVED", "ALREADY_EXISTS", "DUPLICATE_SKIPPED"):
            extra += '<p><a target="_blank" rel="noopener noreferrer" href="https://libweb.zju.edu.cn/55971/list.htm">浙大文献传递</a></p>'
        cards.append('<article><h2>' + str(i) + '. ' + esc(paper.get("title") or "未提供标题") + '</h2><p>' +
                     esc(paper.get("year") or "年份未知") + ' · ' + esc(paper.get("venue") or "来源未知") +
                     '</p><p>' + esc('、'.join(paper.get("authors") or [])) + '</p><p>DOI：' +
                     esc(paper.get("doi") or "未知") + '</p>' + extra + link + '</article>')
    return (
        """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>文献清单</title><style>
body{font:16px/1.7 system-ui,sans-serif;background:#f4f6fa;color:#16233b;
margin:auto;padding:32px;max-width:980px}h1{font-size:28px}h2{font-size:19px;margin:0}
article,header{background:white;padding:24px;border-radius:12px;margin:18px 0}
p{margin:8px 0;overflow-wrap:anywhere}a{color:#164dae}
.button{display:inline-block;padding:8px 14px;border:1px solid #164dae;
border-radius:6px;text-decoration:none}nav a{margin-right:18px}
</style></head><body><header><h1>文献清单</h1><p>检索词："""
        + esc(metadata['query']) + '</p><p>处理模式：' + ('已执行全文收集，结果见各条目' if 'collection_summary' in metadata else '仅检索，尚未执行全文收集；需要自动保存请使用 search --collect') + """</p>
<p>1. 打开感兴趣的论文。2. 官网需要认证时，本人选择学校并登录。
3. 回到本清单继续查看；浏览器按网站规则保留登录状态。</p><nav>
<a target="_blank" rel="noopener noreferrer" href="https://ds.carsi.edu.cn/">CARSI机构认证入口</a>
<a target="_blank" rel="noopener noreferrer" href="https://webvpn.zju.edu.cn/">浙大WebVPN入口</a>
<a target="_blank" rel="noopener noreferrer" href="https://libweb.zju.edu.cn/2022/0408/c39479a2515130/page.htm">官方访问说明</a>
</nav><p>文献元数据来自Crossref；相关性需要本人筛选。机构登录与单篇订阅权限由官网显示，
工具尚未核验；本页不自动登录或下载订阅全文。</p></header><main>"""
        + ''.join(cards) + '</main></body></html>')



def institutional_guide(doi: str = "") -> dict:
    if doi:
        doi = normalize_doi(doi)
    return {"status": "MANUAL_INSTITUTIONAL_ACCESS", "school": "浙江大学",
            "doi_url": article_url(doi) if doi else None,
            "library": "https://libweb.zju.edu.cn/", "database_navigation": "https://libdb.zju.edu.cn/",
            "off_campus_guide": "https://libweb.zju.edu.cn/2022/0408/c39479a2515130/page.htm",
            "webvpn": "https://webvpn.zju.edu.cn/", "carsi": "https://ds.carsi.edu.cn/",
            "policy": "https://libweb.zju.edu.cn/2016/1014/c39581a1666449/page.htm",
            "steps": ["本人在浏览器中按图书馆指引登录；通过数据库导航找文献",
                      "按授权范围手动保存所需单篇 PDF 到自己设置的收件箱",
                      "使用 import 命令整理；需要下载的文献由本人决定"],
            "note": "不自动登录/复用 Cookie/批量爬取机构授权全文；不是浙大官方工具"}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="保存目录；默认项目 downloads，PDF和清单仅本地保存")
    parser.add_argument("--inbox", help="人工 PDF 收件箱目录")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("search"); p.add_argument("query"); p.add_argument("--limit", type=int, default=5)
    p.add_argument("--reading-list", action="store_true", help="保存本地HTML文献清单")
    p.add_argument("--collect", action="store_true", help="串行尝试保存检索结果全文，并记录逐篇状态")
    p.add_argument("--open", action="store_true", help="保存清单并在默认浏览器打开")
    p = sub.add_parser("collect", help="开放全文优先，无法保存时打开本人访问入口")
    p.add_argument("identifier"); p.add_argument("--no-open", action="store_true")
    p.add_argument("--access-state", choices=("unknown", "not_subscribed"), default="unknown", help="记录本人已确认本篇未订阅；不反复打开机构登录")
    p.add_argument("--via", choices=("article", "carsi", "webvpn"), default="article")
    p = sub.add_parser("access", help="用浏览器打开论文或官方机构访问入口")
    p.add_argument("doi"); p.add_argument("--no-open", action="store_true")
    p.add_argument("--via", choices=("article", "carsi", "webvpn"), default="article")
    for command in ("lookup", "oa", "guide"):
        p = sub.add_parser(command); p.add_argument("doi", nargs="?" if command == "guide" else None, default="")
    p = sub.add_parser("download"); p.add_argument("identifier")
    p = sub.add_parser("import"); p.add_argument("filename"); p.add_argument("--identifier", default="manual")
    args = parser.parse_args()
    helper = LiteratureHelper(args.output, args.inbox)
    try:
        if args.command == "search":
            if args.reading_list or args.open or args.collect:
                result = helper.reading_list(args.query, args.limit, args.open, args.collect)
            else:
                result = helper.search(args.query, args.limit)
        elif args.command == "collect":
            result = helper.collect(args.identifier, not args.no_open, args.via, args.access_state)
        elif args.command == "access":
            result = open_access_page(args.doi, args.via, not args.no_open)
        elif args.command == "lookup":
            result = helper.lookup(args.doi)
        elif args.command == "oa":
            result = helper.locate_oa(args.doi)
        elif args.command == "guide":
            result = institutional_guide(args.doi)
        elif args.command == "import":
            result = helper.import_pdf(args.filename, args.identifier)
        else:
            result = helper.download(args.identifier)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (HelperError, OSError) as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
