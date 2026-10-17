"""本人双击启动本机文献服务：保留配对、旧任务和已有文件。"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import webbrowser

from literature_helper import LiteratureHelper, HelperError
from collection_workflow import CollectionManager
from normal_browser import ORIGIN, ensure_bridge


def resolve_paths(output=None, browser_dir=None):
    base = Path(__file__).resolve().parent
    browser = Path(browser_dir or os.environ.get("LIT_BROWSER_DIR") or base / ".local-browser").resolve()
    config = browser / "service-launcher.json"
    local = json.loads(config.read_text(encoding="utf-8")) if config.is_file() else {}
    if not isinstance(local, dict) or ("output_dir" in local and
            (not isinstance(local["output_dir"], str) or not local["output_dir"].strip())):
        raise HelperError("本机启动配置无效，请核对文献库路径；未重建任务")
    destination = output or os.environ.get("LIT_OUTPUT_DIR") or local.get("output_dir") or base / "downloads"
    return Path(destination).resolve(), browser


def start_service(output=None, browser_dir=None, open_page=False):
    destination, browser = resolve_paths(output, browser_dir)
    manager = CollectionManager(LiteratureHelper(destination), browser)
    info = ensure_bridge(manager)
    opened = False
    if open_page:
        # 与既有扩展使用同一配对令牌；不在终端或返回值中输出。
        try:
            opened = bool(webbrowser.open(ORIGIN + "/pair#" + info["token"], new=2))
        except (webbrowser.Error, OSError):
            pass
    return {"status": "READY", "pid": info.get("pid"), "page": ORIGIN + "/pair",
            "page_requested": opened, "output_dir": str(destination)}


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="文献库路径；默认使用本机记录")
    parser.add_argument("--browser-dir", help="既有配对记录目录")
    parser.add_argument("--open", action="store_true", help="服务就绪后打开本机连接页")
    args = parser.parse_args(argv)
    try:
        result = start_service(args.output, args.browser_dir, args.open)
    except (HelperError, OSError, ValueError):
        print("本机文献服务未能就绪。原任务保留；请把此提示告诉agent，核对8766端口或本机启动配置。")
        return 1
    print("文献服务已在后台就绪；已运行时直接复用，原配对和已下载文件保留。")
    print("接下来在Chrome右上角拼图按钮中打开papers-capture。")
    if args.open and not result["page_requested"]:
        print("浏览器未自动打开，可在Chrome访问：" + result["page"])
    print("关闭此启动窗口不会停止后台文献服务。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
