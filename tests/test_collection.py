import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from literature_helper import LiteratureHelper, HelperError, RateLimitError
from collection_workflow import CollectionManager, validate_plan
from browser_worker import classify, public_url, redacted_url, publisher_host


PDF=b'%PDF-1.4\nfixture\n%%EOF\n'


class FakeHelper(LiteratureHelper):
    def __init__(self, output):
        super().__init__(output)
        self.calls=[]
    def search(self, query, limit):
        return {'papers':[{'doi':'10.1000/a','title':'Ultrasonic flowmeter cycle skipping'},
                          {'doi':'10.1000/b','title':'Ultrasonic time of flight'}][:limit]}
    def lookup(self, doi):
        return {'paper':{'doi':doi,'title':'Fixture '+doi}}
    def download(self, identifier):
        self.calls.append(identifier)
        if identifier.endswith('/a'):
            return self._save_pdf(PDF,identifier,{'origin':'test'})
        return {'status':'FULLTEXT_NOT_SAVED'}


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.helper=FakeHelper(self.temp.name)
        self.manager=CollectionManager(self.helper)
    def tearDown(self):
        self.temp.cleanup()
    def create(self):
        return self.manager.create('超声波周跳',['ultrasonic flowmeter cycle skipping','ultrasonic time of flight'],start_worker=False)
    def test_translation_is_explicit(self):
        with self.assertRaisesRegex(HelperError,'NEED_QUERY_TRANSLATION'):
            validate_plan('请找超声文献',[],3,10)
    def test_english_direct(self):
        self.assertEqual(validate_plan('ultrasonic flowmeter',[],3,10),['ultrasonic flowmeter'])
    def test_bounded_and_english(self):
        for qs,n,m in [(['中文'],3,10),([''],3,10),(['a']*5,3,10),(['a'],11,10),(['a'],3,31)]:
            with self.assertRaises(HelperError): validate_plan('prompt',qs,n,m)
    def test_dedupe_and_queries_preserved(self):
        state=self.create()
        self.assertEqual(len(state['papers']),2)
        self.assertEqual(len(state['papers'][0]['matched_queries']),2)
        self.assertEqual(state['actual_pdf_count'],0)
    def test_actual_files_not_abstracts_count(self):
        state=self.create()
        self.assertTrue(self.manager.run_public(state))
        result=self.manager.status(state['session_id'])
        self.assertEqual(result['actual_pdf_count'],1)
        self.assertEqual(result['papers'][1]['status'],'BROWSER_PENDING')
        self.assertTrue(Path(result['papers'][0]['file']['path']).is_file())
    def test_rate_limit_preserves_saved_and_stops(self):
        state=self.create()
        original=self.helper.download
        def download(i):
            if i.endswith('/b'): raise RateLimitError('429')
            return original(i)
        with patch.object(self.helper,'download',side_effect=download):
            self.assertFalse(self.manager.run_public(state))
        self.assertEqual(state['status'],'STOPPED_RATE_LIMIT')
        self.assertEqual(self.manager.status(state['session_id'])['actual_pdf_count'],1)
    def test_resume_does_not_redownload_saved(self):
        state=self.create(); self.manager.run_public(state); self.manager.run_public(state)
        self.assertEqual(self.helper.calls,['10.1000/a','10.1000/b'])
    def test_bad_session_cannot_escape_root(self):
        for sid in ['../secret','A'*32,'abc','']:
            with self.assertRaises(HelperError): self.manager.load(sid)
    def test_action_is_persisted_and_bounded(self):
        state=self.create(); state['current_index']=0; self.manager.save(state); self.manager.action(state['session_id'],'skip')
        command=json.loads((self.manager.directory(state['session_id'])/'command.json').read_text())
        self.assertEqual(command['action'],'skip')
        with self.assertRaises(HelperError): self.manager.action(state['session_id'],'login_with_password')
    def test_skip_before_current_paper_is_rejected(self):
        state=self.create()
        with self.assertRaises(HelperError): self.manager.action(state['session_id'],'skip')
    def test_close_stops_public_queue(self):
        state=self.create(); self.manager.action(state['session_id'],'close')
        self.assertFalse(self.manager.run_public(state))
        self.assertEqual(state['status'],'CLOSED'); self.assertEqual(self.helper.calls,[])
    def test_unconfirmed_start_can_be_resumed(self):
        state=self.create(); state['status']='STARTING'; self.manager.save(state)
        from datetime import datetime,timezone,timedelta
        state['updated_at']=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
        from collection_workflow import atomic_json
        atomic_json(self.manager.directory(state['session_id'])/'state.json',state)
        self.assertEqual(self.manager.status(state['session_id'])['status'],'WORKER_ERROR')
    def test_html_escapes_untrusted_prompt_and_title(self):
        state=self.manager.create('<script>bad()</script>',['ultrasonic'],start_worker=False)
        page=Path(state['dashboard']).read_text(encoding='utf-8')
        self.assertNotIn('<script>',page)
        self.assertIn('&lt;script&gt;',page)
    def test_seed_doi_deduplication(self):
        result=self.manager.from_identifiers(['10.1000/a','10.1000/a'],start_worker=False)
        self.assertEqual(len(result['papers']),1)
    def test_public_error_is_not_permission_denied(self):
        state=self.create()
        with patch.object(self.helper,'download',side_effect=HelperError('network')):
            self.manager.run_public(state)
        self.assertTrue(all(p['status']=='ERROR' for p in state['papers']))


class EntitlementTests(unittest.TestCase):
    def test_institution_name_is_not_fulltext(self):
        self.assertEqual(classify({'doi':'10.1000/a','institution_recognized':True},'10.1000/a'),'ACCESS_UNKNOWN')
    def test_no_access_requires_identity_and_institution(self):
        self.assertEqual(classify({'doi':'10.1000/a','no_access':True},'10.1000/a'),'NEED_USER_AUTHENTICATION')
        self.assertEqual(classify({'doi':'10.1000/a','no_access':True,'institution_recognized':True},'10.1000/a'),'NO_ACCESS')
        self.assertEqual(classify({'doi':'10.1000/b','no_access':True,'institution_recognized':True},'10.1000/a'),'PAPER_IDENTITY_UNKNOWN')
    def test_pdf_candidate_not_yet_saved(self):
        self.assertEqual(classify({'doi':'10.1000/a','pdf_links':['https://example.org/a.pdf']},'10.1000/a'),'PDF_CANDIDATE')
    def test_challenge_and_password_take_precedence(self):
        for key, expected in [('challenge','CHALLENGE_REQUIRED'),('password_form','NEED_USER_AUTHENTICATION')]:
            self.assertEqual(classify({'pdf_links':['a'],key:True},'10.1000/a'),expected)
    def test_article_login_widget_does_not_hide_valid_pdf_candidate(self):
        self.assertEqual(classify({'doi':'10.1000/a','pdf_links':['a'],'password_form':True},'10.1000/a'),'PDF_CANDIDATE')
    def test_regular_browser_close_is_immediate(self):
        with tempfile.TemporaryDirectory() as directory:
            manager=CollectionManager(FakeHelper(directory))
            state=manager.create('prompt',['ultrasonic'],start_worker=False)
            state['backend']='regular_extension';manager.save(state)
            self.assertEqual(manager.action(state['session_id'],'close')['status'],'CLOSED')
    def test_private_url_and_host_spoof_rejected(self):
        for url in ['file:///secret','http://example.org/a.pdf','https://127.0.0.1/a','https://localhost/a','https://10.1.1.1/a','https://user:pass@www.sciencedirect.com/a','https://[::1]/a']:
            with self.assertRaises(HelperError): public_url(url)
        self.assertFalse(publisher_host('sciencedirect.com.evil.example'))
    def test_sensitive_query_not_recorded(self):
        self.assertEqual(redacted_url('https://www.sciencedirect.com/pdf/a?token=secret#x'),'https://www.sciencedirect.com/pdf/a')
        self.assertEqual(redacted_url('https://sso.example.org/private?SAMLResponse=secret'),'https://sso.example.org')


if __name__=='__main__': unittest.main()
