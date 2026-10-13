"""自动全文收集、候选退避及逐篇结果：无网络，使用有状态来源响应。"""
import json
from pathlib import Path
import shutil
import sys
import unittest
import uuid
from urllib.parse import unquote
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from literature_helper import (AccessPageRequired, CandidateUnavailable, HelperError,
                               LiteratureHelper, RateLimitError)

PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"
SCITEPRESS = "10.5220/0007535905680572"
SD = "10.1016/0041-624x(71)90200-9"
FIRST = "https://arxiv.org/pdf/1706.03762"
SECOND = "https://arxiv.org/pdf/1706.03762v1"


def scitepress_work():
    return {"DOI": SCITEPRESS, "title": ["Construction of a Ultrasonic Gas Flowmeter"],
            "published": {"date-parts": [[2018]]},
            "resource": {"primary": {"URL": "http://www.scitepress.org/DigitalLibrary/Link.aspx?doi=" + SCITEPRESS}}}


class Sources:
    def __init__(self):
        self.works = {SCITEPRESS: scitepress_work(), SD: {"DOI": SD}}
        self.oa = {}
        self.items = []
        self.json_calls, self.pdf_calls = [], []
        self.responses = {}

    def json(self, url):
        self.json_calls.append(url)
        if url.startswith('https://api.crossref.org/works?'):
            return {"message": {"items": self.items}}
        if url.startswith('https://api.crossref.org/works/'):
            doi = unquote(url.split('/works/', 1)[1])
            return {"message": self.works.get(doi, {"DOI": doi})}
        if url.startswith('https://api.unpaywall.org/v2/'):
            doi = unquote(url.split('/v2/', 1)[1].split('?', 1)[0])
            return self.oa.get(doi, {})
        raise AssertionError(url)

    def get(self, url, hosts, max_bytes):
        self.pdf_calls.append(url)
        value = self.responses.get(url, PDF)
        if isinstance(value, Exception):
            raise value
        return value, url


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.parent = Path(__file__).resolve().parents[1] / '.test-tmp'
        self.parent.mkdir(exist_ok=True)
        self.root = self.parent / uuid.uuid4().hex
        self.root.mkdir()
        self.client = Sources()
        self.helper = LiteratureHelper(self.root / 'out', self.root / 'inbox', self.client)
        self.env = patch.dict('os.environ', {}, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        assert self.root.resolve().parent == self.parent.resolve()
        shutil.rmtree(self.root)

    def test_scitepress_without_contact_or_account_saves_actual_pdf(self):
        with patch('literature_helper.webbrowser.open') as browser:
            result = self.helper.collect(SCITEPRESS)
        self.assertEqual(result['status'], 'SAVED')
        self.assertEqual(self.client.pdf_calls, ['https://www.scitepress.org/Papers/2018/75359/75359.pdf'])
        self.assertEqual(Path(result['path']).read_bytes(), PDF)
        evidence = json.loads(Path(result['manifest']).read_text(encoding='utf-8'))['provenance']['evidence']
        self.assertEqual(evidence['source'], 'SciTePress')
        self.assertIn('路径约定', evidence['candidate_basis'])
        browser.assert_not_called()

    def test_crossref_wrong_doi_stops_before_download(self):
        self.client.works[SCITEPRESS]['DOI'] = '10.5220/0000000100010002'
        with self.assertRaises(HelperError):
            self.helper.download(SCITEPRESS)
        self.assertFalse(self.client.pdf_calls)

    def test_scitepress_does_not_construct_path_for_untrusted_metadata(self):
        self.client.works[SCITEPRESS]['resource']['primary']['URL'] = 'https://evil.test/x'
        result = self.helper.download(SCITEPRESS)
        self.assertEqual(result['status'], 'FULLTEXT_NOT_SAVED')
        self.assertFalse(self.client.pdf_calls)

    def test_free_personal_account_is_distinct_from_institutional_access(self):
        url = 'https://www.scitepress.org/Papers/2018/75359/75359.pdf'
        self.client.responses[url] = AccessPageRequired('HTTP 403')
        result = self.helper.collect(SCITEPRESS, open_browser=False)
        self.assertEqual(result['publisher_account']['type'], 'FREE_PERSONAL_ACCOUNT_IF_REQUIRED')
        self.assertEqual(result['subscription_access'], 'UNKNOWN')
        self.assertNotIn('browser', result['access'])

    def test_other_supported_oa_location_used_when_best_is_unsupported(self):
        self.client.oa[SD] = {'best_oa_location': {'url_for_pdf': 'https://unsupported.example/a.pdf'},
                              'oa_locations': [{'url_for_pdf': FIRST}]}
        with patch.dict('os.environ', {'UNPAYWALL_EMAIL': 'contact@example.org'}):
            result = self.helper.download(SD)
        self.assertEqual(result['status'], 'SAVED')
        self.assertEqual(self.client.pdf_calls, [FIRST])
        self.assertEqual(len(self.client.json_calls), 1)

    def test_unavailable_first_candidate_uses_second_declared_location(self):
        self.client.oa[SD] = {'best_oa_location': {'url_for_pdf': FIRST},
                              'oa_locations': [{'url_for_pdf': FIRST}, {'url_for_pdf': SECOND}]}
        self.client.responses[FIRST] = CandidateUnavailable('HTTP 404')
        with patch.dict('os.environ', {'UNPAYWALL_EMAIL': 'contact@example.org'}):
            result = self.helper.download(SD)
        self.assertEqual(result['status'], 'SAVED')
        self.assertEqual(self.client.pdf_calls, [FIRST, SECOND])
        self.assertEqual(result['attempts'][0]['status'], 'CANDIDATE_UNAVAILABLE')

    def test_html_login_response_is_not_saved_as_pdf(self):
        self.client.responses['https://www.scitepress.org/Papers/2018/75359/75359.pdf'] = b'<html>login</html>'
        result = self.helper.download(SCITEPRESS)
        self.assertEqual(result['status'], 'FULLTEXT_NOT_SAVED')
        self.assertFalse(self.helper.output.exists())

    def test_rate_limit_stops_without_alternate_source_or_browser(self):
        self.client.oa[SD] = {'best_oa_location': {'url_for_pdf': FIRST}, 'oa_locations': [{'url_for_pdf': SECOND}]}
        self.client.responses[FIRST] = RateLimitError('429')
        with patch.dict('os.environ', {'UNPAYWALL_EMAIL': 'contact@example.org'}), patch('literature_helper.webbrowser.open') as browser:
            with self.assertRaises(RateLimitError):
                self.helper.collect(SD)
        self.assertEqual(self.client.pdf_calls, [FIRST])
        self.assertEqual(len(self.client.json_calls), 1)
        browser.assert_not_called()

    def test_three_candidate_limit_is_enforced(self):
        urls = ['https://arxiv.org/pdf/1706.03762v' + str(i) for i in range(1, 6)]
        self.client.oa[SD] = {'oa_locations': [{'url_for_pdf': u} for u in urls]}
        self.client.responses.update({u: CandidateUnavailable('404') for u in urls})
        with patch.dict('os.environ', {'UNPAYWALL_EMAIL': 'contact@example.org'}):
            result = self.helper.download(SD)
        self.assertEqual(result['status'], 'FULLTEXT_NOT_SAVED')
        self.assertEqual(len(self.client.pdf_calls), 3)

    def test_not_subscribed_does_not_open_repeat_login_and_reports_unchecked_query(self):
        with patch('literature_helper.webbrowser.open') as browser:
            result = self.helper.collect(SD, access_state='not_subscribed')
        browser.assert_not_called()
        self.assertEqual(result['status'], 'MANUAL_REQUIRED')
        self.assertEqual(result['subscription_access'], 'NOT_SUBSCRIBED_USER_REPORTED')
        self.assertNotIn('access', result)
        self.assertEqual(result['open_access_result']['checks'][0]['status'], 'NEED_CONTACT_EMAIL')
        self.assertIn('library_document_delivery', result['fallback'])

    def test_tdm_license_does_not_authorize_automatic_fulltext(self):
        self.client.works[SD].update({'link': [{'URL': FIRST, 'content-type': 'application/pdf', 'content-version': 'vor'}],
            'license': [{'URL': 'https://www.elsevier.com/tdm/userlicense/1.0/', 'content-version': 'tdm', 'start': {'date-parts': [[1971,4,1]]}}]})
        self.assertEqual(self.helper.download(SD)['status'], 'FULLTEXT_NOT_SAVED')
        self.assertFalse(self.client.pdf_calls)

    def test_matching_current_cc_license_permits_declared_public_pdf(self):
        self.client.works[SD].update({'link': [{'URL': FIRST, 'content-type': 'application/pdf', 'content-version': 'vor'}],
            'license': [{'URL': 'https://creativecommons.org/licenses/by/4.0/', 'content-version': 'vor', 'start': {'date-parts': [[2020,1,1]]}}]})
        self.assertEqual(self.helper.download(SD)['status'], 'SAVED')
        self.assertEqual(self.client.pdf_calls, [FIRST])

    def test_future_or_different_version_license_is_not_accepted(self):
        for date, version in [([2099,1,1], 'vor'), ([2020,1,1], 'am')]:
            self.client.works[SD].update({'link': [{'URL': FIRST, 'content-type': 'application/pdf', 'content-version': 'vor'}],
                'license': [{'URL': 'https://creativecommons.org/licenses/by/4.0/', 'content-version': version, 'start': {'date-parts': [date]}}]})
            self.assertEqual(self.helper.download(SD)['status'], 'FULLTEXT_NOT_SAVED')
        self.assertFalse(self.client.pdf_calls)

    def test_collection_pipeline_saves_pdf_and_reports_pending_separately(self):
        self.client.items = [self.client.works[SCITEPRESS], self.client.works[SD]]
        with patch('literature_helper.webbrowser.open') as browser:
            result = self.helper.reading_list('ultrasonic', collect_fulltext=True)
        browser.assert_not_called()
        self.assertEqual(result['collection_summary'], {'SAVED': 1, 'USER_BROWSER_ACTION_REQUIRED': 1})
        records = json.loads(Path(result['manifest']).read_text(encoding='utf-8'))
        self.assertEqual(records['papers'][0]['collection']['status'], 'SAVED')
        page = Path(result['path']).read_text(encoding='utf-8')
        self.assertIn('打开已保存PDF', page)
        self.assertIn('全文未保存', page)
        self.assertIn('普通联系邮箱', page)

    def test_pipeline_limit_stops_remaining_and_preserves_partial_files(self):
        third = '10.1000/third'
        self.client.items = [self.client.works[SCITEPRESS], self.client.works[SD], {'DOI': third}]
        self.client.oa[SCITEPRESS] = {'best_oa_location': {'url_for_pdf': FIRST}}
        self.client.oa[SD] = {'best_oa_location': {'url_for_pdf': SECOND}}
        self.client.responses[SECOND] = RateLimitError('429')
        with patch.dict('os.environ', {'UNPAYWALL_EMAIL': 'contact@example.org'}):
            result = self.helper.reading_list('ultrasonic', collect_fulltext=True)
        self.assertEqual(result['pipeline_status'], 'STOPPED_RATE_LIMIT')
        self.assertEqual(result['collection_summary'], {'NOT_ATTEMPTED':1, 'RATE_LIMITED':1, 'SAVED':1})
        self.assertEqual(len(list(self.helper.output.glob('*.pdf'))),1)
        self.assertFalse(any('third' in url for url in self.client.json_calls))

    def test_duplicate_doi_is_not_collected_twice(self):
        self.client.items = [self.client.works[SCITEPRESS], self.client.works[SCITEPRESS]]
        result = self.helper.reading_list('ultrasonic', collect_fulltext=True)
        self.assertEqual(result['collection_summary'], {'DUPLICATE_SKIPPED':1, 'SAVED':1})
        self.assertEqual(len(self.client.pdf_calls),1)


if __name__ == '__main__':
    unittest.main()
