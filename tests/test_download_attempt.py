import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError
from literature_helper import LiteratureHelper, HelperError
from collection_workflow import CollectionManager
from normal_browser import RegularBridge, handler_for

DOI='10.1016/j.measurement.2019.07.014'
PII='S0263224119306359'
ARTICLE='https://www.sciencedirect.com/science/article/pii/'+PII

class DownloadAttemptTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.manager=CollectionManager(LiteratureHelper(self.root/'library'),self.root/'browser')
        self.bridge=RegularBridge(self.manager,self.root/'downloads')
        self.state=self.manager._create('试验',['delay'],[],[{'doi':DOI,'identifier':DOI,'title':'试验','article_url':'https://doi.org/'+DOI,'status':'ACCESS_UNKNOWN','publisher_binding':{'doi':DOI,'source':'Crossref','publisher_pii':PII,'publisher_article_url':ARTICLE}}],False,False)
        self.state.update(backend='regular_extension',status='ACCESS_UNKNOWN',current_index=0);self.manager.save(self.state)
        self.data={'session_id':self.state['session_id'],'index':0}
    def tearDown(self): self.temp.cleanup()
    def begin(self): return self.bridge.download_attempt({**self.data,'action':'begin'})['attempt']['id']
    def observe(self,attempt,status,**extra): return self.bridge.update({**self.data,'attempt_id':attempt,'status':status,'identity_matched':True,**extra})
    def test_explicit_new_attempt_ignores_old_notifications(self):
        first=self.begin();self.observe(first,'ACCESS_UNKNOWN',failure_code='FETCH_PDF')
        second=self.begin();self.assertNotEqual(first,second)
        self.observe(second,'DOWNLOADING');self.observe(first,'ACCESS_UNKNOWN',failure_code='FETCH_PDF')
        state=self.manager.load(self.data['session_id']);self.assertEqual(state['papers'][0]['status'],'DOWNLOADING');self.assertEqual(state['papers'][0]['active_attempt']['id'],second)
    def test_late_article_observation_cannot_replace_downloading(self):
        attempt=self.begin();self.observe(attempt,'DOWNLOADING')
        for status in ['ACCESS_UNKNOWN','NEED_USER_AUTHENTICATION','CHALLENGE_REQUIRED']:
            result=self.observe(attempt,status);self.assertEqual(result['papers'][0]['status'],'DOWNLOADING')
        self.assertEqual(self.observe(attempt,'ACCESS_UNKNOWN',failure_code='FETCH_PDF')['papers'][0]['status'],'ACCESS_UNKNOWN')
    def test_busy_attempt_not_restarted_until_stale(self):
        attempt=self.begin();self.observe(attempt,'DOWNLOADING')
        result=self.bridge.download_attempt({**self.data,'action':'begin'});self.assertEqual(result['status'],'BUSY');self.assertEqual(result['attempt']['id'],attempt)
        state=self.manager.load(self.data['session_id']);state['papers'][0]['active_attempt']['started_at']=(datetime.now(timezone.utc)-timedelta(seconds=91)).isoformat();self.manager.save(state)
        self.assertNotEqual(self.begin(),attempt)
    def test_wrong_attempt_pdf_rejected_current_attempt_saves(self):
        first=self.begin();second=self.begin();self.observe(second,'DOWNLOADING')
        body=b'%PDF-1.4\nfixture\n%%EOF'
        with self.assertRaises(HelperError):self.bridge.receive_pdf(self.data['session_id'],0,body,'DOCUMENT_LINK',first)
        with self.assertRaises(HelperError):self.bridge.receive_pdf(self.data['session_id'],0,body,'DOCUMENT_LINK')
        result=self.bridge.receive_pdf(self.data['session_id'],0,body,'DOCUMENT_LINK',second);self.assertEqual(result['actual_pdf_count'],1)
    def test_old_extension_observation_cannot_overwrite_new_attempt(self):
        attempt=self.begin();self.observe(attempt,'DOWNLOADING')
        result=self.bridge.update({**self.data,'status':'ACCESS_UNKNOWN','identity_matched':True});self.assertEqual(result['papers'][0]['status'],'DOWNLOADING')
        with self.assertRaises(HelperError):self.bridge.update({**self.data,'download_path':'missing.pdf'},True)
    def test_expired_link_can_return_only_once_to_same_registered_article(self):
        attempt=self.begin();data={**self.data,'action':'refresh-link','attempt_id':attempt}
        result=self.bridge.download_attempt(data);self.assertEqual(result['article_url'],ARTICLE);self.assertEqual(result['attempt']['link_refreshes'],1)
        self.assertEqual(self.bridge.download_attempt(data)['status'],'EXHAUSTED')
        with self.assertRaises(HelperError):self.bridge.download_attempt({**data,'attempt_id':'0'*32})
        state=self.manager.load(self.data['session_id']);state['papers'][0]['publisher_binding']['publisher_article_url']='https://evil.example/pii/'+PII;self.manager.save(state)
        attempt=self.begin()
        with self.assertRaises(HelperError):self.bridge.download_attempt({**data,'attempt_id':attempt})
    def test_diagnostic_records_only_enumerated_transfer_detail(self):
        self.bridge.extension_diagnostic({'result':'TRANSFER_FAILED','phase':'FETCH','reason':'HTTP_ERROR','http_status':403,'mime_kind':'HTML','link_state':'LIVE','url':'https://example.invalid/?secret=secret','headers':{'Cookie':'secret'}})
        row=json.loads((self.manager.browser_dir/'extension-diagnostic.json').read_text(encoding='utf-8'))[-1]
        self.assertEqual(row['http_status'],403);self.assertEqual(row['reason'],'HTTP_ERROR');self.assertNotIn('secret',json.dumps(row))
    def test_attempt_endpoint_requires_pairing_and_valid_action(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(self.bridge,'fixture-token'));threading.Thread(target=server.serve_forever,daemon=True).start()
        client=build_opener(ProxyHandler({}));url='http://127.0.0.1:'+str(server.server_port)+'/download-attempt'
        def call(data,auth=True):return client.open(Request(url,data=json.dumps(data).encode(),headers=({'Authorization':'Bearer fixture-token'} if auth else {})))
        try:
            with self.assertRaises(HTTPError) as caught:call({**self.data,'action':'begin'},False)
            self.assertEqual(caught.exception.code,401)
            with self.assertRaises(HTTPError):call({**self.data,'action':'arbitrary'})
            with call({**self.data,'action':'begin'}) as response:self.assertEqual(json.load(response)['status'],'READY')
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
