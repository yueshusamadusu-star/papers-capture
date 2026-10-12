"""stdio MCP 适配器；所有下载/导入只写启动时设置的目录。"""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from typing import Any
from literature_helper import LiteratureHelper, institutional_guide

server = FastMCP("ZJU Literature Helper (unofficial)")
helper = LiteratureHelper()
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


def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
