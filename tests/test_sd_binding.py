import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError
from literature_helper import LiteratureHelper, HelperError, summarize
from collection_workflow import CollectionManager
from normal_browser import RegularBridge, handler_for

DOI = "10.1016/j.measurement.2019.07.014"
PII = "S0263224119306359"
PRIMARY = "https://linkinghub.elsevier.com/retrieve/pii/" + PII
CANONICAL = "https://www.sciencedirect.com/science/article/pii/" + PII

class ScienceDirectMetadataTests(unittest.TestCase):
    def paper(self, url, **extra):
        return summarize({"DOI": DOI, "resource": {"primary": {"URL": url}}, **extra})
    def test_trusted_primary_preserves_stable_id_without_query(self):
        for url in [PRIMARY, CANONICAL, CANONICAL.replace('/article/', '/article/abs/')]:
            paper = self.paper(url + '?private=unused')
            self.assertEqual(paper['publisher_pii'], PII)
            self.assertEqual(paper['publisher_article_url'], CANONICAL)
            self.assertNotIn('private', str(paper))
    def test_untrusted_conflicting_or_incomplete_metadata_is_not_binding(self):
        for url in [PRIMARY.replace('https:', 'http:'), PRIMARY.replace('elsevier.com', 'elsevier.com.evil.example'), PRIMARY.replace('://', '://user:secret@'), PRIMARY.replace('/retrieve/', '/other/'), PRIMARY + '/pdf', PRIMARY.replace(PII, 'S123')]:
            self.assertNotIn('publisher_pii', self.paper(url))
        self.assertNotIn('publisher_pii', self.paper(PRIMARY, DOI='10.1000/wrong'))
        self.assertNotIn('publisher_pii', self.paper(PRIMARY, **{'alternative-id': ['S0263224119306358']}))
        self.assertNotIn('publisher_pii', summarize({'DOI': DOI, 'alternative-id': [PII]}))

class BindingBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = CollectionManager(LiteratureHelper(self.root/'library'), self.root/'browser')
        self.bridge = RegularBridge(self.manager, self.root/'downloads')
        self.state = self.manager._create('试验', ['delay'], [], [{'doi': DOI, 'identifier': DOI, 'article_url': 'https://doi.org/'+DOI, 'title': '试验', 'status': 'ACCESS_UNKNOWN'}], False, False)
        self.state.update(backend='regular_extension', status='ACCESS_UNKNOWN', current_index=0)
        self.manager.save(self.state)
        self.data = {'session_id': self.state['session_id'], 'index': 0}
    def tearDown(self):
        self.temp.cleanup()
    def metadata(self):
        return {'paper': {'doi': DOI, 'publisher_pii': PII, 'publisher_article_url': CANONICAL}}
    def test_resolve_persists_and_reuses_trusted_binding_without_changing_progress(self):
        with patch.object(self.manager.helper, 'lookup', return_value=self.metadata()) as lookup:
            first = self.bridge.paper_binding(self.data)
            second = self.bridge.paper_binding(self.data)
        self.assertEqual(first, second)
        lookup.assert_called_once_with(DOI)
        state = self.manager.load(self.data['session_id'])
        self.assertEqual(state['papers'][0]['status'], 'ACCESS_UNKNOWN')
        self.assertEqual(state['papers'][0]['publisher_binding']['source'], 'Crossref')
        self.assertEqual(state['current_index'], 0)
    def test_binding_doi_and_primary_conflicts_rejected(self):
        metadata = self.metadata(); metadata['paper']['doi'] = '10.1000/wrong'
        with patch.object(self.manager.helper, 'lookup', return_value=metadata), self.assertRaises(HelperError):
            self.bridge.paper_binding(self.data)
        metadata = self.metadata(); metadata['paper']['publisher_article_url'] = CANONICAL.replace(PII, 'S0263224119306358')
        with patch.object(self.manager.helper, 'lookup', return_value=metadata):
            self.assertEqual(self.bridge.paper_binding(self.data)['status'], 'UNKNOWN')
        self.assertNotIn('publisher_binding', self.manager.load(self.data['session_id'])['papers'][0])
    def test_late_lookup_does_not_overwrite_skip_or_other_paper_progress(self):
        def lookup(_):
            self.bridge.update({**self.data, 'status': 'SKIPPED_BY_USER'})
            return self.metadata()
        with patch.object(self.manager.helper, 'lookup', side_effect=lookup), self.assertRaises(HelperError):
            self.bridge.paper_binding(self.data)
        self.assertEqual(self.manager.load(self.data['session_id'])['papers'][0]['status'], 'SKIPPED_BY_USER')
    def test_skips_stay_terminal_for_stale_observation_completion_and_bytes(self):
        for skipped in ['SKIPPED_BY_USER', 'SKIPPED_NO_ACCESS']:
            self.state['papers'][0]['status'] = skipped; self.manager.save(self.state)
            before = self.manager.directory(self.data['session_id']).joinpath('state.json').read_bytes()
            self.bridge.update({**self.data, 'status': 'DOWNLOADING', 'identity_matched': True})
            self.bridge.update({**self.data, 'download_path': 'missing.pdf'}, True)
            self.bridge.receive_pdf(self.data['session_id'], 0, b'%PDF-1.4\nfixture\n%%EOF', 'DOCUMENT_LINK')
            after = self.manager.directory(self.data['session_id']).joinpath('state.json').read_bytes()
            self.assertEqual(before, after)
    def test_diagnostic_keeps_only_enumerated_non_secret_fields(self):
        data = {'result': 'PII_MISMATCH', 'extension_version': '0.5.4', 'active_session': self.data['session_id'],
                'expected_pii': PII, 'observed_pii': 'S0263224119306358', 'page_kind': 'SD_PDF',
                'url': 'https://example.invalid/?signed=secret', 'cookie': 'secret', 'password': 'secret'}
        for _ in range(12): self.bridge.extension_diagnostic(data)
        rows = json.loads((self.manager.browser_dir/'extension-diagnostic.json').read_text(encoding='utf-8'))
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[-1]['expected_pii'], PII)
        self.assertNotIn('secret', json.dumps(rows))
        self.assertNotIn('url', rows[-1])
        with self.assertRaises(HelperError): self.bridge.extension_diagnostic({'result': 'https://secret.invalid'})

    def test_diagnostic_http_requires_capability(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.bridge, 'fixture-token'))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        client = build_opener(ProxyHandler({})); url = 'http://127.0.0.1:'+str(server.server_port)+'/extension-diagnostic'
        payload = json.dumps({'result': 'POPUP', 'extension_version': '0.5.4'}).encode()
        try:
            with self.assertRaises(HTTPError) as caught: client.open(Request(url, data=payload))
            self.assertEqual(caught.exception.code, 401)
            self.assertFalse((self.manager.browser_dir/'extension-diagnostic.json').exists())
            with client.open(Request(url, data=payload, headers={'Authorization':'Bearer fixture-token'})) as response:
                self.assertEqual(json.load(response)['status'], 'RECORDED')
        finally:
            server.shutdown(); server.server_close()

    def test_endpoint_requires_local_capability_and_valid_pending_index(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.bridge, 'fixture-token'))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        client = build_opener(ProxyHandler({})); url = 'http://127.0.0.1:'+str(server.server_port)+'/paper-binding'
        def call(data, auth=True):
            return client.open(Request(url, data=json.dumps(data).encode(), headers={'Content-Type':'application/json', **({'Authorization':'Bearer fixture-token'} if auth else {})}))
        try:
            with self.assertRaises(HTTPError) as caught: call(self.data, False)
            self.assertEqual(caught.exception.code, 401)
            with patch.object(self.manager.helper, 'lookup', return_value=self.metadata()) as lookup:
                for index in [-1, True, 99]:
                    with self.assertRaises(HTTPError): call({**self.data, 'index': index})
                lookup.assert_not_called()
                with call(self.data) as result:
                    self.assertEqual(json.load(result)['publisher_pii'], PII)
        finally:
            server.shutdown(); server.server_close()

if __name__ == '__main__': unittest.main()
