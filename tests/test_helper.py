"""无网络测试：验证文件保留、访问边界和错误处理。"""
import io
import json
from pathlib import Path
import sys
import shutil
import unittest
import uuid
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from literature_helper import (API_HOSTS, PDF_HOSTS, HelperError, LiteratureHelper,
                               PublicClient, checked_url, institutional_guide, normalize_doi)

PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"


class FakeClient:
    def __init__(self, record=None):
        self.record = record or {}
        self.calls = []

    def json(self, url):
        self.calls.append(url)
        if url.startswith('https://api.crossref.org/works/'):
            return {'message': {'DOI': unquote(url.split('/works/', 1)[1])}}
        return self.record

    def get(self, url, hosts, max_bytes):
        self.calls.append(url)
        return PDF, url


class HelperTests(unittest.TestCase):
    def setUp(self):
        # 临时验证工件也留在工具目录；兼容受限工作区。
        temp_root = Path(__file__).resolve().parents[1] / ".test-tmp"
        temp_root.mkdir(exist_ok=True)
        self.root = temp_root / uuid.uuid4().hex
        self.root.mkdir()
        self.inbox = self.root / "inbox"
        self.inbox.mkdir()
        self.client = FakeClient()
        self.helper = LiteratureHelper(self.root / "out", self.inbox, self.client)

    def tearDown(self):
        expected_root = Path(__file__).resolve().parents[1] / ".test-tmp"
        assert self.root.resolve().parent == expected_root.resolve()
        shutil.rmtree(self.root)

    def test_doi_url_and_case(self):
        self.assertEqual(normalize_doi("https://doi.org/10.3390/METROLOGY5040071"), "10.3390/metrology5040071")

    def test_invalid_identifier_never_requests(self):
        for value in ("file:///secret", "https://localhost/x", "bad", "arxiv:../../a"):
            with self.subTest(value=value), self.assertRaises(HelperError):
                self.helper.download(value)
        self.assertFalse(self.client.calls)

    def test_url_access_boundary(self):
        for value in ("http://arxiv.org/pdf/1", "https://localhost/a", "https://127.0.0.1/a",
                      "https://arxiv.org.evil.example/a", "https://user:pass@arxiv.org/a",
                      "https://arxiv.org:444/a", "file:///a", "https://webvpn.zju.edu.cn/a"):
            with self.subTest(value=value), self.assertRaises(HelperError):
                checked_url(value, PDF_HOSTS)

    def test_search_bounds_no_requests(self):
        for query, limit in (("", 1), ("x", 0), ("x", 11), ("x" * 501, 1)):
            with self.subTest(limit=limit), self.assertRaises(HelperError):
                self.helper.search(query, limit)
        self.assertFalse(self.client.calls)

    def test_missing_optional_metadata(self):
        self.client.record = {"message": {"items": [{"DOI": "10.1000/x"}]}}
        paper = self.helper.search("ultrasonic flow")["papers"][0]
        self.assertIsNone(paper["year"])
        self.assertEqual(paper["authors"], [])

    def test_missing_contact_does_not_send_request(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(self.helper.locate_oa("10.1000/x")["status"], "NEED_CONTACT_EMAIL")
        self.assertFalse(self.client.calls)

    def test_oa_location_unsupported_host_stays_manual(self):
        self.client.record = {"best_oa_location": {"url_for_pdf": "https://publisher.example/x.pdf"}}
        with patch.dict("os.environ", {"UNPAYWALL_EMAIL": "contact@example.org"}):
            result = self.helper.download("10.1000/x")
        self.assertFalse(result["automatic_download_supported"])
        self.assertEqual(len(self.client.calls), 2)
        self.assertTrue(all("api." in url for url in self.client.calls))
        self.assertNotIn("email", json.dumps(result))

    def test_oa_download_supported_source(self):
        self.client.record = {"best_oa_location": {"url_for_pdf": "https://arxiv.org/pdf/1706.03762"}}
        with patch.dict("os.environ", {"UNPAYWALL_EMAIL": "contact@example.org"}):
            result = self.helper.download("10.1000/x")
        self.assertEqual(result["status"], "SAVED")

    def test_pdf_validation(self):
        for body in (b"<html>login</html>", b"%PDF-1.4\ntruncated", b"%PDF-" + b"x" * (25 * 1024 * 1024)):
            with self.assertRaises(HelperError):
                self.helper._save_pdf(body, "x", {})
        self.assertFalse(self.helper.output.exists())

    def test_download_manifest_and_deduplication(self):
        first = self.helper.download("arxiv:1706.03762")
        second = self.helper.download("arxiv:1706.03762")
        self.assertEqual(first["status"], "SAVED")
        self.assertEqual(second["status"], "ALREADY_EXISTS")
        manifest = json.loads(Path(first["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["sha256"], first["sha256"])
        self.assertEqual(manifest["provenance"]["origin"], "public_oa")

    def test_inconsistent_existing_file_is_preserved(self):
        result = self.helper.download("arxiv:1706.03762")
        path = Path(result["path"])
        path.write_bytes(b"user existing content")
        with self.assertRaises(HelperError):
            self.helper.download("arxiv:1706.03762")
        self.assertEqual(path.read_bytes(), b"user existing content")

    def test_manual_import_keeps_source(self):
        source = self.inbox / "a.pdf"
        source.write_bytes(PDF)
        result = self.helper.import_pdf("a.pdf")
        self.assertEqual(result["status"], "SAVED")
        self.assertEqual(source.read_bytes(), PDF)

    def test_manual_import_cannot_escape(self):
        for value in ("../a.pdf", "..\\a.pdf", "C:\\a.pdf", "/a.pdf", "x:y.pdf"):
            with self.subTest(value=value), self.assertRaises(HelperError):
                self.helper.import_pdf(value)

    def test_manual_guide_no_authentication(self):
        result = institutional_guide("10.1000/x")
        self.assertEqual(result["status"], "MANUAL_INSTITUTIONAL_ACCESS")
        self.assertIn("webvpn.zju.edu.cn", result["webvpn"])


class TransportTests(unittest.TestCase):
    def client_with_open(self, fn):
        client = PublicClient()
        client.opener.open = fn
        return client

    def test_redirect_to_private_address_rejected_before_second_request(self):
        calls = []
        def call(req, timeout):
            calls.append(req.full_url)
            raise HTTPError(req.full_url, 302, "redirect", {"Location": "https://127.0.0.1/a"}, io.BytesIO())
        client = self.client_with_open(call)
        with self.assertRaises(HelperError):
            client.get("https://arxiv.org/pdf/x", PDF_HOSTS, 100)
        self.assertEqual(len(calls), 1)

    def test_rate_limit_no_retry_or_email_leak(self):
        calls = []
        def call(req, timeout):
            calls.append(req.full_url)
            raise HTTPError(req.full_url, 429, "limit", {"Retry-After": "60"}, io.BytesIO())
        client = self.client_with_open(call)
        with self.assertRaises(HelperError) as caught:
            client.get("https://api.unpaywall.org/v2/10.1000/x?email=private@example.org", API_HOSTS, 100)
        self.assertNotIn("private@example.org", str(caught.exception))
        self.assertEqual(len(calls), 1)

    def test_response_size_limit(self):
        response = io.BytesIO(b"x" * 11)
        response.geturl = lambda: "https://api.crossref.org/works"
        client = self.client_with_open(lambda req, timeout: response)
        with self.assertRaises(HelperError):
            client.get("https://api.crossref.org/works", API_HOSTS, 10)


if __name__ == "__main__":
    unittest.main()
