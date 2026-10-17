import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from literature_helper import HelperError
from service_launcher import main, resolve_paths, start_service


class ServiceLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.browser = Path(self.temp.name) / "browser"
        self.browser.mkdir()
        self.library = Path(self.temp.name) / "existing-library"
        self.config = self.browser / "service-launcher.json"
        self.config.write_text(json.dumps({"output_dir": str(self.library)}), encoding="utf-8")
        self.env = patch.dict(os.environ, {"LIT_OUTPUT_DIR": "", "LIT_BROWSER_DIR": ""})
        self.env.start()
    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()
    def test_reuses_local_library_without_making_new_collection(self):
        with patch("service_launcher.ensure_bridge", return_value={"token": "fixture-private", "pid": 123}) as bridge:
            result = start_service(browser_dir=self.browser)
        manager = bridge.call_args.args[0]
        self.assertEqual(manager.helper.output, self.library.resolve())
        self.assertEqual(manager.browser_dir, self.browser.resolve())
        self.assertFalse(manager.root.exists())
        self.assertNotIn("fixture-private", json.dumps(result))
        self.assertFalse(result["page_requested"])
    def test_explicit_output_wins_over_env_and_local_config(self):
        os.environ["LIT_OUTPUT_DIR"] = str(Path(self.temp.name) / "environment")
        output, _ = resolve_paths(Path(self.temp.name) / "explicit", self.browser)
        self.assertEqual(output.name, "explicit")
        output, _ = resolve_paths(browser_dir=self.browser)
        self.assertEqual(output.name, "environment")
    def test_pairing_page_uses_existing_token_but_return_is_redacted(self):
        with patch("service_launcher.ensure_bridge", return_value={"token": "fixture-private", "pid": 123}), patch("service_launcher.webbrowser.open", return_value=True) as open_page:
            result = start_service(browser_dir=self.browser, open_page=True)
        self.assertTrue(result["page_requested"])
        self.assertEqual(open_page.call_args.args[0], "http://127.0.0.1:8766/pair#fixture-private")
        self.assertNotIn("fixture-private", json.dumps(result))
    def test_invalid_config_stops_without_starting_service(self):
        self.config.write_text('{"output_dir": []}', encoding="utf-8")
        with patch("service_launcher.ensure_bridge") as bridge:
            with self.assertRaises(HelperError):
                start_service(browser_dir=self.browser)
        bridge.assert_not_called()
    def test_start_failure_does_not_expose_private_exception(self):
        stream = io.StringIO()
        with patch("service_launcher.start_service", side_effect=HelperError("private-fixture")), contextlib.redirect_stdout(stream):
            self.assertEqual(main([]), 1)
        self.assertNotIn("private-fixture", stream.getvalue())
    def test_no_auto_browser_without_open_flag(self):
        with patch("service_launcher.ensure_bridge", return_value={"token": "fixture-private"}), patch("service_launcher.webbrowser.open") as open_page:
            start_service(browser_dir=self.browser)
        open_page.assert_not_called()


if __name__ == "__main__":
    unittest.main()
