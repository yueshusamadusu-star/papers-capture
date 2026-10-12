"""少量联网验收：公开检索、DOI核对、单篇arXiv全文；不访问校园登录。"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from literature_helper import LiteratureHelper


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="PDF与联网验收摘要保存目录")
    args = parser.parse_args()
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    helper = LiteratureHelper(root / "pdfs")
    result = {"time_utc": datetime.now(timezone.utc).isoformat(), "checks": {},
              "scope": "公共来源少量请求；不测试校园登录或授权资源爬取"}
    for name, action in (
        ("search", lambda: helper.search("ultrasonic flowmeter cycle skipping", 3)),
        ("lookup", lambda: helper.lookup("10.3390/metrology5040071")),
        ("download", lambda: helper.download("arxiv:1706.03762")),
    ):
        try:
            value = action()
            if name == "search":
                assert len(value["papers"]) > 0
            elif name == "lookup":
                assert value["paper"]["doi"].lower() == "10.3390/metrology5040071"
            else:
                pdf = Path(value["path"])
                assert hashlib.sha256(pdf.read_bytes()).hexdigest() == value["sha256"]
            result["checks"][name] = {"status": "PASS", "result": value}
        except Exception as exc:
            result["checks"][name] = {"status": "FAILED", "reason": str(exc)}
        print(name + ": " + result["checks"][name]["status"], flush=True)
    (root / "live_verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if all(c["status"] == "PASS" for c in result["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
