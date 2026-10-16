import tempfile
from pathlib import Path
import unittest
from ieee_network import IeeeNetworkPolicy, merge_rules
from literature_helper import HelperError

class Store:
    def __init__(self, **changes):
        self.values = {"ProxyEnable": 1, "ProxyServer": "127.0.0.1:8001",
                       "ProxyOverride": "<local>;example.edu", "AutoConfigURL": "", "override_exists": True}
        self.values.update(changes)
        self.writes = 0
    def read(self): return dict(self.values)
    def write_override(self, value, exists=True):
        self.writes += 1
        self.values.update(ProxyOverride=value, override_exists=exists)
    def notify(self): return True

class IeeeNetworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store()
        self.policy = IeeeNetworkPolicy(Path(self.temp.name), self.store)
    def tearDown(self): self.temp.cleanup()
    def test_enable_preserves_chat_proxy_and_exact_original_roundtrip(self):
        original = dict(self.store.values)
        result = self.policy.enable()
        self.assertTrue(result["proxy_settings_preserved"])
        self.assertEqual(self.store.values["ProxyServer"], original["ProxyServer"])
        self.assertEqual(self.store.values["ProxyEnable"], original["ProxyEnable"])
        self.assertEqual(self.store.values["ProxyOverride"], "<local>;example.edu;ieee.org;*.ieee.org")
        self.policy.restore()
        self.assertEqual(self.store.values, original)
    def test_repeated_enable_does_not_lose_original_backup(self):
        original = self.store.values["ProxyOverride"]
        self.policy.enable(); self.policy.enable(); self.policy.restore()
        self.assertEqual(self.store.values["ProxyOverride"], original)
    def test_restore_retains_new_rules_added_by_another_program(self):
        self.policy.enable()
        self.store.values["ProxyOverride"] += ";later.example.edu"
        self.policy.restore()
        self.assertEqual(self.store.values["ProxyOverride"], "<local>;example.edu;later.example.edu")
    def test_pac_is_not_overwritten(self):
        self.store.values["AutoConfigURL"] = "https://example.invalid/proxy.pac"
        with self.assertRaises(HelperError): self.policy.enable()
        self.assertEqual(self.store.writes, 0)
        self.assertFalse(self.policy.path.exists())
    def test_read_status_does_not_change_settings(self):
        result = self.policy.status()
        self.assertEqual(result["status"], "NEED_IEEE_DIRECT_RULE")
        self.assertEqual(self.store.writes, 0)
        self.assertNotIn("127.0.0.1", str(result))
    def test_preexisting_ieee_bypass_is_retained_on_restore(self):
        self.store.values["ProxyOverride"] += ";ieee.org;*.ieee.org"
        original = self.store.values["ProxyOverride"]
        self.policy.enable(); self.policy.restore()
        self.assertEqual(self.store.values["ProxyOverride"], original)
    def test_browser_template_keeps_loopback_proxy_and_existing_exceptions(self):
        self.policy.enable()
        result = self.policy.browser_template()
        self.assertEqual(result["status"], "MANUAL_LOOPBACK_PROXY_TEMPLATE")
        self.assertEqual(result["config"]["rules"]["singleProxy"], {"scheme": "http", "host": "127.0.0.1", "port": 8001})
        self.assertIn("example.edu", result["config"]["rules"]["bypassList"])
    def test_browser_template_refuses_pac_remote_or_disabled_proxy(self):
        for update in ({"AutoConfigURL": "https://example.invalid/private"},
                       {"ProxyServer": "remote.example:8001"},
                       {"ProxyServer": "user:password@localhost:8001"},
                       {"ProxyEnable": 0}):
            with self.subTest(update=list(update)):
                store = Store(**update)
                result = IeeeNetworkPolicy(Path(self.temp.name), store).browser_template()
                self.assertEqual(result, {"status": "UNSUPPORTED_SYSTEM_PROXY"})
                self.assertEqual(store.writes, 0)
    def test_browser_report_keeps_only_redacted_diagnostics(self):
        result = self.policy.record_browser({
            "status": "BROWSER_RULE_CONFIGURED", "mode": "fixed_servers", "level": "controlled_by_this_extension",
            "configuration_verified": True, "exit_verified": True, "extension_version": "0.4.5",
            "proxy": "private-value", "cookie": "private-value"})
        self.assertTrue(result["configuration_verified"])
        self.assertFalse(result["exit_verified"])
        self.assertNotIn("private-value", str(result))
        self.assertEqual(result["extension_version"], "0.4.5")
        self.assertTrue(self.policy.path.with_name("ieee-browser-diagnostic.json").is_file())
        with self.assertRaises(HelperError):
            self.policy.record_browser({"status": "https://private.invalid/"})
    def test_similar_domain_does_not_count_as_ieee(self):
        merged, added = merge_rules("<local>;not-ieee.org;ieee.org.evil.example")
        self.assertEqual(added, ["ieee.org", "*.ieee.org"])
        self.assertIn("ieee.org.evil.example", merged)
if __name__ == "__main__":
    unittest.main()
