"""IEEE校园网直连：仅增减Windows手动代理绕过列表中的IEEE条目。"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import re
from datetime import datetime, timezone
import uuid
from literature_helper import HelperError

RULES = ("ieee.org", "*.ieee.org")
REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"

def merge_rules(value):
    present = {p.strip().lower() for p in value.split(";") if p.strip()}
    added = [p for p in RULES if p not in present]
    suffix = ";".join(added)
    merged = value + ("" if not value or value.endswith(";") else ";") + suffix if suffix else value
    return merged, added

class WindowsProxyStore:
    def read(self):
        import winreg
        result = {"ProxyEnable": 0, "ProxyServer": "", "ProxyOverride": "", "AutoConfigURL": "",
                  "override_exists": False}
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH, 0, winreg.KEY_READ) as key:
            for name in ("ProxyEnable", "ProxyServer", "ProxyOverride", "AutoConfigURL"):
                try:
                    result[name] = winreg.QueryValueEx(key, name)[0]
                    if name == "ProxyOverride": result["override_exists"] = True
                except FileNotFoundError:
                    pass
        if not isinstance(result["ProxyOverride"], str):
            raise HelperError("系统代理例外格式未知，未改设置")
        return result
    def write_override(self, value, exists=True):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            if exists:
                winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, value)
            else:
                try: winreg.DeleteValue(key, "ProxyOverride")
                except FileNotFoundError: pass
    def notify(self):
        import ctypes
        wininet = ctypes.WinDLL("wininet", use_last_error=True)
        changed = bool(wininet.InternetSetOptionW(None, 39, None, 0))
        refreshed = bool(wininet.InternetSetOptionW(None, 37, None, 0))
        return changed and refreshed

class IeeeNetworkPolicy:
    def __init__(self, browser_dir, store=None):
        self.path = Path(browser_dir) / "ieee-route.json"
        self.store = store if store is not None else (WindowsProxyStore() if os.name == "nt" else None)
        self.lock = threading.Lock()
    def _load(self):
        if not self.path.is_file(): return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict): raise HelperError("IEEE网络备份无效，未改设置")
        return data
    def _save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)
    def browser_template(self):
        """只向已授权扩展提供本机环回代理模板，不输出远端节点或认证信息。"""
        if self.store is None:
            return {"status": "UNSUPPORTED_SYSTEM_PROXY"}
        current = self.store.read()
        if current.get("AutoConfigURL") or not current.get("ProxyEnable"):
            return {"status": "UNSUPPORTED_SYSTEM_PROXY"}
        server = current.get("ProxyServer", "")
        match = re.fullmatch(r"(127\.0\.0\.1|localhost|\[::1\]):([0-9]{1,5})", server, re.I) if isinstance(server, str) else None
        if not match or not 0 < int(match[2]) < 65536:
            return {"status": "UNSUPPORTED_SYSTEM_PROXY"}
        host = match[1].strip("[]").lower()
        return {"status": "MANUAL_LOOPBACK_PROXY_TEMPLATE", "config": {
            "mode": "fixed_servers", "rules": {
                "singleProxy": {"scheme": "http", "host": host, "port": int(match[2])},
                "bypassList": [p.strip() for p in current["ProxyOverride"].split(";") if p.strip()]}}}
    def record_browser(self, data):
        # 只保存枚举与布尔量；不接收原始代理配置、网址、IP、Cookie或令牌。
        if not isinstance(data, dict):
            raise HelperError("浏览器网络诊断格式无效")
        choices = {
            "status": {"NEED_PROXY_PERMISSION", "BROWSER_RULE_CONFIGURED",
                       "BROWSER_ROUTE_UNCONFIRMED", "ALREADY_DIRECT", "BROWSER_OVERRIDE_CLEARED"},
            "mode": {"unknown", "direct", "system", "fixed_servers", "pac_script", "auto_detect"},
            "level": {"unknown", "not_controllable", "controlled_by_other_extensions",
                      "controllable_by_this_extension", "controlled_by_this_extension"}}
        result = {k: data[k] for k, allowed in choices.items() if data.get(k) in allowed}
        if "status" not in result:
            raise HelperError("浏览器网络状态无效")
        for key in ("enabled", "rule_present", "configuration_verified"):
            result[key] = data.get(key) is True
        result["exit_verified"] = False
        result["observed_at"] = datetime.now(timezone.utc).isoformat()
        version = data.get("extension_version", "")
        if isinstance(version, str) and re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", version):
            result["extension_version"] = version
        target = self.path.with_name("ieee-browser-diagnostic.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
        return result
    def status(self):
        policy = self._load()
        if self.store is None:
            return {"status": "MANUAL_PLATFORM", "policy_enabled": bool(policy.get("enabled")),
                    "direct_rule_present": False, "scope": list(RULES)}
        current = self.store.read()
        present = {p.strip().lower() for p in current["ProxyOverride"].split(";") if p.strip()}
        direct = all(p in present for p in RULES)
        state = ("MANUAL_PAC" if current.get("AutoConfigURL") else
                 "DIRECT_RULE_CONFIGURED" if direct else
                 "NO_SYSTEM_PROXY" if not current.get("ProxyEnable") else "NEED_IEEE_DIRECT_RULE")
        return {"status": state, "policy_enabled": bool(policy.get("enabled")),
                "direct_rule_present": direct, "system_proxy_enabled": bool(current.get("ProxyEnable")),
                "scope": list(RULES)}
    def enable(self):
        with self.lock:
            if self.store is None:
                raise HelperError("当前平台请在代理软件中为ieee.org及子域添加DIRECT规则")
            before = self.store.read()
            if before.get("AutoConfigURL"):
                raise HelperError("当前使用PAC，不覆盖它；请在原代理规则中把IEEE域名设为DIRECT")
            merged, added = merge_rules(before["ProxyOverride"])
            saved = self._load()
            if not saved.get("enabled"):
                saved = {"before_override": before["ProxyOverride"],
                         "before_exists": bool(before.get("override_exists")), "added": []}
            saved.update(enabled=True, applied_override=merged,
                         added=list(dict.fromkeys(saved.get("added", []) + added)))
            self._save(saved)
            if merged != before["ProxyOverride"]: self.store.write_override(merged)
            notified = self.store.notify()
            after = self.store.read()
            result = self.status()
            result.update(proxy_settings_preserved=all(before.get(k) == after.get(k)
                          for k in ("ProxyEnable", "ProxyServer", "AutoConfigURL")), settings_notified=notified)
            return result
    def restore(self):
        with self.lock:
            saved = self._load()
            if not saved.get("enabled"): return self.status()
            if self.store is None: raise HelperError("当前平台无法撤销Windows代理例外")
            before = self.store.read()
            added = saved.get("added", [])
            if any(item not in RULES for item in added):
                raise HelperError("备份包含范围外条目，未撤销设置")
            if before["ProxyOverride"] == saved.get("applied_override"):
                value, exists = saved["before_override"], bool(saved["before_exists"])
            else:
                value = ";".join(p for p in before["ProxyOverride"].split(";") if p.strip() not in added)
                exists = True
            self.store.write_override(value, exists)
            self.store.notify()
            saved["enabled"] = False
            self._save(saved)
            return self.status()

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser-dir", default=str(Path(__file__).parent / ".local-browser"))
    parser.add_argument("action", choices=["status", "enable", "restore"])
    args = parser.parse_args()
    try:
        result = getattr(IeeeNetworkPolicy(args.browser_dir), args.action)()
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (HelperError, OSError, ValueError) as exc:
        print(json.dumps({"status": "NETWORK_CONFIGURATION_REQUIRED", "message": str(exc)}, ensure_ascii=False))
        return 1
if __name__ == "__main__":
    raise SystemExit(main())
