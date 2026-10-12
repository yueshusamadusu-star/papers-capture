"""公开 API 文献助手：不接收校园密码，不自动访问机构授权全文。"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

VERSION = "0.1.0"
MAX_PDF = 25 * 1024 * 1024
MAX_JSON = 2 * 1024 * 1024
# 首版仅自动下载这些公共来源；其余 OA 链接返回人工处理。
PDF_HOSTS = frozenset({"arxiv.org", "export.arxiv.org", "www.mdpi.com",
                       "mdpi-res.com", "pmc.ncbi.nlm.nih.gov"})
API_HOSTS = frozenset({"api.crossref.org", "api.unpaywall.org"})


class HelperError(ValueError):
    """可向用户展示的错误；不回显带邮箱等参数的请求地址。"""


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
                        if exc.code == 429:
                            raise HelperError("来源限流：请稍后重试，并遵守服务方 Retry-After 提示") from None
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
    return {"doi": work.get("DOI"), "title": (work.get("title") or [""])[0],
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

    def lookup(self, doi: str) -> dict:
        doi = normalize_doi(doi)
        url = "https://api.crossref.org/works/" + quote(doi, safe="")
        work = self.client.json(url).get("message")
        if not isinstance(work, dict):
            raise HelperError("未取得该 DOI 的 Crossref 记录")
        return {"status": "METADATA_ONLY", "paper": summarize(work)}

    def locate_oa(self, doi: str) -> dict:
        doi = normalize_doi(doi)
        email = os.environ.get("UNPAYWALL_EMAIL", "").strip()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            return {"status": "NEED_CONTACT_EMAIL", "doi": doi,
                    "note": "可在本机环境变量 UNPAYWALL_EMAIL 填本人联系邮箱；这是公共 API 联系字段，不是校园密码"}
        url = "https://api.unpaywall.org/v2/" + quote(doi, safe="") + "?" + urlencode({"email": email})
        record = self.client.json(url)
        location = record.get("best_oa_location") or {}
        pdf = location.get("url_for_pdf")
        supported = False
        if pdf:
            try:
                checked_url(pdf, PDF_HOSTS)
                supported = True
            except HelperError:
                pass
        return {"status": "OA_FOUND" if pdf else "MANUAL_REQUIRED", "doi": doi,
                "pdf_url": pdf, "landing_url": location.get("url_for_landing_page"),
                "license": location.get("license"), "version": location.get("version"),
                "automatic_download_supported": supported, "source": "Unpaywall",
                "note": "OA 可读不等于可再分发；未支持站点请人工访问"}

    def download(self, identifier: str) -> dict:
        if identifier.startswith("arxiv:"):
            aid = identifier[6:].strip()
            if not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v[1-9]\d*)?", aid):
                raise HelperError("arXiv 编号无效，例如 arxiv:1706.03762")
            url = "https://arxiv.org/pdf/" + aid
            evidence = {"provider": "arXiv", "landing_url": "https://arxiv.org/abs/" + aid,
                        "license": "逐篇许可见 arXiv 页面；仅本地个人研究，不再分发"}
        else:
            identifier = normalize_doi(identifier)
            location = self.locate_oa(identifier)
            if location["status"] != "OA_FOUND" or not location["automatic_download_supported"]:
                return location
            url = location["pdf_url"]
            evidence = location
        body, final_url = self.client.get(url, PDF_HOSTS, MAX_PDF)
        return self._save_pdf(body, identifier, {"origin": "public_oa", "url": url,
                                                "final_url": final_url, "evidence": evidence})

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
            raise HelperError("没有取得完整 PDF（可能是登录/验证码页面），未保存")
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


def institutional_guide(doi: str = "") -> dict:
    if doi:
        doi = normalize_doi(doi)
    return {"status": "MANUAL_INSTITUTIONAL_ACCESS", "school": "浙江大学",
            "doi_url": "https://doi.org/" + doi if doi else None,
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
    for command in ("lookup", "oa", "guide"):
        p = sub.add_parser(command); p.add_argument("doi", nargs="?" if command == "guide" else None, default="")
    p = sub.add_parser("download"); p.add_argument("identifier")
    p = sub.add_parser("import"); p.add_argument("filename"); p.add_argument("--identifier", default="manual")
    args = parser.parse_args()
    helper = LiteratureHelper(args.output, args.inbox)
    try:
        if args.command == "search":
            result = helper.search(args.query, args.limit)
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
