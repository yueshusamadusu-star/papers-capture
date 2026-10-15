"""stdio MCP 适配器；所有下载/导入只写启动时设置的目录。"""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from typing import Any
from literature_helper import LiteratureHelper, institutional_guide, open_access_page

server = FastMCP("ZJU Literature Helper (unofficial)")
helper = LiteratureHelper()
from collection_workflow import CollectionManager
collections = CollectionManager(helper)
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)


@server.tool(annotations=READ)
def search_papers(query: str, limit: int = 5) -> dict[str, Any]:
    """通过 Crossref 查询最多10篇公开元数据，不下载全文。"""
    return helper.search(query, limit)


@server.tool(annotations=READ)
def lookup_paper(doi: str) -> dict[str, Any]:
    """核对单篇 DOI 的公开元数据。"""
    return helper.lookup(doi)


@server.tool(annotations=READ)
def locate_open_access(doi: str) -> dict[str, Any]:
    """通过 Unpaywall 查找开放版本，需本机 UNPAYWALL_EMAIL 联系邮箱。"""
    return helper.locate_oa(doi)


@server.tool(annotations=WRITE)
def download_open_access(identifier: str) -> dict[str, Any]:
    """下载用户选定的一篇公开全文到指定根目录。输入 DOI 或 arxiv:编号，不接受任意网址或校园凭据。"""
    return helper.download(identifier)


@server.tool(annotations=READ)
def zju_access_guide(doi: str = "") -> dict[str, Any]:
    """返回浙大官方人工访问指引；不登录或操作浏览器。"""
    return institutional_guide(doi)


@server.tool(annotations=WRITE)
def import_local_pdf(filename: str, identifier: str = "manual") -> dict[str, Any]:
    """将用户放入收件箱的一个 PDF 复制整理到保存目录，保留原文件；只接受文件名。"""
    return helper.import_pdf(filename, identifier)


@server.tool(annotations=WRITE)
def prepare_reading_list(query: str, limit: int = 5, open_browser: bool = False) -> dict[str, Any]:
    """检索并保存本地HTML文献清单；open_browser=true时请求默认浏览器打开，不读取登录状态。"""
    return helper.reading_list(query, limit, open_browser)


@server.tool(annotations=WRITE)
def open_paper_access(doi: str, route: str = "article", open_browser: bool = False) -> dict[str, Any]:
    """给出论文/CARSI/WebVPN入口；open_browser=true才打开浏览器，由用户本人认证。"""
    return open_access_page(doi, route, open_browser)


@server.tool(annotations=WRITE)
def collect_paper(identifier: str, open_browser: bool = False, route: str = "article", access_state: str = "unknown") -> dict[str, Any]:
    """优先下载支持的开放全文；否则提供本人访问入口，可显式请求打开浏览器。不会在浏览器中执行认证。"""
    return helper.collect(identifier, open_browser, route, access_state)


@server.tool(annotations=WRITE)
def search_and_collect(query: str, limit: int = 3, open_browser: bool = False) -> dict[str, Any]:
    """串行检索并尝试保存最多10篇公开全文，清单逐篇记录结果；限流停止，不弹逐篇认证页。"""
    return helper.reading_list(query, limit, open_browser, collect_fulltext=True)


@server.tool(annotations=WRITE)
def begin_literature_collection(prompt: str, english_queries: list[str], per_query: int = 5, max_papers: int = 15, use_browser: bool = True) -> dict[str, Any]:
    """先由调用agent把中文需求拆成1–4条专业英文检索式；本工具多式检索、按DOI去重并启动后台收集。优先公开PDF；需要认证时打开专用浏览器，由本人登录后自动核对本篇权限并保存/退避。返回session_id；后续调用collection_status，不能把启动当作下载完成。"""
    return collections.create(prompt, english_queries, per_query, max_papers, use_browser)


@server.tool(annotations=WRITE)
def begin_paper_downloads(dois: list[str], use_browser: bool = True) -> dict[str, Any]:
    """启动本人选定的1–30篇DOI的公开优先/本人认证收集任务；需要本人授权时暂停，不接收账号密码。"""
    return collections.from_identifiers(dois, use_browser)


@server.tool(annotations=READ)
def collection_status(session_id: str) -> dict[str, Any]:
    """读取收集任务的逐篇下载/权限/待本人认证状态与实际PDF数量；不读取浏览器密码、Cookie或其他标签内容。"""
    return collections.status(session_id)


@server.tool(annotations=WRITE)
def resume_collection(session_id: str) -> dict[str, Any]:
    """本人表示已完成授权并返回论文页后，继续核对和保存；网页仍不确定时保留未知，不假称授权成功。"""
    return collections.action(session_id, "resume")


@server.tool(annotations=WRITE)
def skip_collection_paper(session_id: str) -> dict[str, Any]:
    """按本人要求跳过当前待处理论文，保留元数据并继续下一篇；不把本人跳过写成无订阅。"""
    return collections.action(session_id, "skip")


@server.tool(annotations=WRITE)
def close_collection(session_id: str) -> dict[str, Any]:
    """关闭该文献任务的专用浏览器，保留已保存PDF与进度，不关闭用户既有浏览器。"""
    return collections.action(session_id, "close")


@server.tool(annotations=WRITE)
def use_regular_browser(session_id: str, open_browser: bool = True) -> dict[str, Any]:
    """专用自动化浏览器反复验证时，改用本人正常Chrome/Edge中的本地扩展接续。停止原专用后端，给出一次性安装目录并打开本机配对页；不绕过验证码。扩展使用浏览器自己的下载权限，不导出Cookie或密码。需本人加载扩展，实际下载结果由collection_status核对。"""
    from normal_browser import use_regular_browser as connect
    return connect(collections, session_id, open_browser)


def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
