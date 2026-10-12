"""文献清单及本人浏览器认证流程，不访问真实账户。"""
import io
import json
from pathlib import Path
import shutil
import sys
import unittest
import uuid
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from literature_helper import (AccessPageRequired, HelperError, LiteratureHelper,
                               PublicClient, API_HOSTS, open_access_page)

PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"


class FakeClient:
    def __init__(self, record=None):
        self.record = record or {}
        self.calls = []

    def json(self, url):
        self.calls.append(url)
        return self.record

    def get(self, url, hosts, max_bytes):
        self.calls.append(url)
        return PDF, url


class BrowserWorkflowTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parents[1] / '.test-tmp'
        parent.mkdir(exist_ok=True)
        self.root = parent / uuid.uuid4().hex
        self.root.mkdir()
        self.client = FakeClient({'message': {'items': [
            {'DOI': '10.1000/test', 'title': ['A useful paper'],
             'container-title': ['Journal'], 'published': {'date-parts': [[2024]]}}
        ]}})
        self.helper = LiteratureHelper(self.root / 'out', self.root / 'inbox', self.client)

    def tearDown(self):
        parent = Path(__file__).resolve().parents[1] / '.test-tmp'
        assert self.root.resolve().parent == parent.resolve()
        shutil.rmtree(self.root)

    def test_reading_list_escapes_metadata_and_ignores_supplied_links(self):
        paper = self.client.record['message']['items'][0]
        paper.update({'title': ['<script>alert(1)</script>'], 'URL': 'javascript:alert(2)'})
        with patch('literature_helper.webbrowser.open') as browser:
            result = self.helper.reading_list('<img src=x onerror=alert(3)>')
        browser.assert_not_called()
        body = Path(result['path']).read_text(encoding='utf-8')
        self.assertNotIn('<script>', body)
        self.assertNotIn('<img', body)
        self.assertNotIn('javascript:', body)
        self.assertIn('&lt;script&gt;', body)
        self.assertIn('https://doi.org/10.1000/test', body)
        self.assertEqual(result['authentication'], 'UNKNOWN')
        manifest = json.loads(Path(result['manifest']).read_text(encoding='utf-8'))
        self.assertEqual(manifest['papers'][0]['doi'], '10.1000/test')

    def test_reading_lists_do_not_overwrite_and_failure_keeps_results(self):
        first = self.helper.reading_list('first')
        content = Path(first['path']).read_bytes()
        with patch('literature_helper.webbrowser.open', return_value=False):
            second = self.helper.reading_list('second', open_browser=True)
        self.assertNotEqual(first['path'], second['path'])
        self.assertEqual(Path(first['path']).read_bytes(), content)
        self.assertEqual(second['browser']['status'], 'BROWSER_OPEN_FAILED')
        self.assertTrue(Path(second['manifest']).is_file())

    def test_access_opens_official_route_without_claiming_login(self):
        with patch('literature_helper.webbrowser.open', return_value=True) as browser:
            result = open_access_page('10.1000/a?next=<bad>', 'carsi')
        browser.assert_called_once_with('https://ds.carsi.edu.cn/', new=2)
        self.assertEqual(result['browser']['status'], 'BROWSER_OPEN_REQUESTED')
        self.assertEqual(result['authentication'], 'UNKNOWN')
        self.assertEqual(result['subscription_access'], 'UNKNOWN')
        self.assertEqual(result['article_url'], 'https://doi.org/10.1000/a%3Fnext%3D%3Cbad%3E')

    def test_invalid_access_never_opens_browser(self):
        with patch('literature_helper.webbrowser.open') as browser:
            for doi, route in [('file:///secret', 'article'), ('10.1000/x', 'https://evil.test/')]:
                with self.subTest(doi=doi), self.assertRaises(HelperError):
                    open_access_page(doi, route)
        browser.assert_not_called()

    def test_collect_missing_email_opens_article_and_never_sends_credentials(self):
        with patch.dict('os.environ', {}, clear=True), patch('literature_helper.webbrowser.open', return_value=True) as browser:
            result = self.helper.collect('10.1000/test')
        browser.assert_called_once_with('https://doi.org/10.1000/test', new=2)
        self.assertFalse(self.client.calls)
        self.assertEqual(result['status'], 'USER_BROWSER_ACTION_REQUIRED')
        self.assertEqual(result['open_access_result']['status'], 'NEED_CONTACT_EMAIL')
        self.assertEqual(result['access']['authentication'], 'UNKNOWN')

    def test_collect_open_fulltext_does_not_open_browser(self):
        self.client.record = {'best_oa_location': {'url_for_pdf': 'https://arxiv.org/pdf/1706.03762'}}
        with patch.dict('os.environ', {'UNPAYWALL_EMAIL': 'contact@example.org'}), patch('literature_helper.webbrowser.open') as browser:
            result = self.helper.collect('10.1000/test')
        browser.assert_not_called()
        self.assertEqual(result['status'], 'SAVED')

    def test_collect_no_open_returns_action_without_changing_browser(self):
        with patch.dict('os.environ', {}, clear=True), patch('literature_helper.webbrowser.open') as browser:
            result = self.helper.collect('10.1000/test', open_browser=False, route='webvpn')
        browser.assert_not_called()
        self.assertEqual(result['access']['url'], 'https://webvpn.zju.edu.cn/')
        self.assertNotIn('browser', result['access'])

    def test_collect_does_not_treat_network_or_rate_limit_as_login(self):
        with patch('literature_helper.webbrowser.open') as browser:
            for reason in ('网络连接失败', '来源限流429'):
                with self.subTest(reason=reason), patch.object(self.helper, 'download', side_effect=HelperError(reason)):
                    with self.assertRaises(HelperError):
                        self.helper.collect('10.1000/test')
        browser.assert_not_called()

    def test_http_access_codes_allow_human_review_but_do_not_confirm_authentication(self):
        for code in (401, 403):
            client = PublicClient()
            def fail(req, timeout):
                raise HTTPError(req.full_url, code, 'restricted', {}, io.BytesIO())
            client.opener.open = fail
            with self.subTest(code=code), self.assertRaises(AccessPageRequired) as caught:
                client.get('https://api.crossref.org/works', API_HOSTS, 100)
            with patch.object(self.helper, 'download', side_effect=caught.exception):
                result = self.helper.collect('10.1000/test', open_browser=False)
            self.assertEqual(result['open_access_result']['status'], 'ACCESS_CHECK_REQUIRED')
            self.assertEqual(result['access']['authentication'], 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
