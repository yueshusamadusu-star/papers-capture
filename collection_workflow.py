"""可恢复的文献任务：专业检索式由调用agent提供，认证在专用浏览器完成。"""
from __future__ import annotations

from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
from urllib.parse import quote

from literature_helper import LiteratureHelper, HelperError, RateLimitError, normalize_doi, article_url, VERSION

TERMINAL = {"SAVED", "ALREADY_EXISTS", "SKIPPED_NO_ACCESS", "SKIPPED_BY_USER", "NO_IDENTIFIER", "ERROR", "UNSUPPORTED_PUBLISHER"}


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, data: dict):
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with tmp.open("x", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def validate_plan(prompt: str, queries: list[str], per_query: int, max_papers: int):
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 2000:
        raise HelperError("研究需求长度应为1–2000")
    if not queries and not re.search(r"[\u4e00-\u9fff]", prompt):
        queries = [prompt]
    if not queries:
        raise HelperError("NEED_QUERY_TRANSLATION：请调用agent先将需求拆成1–4条专业英文检索式，再调用本工具；无需另买模型API")
    if not isinstance(queries, list) or not 1 <= len(queries) <= 4:
        raise HelperError("需要1–4条专业英文检索式")
    if any(not isinstance(q, str) or not 1 <= len(q.strip()) <= 500 or re.search(r"[\u4e00-\u9fff]", q) for q in queries):
        raise HelperError("english_queries须为非空英文检索式，不把中文长句直接发送检索")
    if not 1 <= per_query <= 10 or not 1 <= max_papers <= 30:
        raise HelperError("每式1–10篇；单任务最多1–30篇，按相关性排序后去重")
    return list(dict.fromkeys(q.strip() for q in queries))


class CollectionManager:
    def __init__(self, helper=None, browser_dir=None):
        self.helper = helper or LiteratureHelper()
        self.root = self.helper.output / "collections"
        self.browser_dir = Path(browser_dir or os.environ.get("LIT_BROWSER_DIR") or Path(__file__).parent / ".local-browser").resolve()

    def directory(self, session_id):
        if not isinstance(session_id, str) or not re.fullmatch(r"[0-9a-f]{32}", session_id):
            raise HelperError("任务编号无效")
        path = self.root / session_id
        if path.is_symlink() or path.resolve().parent != self.root.resolve():
            raise HelperError("任务目录不在允许根目录")
        return path

    def load(self, session_id):
        path = self.directory(session_id) / "state.json"
        if not path.is_file() or path.is_symlink():
            raise HelperError("未找到该收集任务")
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, state):
        directory = self.directory(state["session_id"])
        directory.mkdir(parents=True, exist_ok=True)
        state["updated_at"] = now()
        state["summary"] = {s: sum(p["status"] == s for p in state["papers"]) for s in sorted({p["status"] for p in state["papers"]})}
        atomic_json(directory / "state.json", state)
        target = directory / "index.html"
        tmp = target.with_suffix(".tmp")
        tmp.write_text(render_collection(state), encoding="utf-8")
        os.replace(tmp, target)

    def create(self, prompt: str, english_queries: list[str], per_query=5, max_papers=15, use_browser=True, start_worker=True):
        queries = validate_plan(prompt, english_queries, per_query, max_papers)
        papers, by_id, searches = [], {}, []
        for query in queries:
            result = self.helper.search(query, per_query)
            searches.append({"query": query, "provider": "Crossref", "returned": len(result["papers"])})
            for paper in result["papers"]:
                try:
                    key = normalize_doi(paper.get("doi") or "")
                except HelperError:
                    continue
                if key in by_id:
                    by_id[key]["matched_queries"].append(query)
                    continue
                item = {**paper, "identifier": key, "doi": key, "matched_queries": [query], "status": "PUBLIC_PENDING", "article_url": article_url(key)}
                by_id[key] = item
                papers.append(item)
        words = set(re.findall(r"[a-z]{3,}", " ".join(queries).lower())) - {"and", "the", "for", "with"}
        for p in papers:
            p["title_term_matches"] = len(words & set(re.findall(r"[a-z]{3,}", p.get("title", "").lower())))
        papers.sort(key=lambda p: (p["title_term_matches"], len(p["matched_queries"])), reverse=True)
        return self._create(prompt, queries, searches, papers[:max_papers], use_browser, start_worker)

    def from_identifiers(self, identifiers: list[str], use_browser=True, start_worker=True):
        if not isinstance(identifiers, list) or not 1 <= len(identifiers) <= 30:
            raise HelperError("需要1–30个DOI")
        keys = list(dict.fromkeys(normalize_doi(i) for i in identifiers))
        papers = []
        for key in keys:
            paper = self.helper.lookup(key)["paper"]
            papers.append({**paper, "identifier": key, "doi": key, "matched_queries": [], "status": "PUBLIC_PENDING", "article_url": article_url(key)})
        return self._create("本人选定的论文", [], [], papers, use_browser, start_worker)

    def _create(self, prompt, queries, searches, papers, use_browser, start_worker):
        sid = uuid.uuid4().hex
        state = {"tool_version": VERSION, "session_id": sid, "created_at": now(), "status": "CREATED" if papers else "FINISHED", "original_prompt": prompt,
                 "english_queries": queries, "searches": searches, "papers": papers, "use_browser": use_browser,
                 "current_index": None, "note": "题名相关性仅初筛；只有实际保存并校验PDF才计入全文数量，摘要不计全文"}
        self.save(state)
        if papers and start_worker:
            self.launch(sid)
        return self.status(sid)

    def launch(self, sid):
        state = self.load(sid)
        if state["status"] in {"FINISHED", "STOPPED_RATE_LIMIT", "CLOSED"}:
            return
        state["status"] = "STARTING"
        self.save(state)
        options = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("browser_worker.py")),
                                    "--session", sid, "--output", str(self.helper.output), "--browser-dir", str(self.browser_dir)], **options)
        return process.pid

    def status(self, sid):
        state = self.load(sid)
        if state["status"] == "STARTING" and not (self.directory(sid) / "started.json").exists():
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(state["updated_at"])).total_seconds()
            if age > 30:
                state["status"] = "WORKER_ERROR"
                state["reason"] = "后台启动未确认，保留进度；可resume重试，不能当作已开始下载"
                self.save(state)
        state["dashboard"] = str(self.directory(sid) / "index.html")
        state["manifest"] = str(self.directory(sid) / "state.json")
        state["actual_pdf_count"] = sum(p["status"] in {"SAVED", "ALREADY_EXISTS"} for p in state["papers"])
        return state

    def action(self, sid, action):
        if action not in {"resume", "skip", "close"}:
            raise HelperError("操作仅支持resume、skip、close")
        state = self.load(sid)
        if state["status"] in {"FINISHED", "STOPPED_RATE_LIMIT", "CLOSED"}:
            return self.status(sid)
        if action == "skip" and state.get("current_index") is None:
            raise HelperError("暂无待本人处理的当前论文；请先查看任务状态")
        if state.get("backend") == "regular_extension":
            if action == "close":
                state["status"] = "CLOSED"
            elif action == "skip":
                state["papers"][state["current_index"]]["status"] = "SKIPPED_BY_USER"
            else:
                # 恢复服务先于任务写入；启动失败时保留原断点和逐篇状态。
                from normal_browser import ensure_bridge
                ensure_bridge(self)
                result = self.status(sid)
                result["note"] = "本机接续服务已就绪；请在正常浏览器扩展点击‘我已登录，检查当前论文’，以接续当前可见页面"
                return result
            self.save(state)
            return self.status(sid)
        atomic_json(self.directory(sid) / "command.json", {"action": action, "id": uuid.uuid4().hex})
        if action == "close" and state["status"] in {"TIMED_OUT", "BROWSER_BUSY", "BROWSER_UNAVAILABLE", "WORKER_ERROR"}:
            state["status"] = "CLOSED"
            self.save(state)
        if state["status"] in {"TIMED_OUT", "BROWSER_BUSY", "BROWSER_UNAVAILABLE", "WORKER_ERROR"} and action == "resume":
            self.launch(sid)
        return self.status(sid)

    def run_public(self, state):
        if state["status"] in {"FINISHED", "CLOSED", "STOPPED_RATE_LIMIT"}:
            return state["status"] == "FINISHED"
        state["status"] = "PUBLIC_COLLECTION"
        self.save(state)
        for p in state["papers"]:
            command = self.directory(state["session_id"]) / "command.json"
            if command.exists() and json.loads(command.read_text(encoding="utf-8")).get("action") == "close":
                command.unlink(missing_ok=True)
                state["status"] = "CLOSED"; self.save(state); return False
            if p["status"] != "PUBLIC_PENDING":
                continue
            try:
                result = self.helper.download(p["identifier"])
                p["public_result"] = result
                p["status"] = result["status"] if result["status"] in {"SAVED", "ALREADY_EXISTS"} else "BROWSER_PENDING"
                if p["status"] in {"SAVED", "ALREADY_EXISTS"}:
                    p["file"] = {k: result[k] for k in ["path", "sha256", "bytes", "manifest"] if k in result}
            except RateLimitError:
                state["status"] = "STOPPED_RATE_LIMIT"
                p["status"] = "RATE_LIMITED"
                self.save(state)
                return False
            except (HelperError, OSError):
                p["status"] = "ERROR"
                p["reason"] = "公开来源请求失败；不冒充未登录或未订阅，可另立任务重试"
            self.save(state)
        return True


def render_collection(state):
    esc = lambda s: html.escape(str(s), quote=True)
    labels = {"SAVED": "已保存PDF", "ALREADY_EXISTS": "PDF已存在", "BROWSER_PENDING": "等待浏览器检查", "PUBLIC_PENDING": "等待公开来源检查",
              "NEED_USER_AUTHENTICATION": "请在所选浏览器本人登录", "ACCESS_UNKNOWN": "权限尚不确定", "CHALLENGE_REQUIRED": "请本人完成网站验证",
              "NEED_BROWSER_SAVE": "请点已打开PDF阅读器的下载按钮，工具接收归档", "SKIPPED_NO_ACCESS": "本篇无全文权限，已退避", "SKIPPED_BY_USER": "本人跳过", "ERROR": "请求失败", "UNSUPPORTED_PUBLISHER": "尚未适配的出版商"}
    cards = []
    for p in state["papers"]:
        href = article_url(p["doi"])
        content = '<article><h2>' + esc(p.get("title", p["doi"])) + '</h2><p>' + esc(p["doi"]) + ' · ' + esc(labels.get(p["status"], p["status"])) + '</p>'
        digest = p.get("file", {}).get("sha256", "")
        if re.fullmatch(r"[0-9a-f]{64}", digest):
            content += '<a href="../../' + digest + '.pdf">查看已保存PDF</a> · '
        content += '<a target="_blank" href="' + esc(href) + '">论文官网／本人认证</a></article>'
        cards.append(content)
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta http-equiv="refresh" content="8"><title>文献收集任务</title><style>body{font:16px/1.7 system-ui;max-width:1000px;margin:30px auto;padding:20px;background:#f4f6fa}article,header{background:white;padding:20px;margin:16px 0;border-radius:10px}h2{font-size:19px}a{color:#164dae}</style><header><h1>文献收集任务</h1><p>' + esc(state["original_prompt"]) + '</p><p>状态：' + esc(state["status"]) + '；全文已保存：' + str(sum(p["status"] in {"SAVED", "ALREADY_EXISTS"} for p in state["papers"])) + '</p><p>需要授权时，请在所选浏览器本人登录并返回论文页，不需要把密码发给agent。普通浏览器扩展可点“我已登录，检查当前论文”；专用浏览器可对agent说“我已登录，继续”。不确定权限不会直接判成无权限。</p><p>任务编号：' + esc(state["session_id"]) + '</p></header>' + ''.join(cards) + '</html>'


def main():
    import argparse
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    sub = parser.add_subparsers(dest="action", required=True)
    p=sub.add_parser("start"); p.add_argument("prompt"); p.add_argument("--query", action="append", default=[])
    p.add_argument("--per-query", type=int, default=5); p.add_argument("--max-papers", type=int, default=15); p.add_argument("--no-browser", action="store_true")
    p=sub.add_parser("papers"); p.add_argument("identifiers", nargs="+"); p.add_argument("--no-browser", action="store_true")
    for verb in ["status", "resume", "skip", "close"]:
        p=sub.add_parser(verb); p.add_argument("session_id")
    args=parser.parse_args()
    manager=CollectionManager(LiteratureHelper(args.output))
    try:
        if args.action == "start":
            result=manager.create(args.prompt,args.query,args.per_query,args.max_papers,not args.no_browser)
        elif args.action == "papers":
            result=manager.from_identifiers(args.identifiers,not args.no_browser)
        elif args.action == "status":
            result=manager.status(args.session_id)
        else:
            result=manager.action(args.session_id,args.action)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (HelperError,OSError) as exc:
        print(json.dumps({"status":"ERROR","message":str(exc)},ensure_ascii=False),file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
