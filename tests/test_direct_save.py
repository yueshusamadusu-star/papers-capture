import json
from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
import unittest
from collection_workflow import CollectionManager
from literature_helper import LiteratureHelper, HelperError, PdfResponseError
from normal_browser import RegularBridge,handler_for

PDF=b'%PDF-1.4\nfixture\n%%EOF'
class DirectSaveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.manager=CollectionManager(LiteratureHelper(self.root/'library'),self.root/'private')
        self.bridge=RegularBridge(self.manager,self.root/'Downloads')
        self.state=self.manager._create('试验',['ultrasonic'],[],[{'doi':'10.1000/a','identifier':'10.1000/a','title':'中文论文: Air / Flow?','article_url':'https://doi.org/10.1000/a','status':'DOWNLOADING','browser_evidence':{'identity_matched':True}}],False,False)
        self.state['backend']='regular_extension';self.manager.save(self.state);self.sid=self.state['session_id']
    def tearDown(self):self.temp.cleanup()
    def save(self,body=PDF):return self.bridge.receive_pdf(self.sid,0,body,'PDF_RESPONSE')
    def test_directory_persists_and_keeps_other_private_settings(self):
        self.manager.browser_dir.mkdir();p=self.manager.browser_dir/'settings.json'
        p.write_text(json.dumps({'download_directory':str(self.root/'Downloads'),'other':'keep'}))
        target=self.root/'我选择的目录'
        self.assertEqual(self.bridge.configure({'save_directory':str(target)})['save_directory'],str(target))
        restored=RegularBridge(self.manager,self.root/'Downloads')
        self.assertEqual(restored.save_directory,target)
        self.assertEqual(json.loads(p.read_text(encoding="utf-8"))['other'],'keep')
    def test_relative_or_bad_directory_rejected(self):
        before=self.bridge.save_directory
        for value in ['../escape','',None,'bad\x00path']:
            with self.assertRaises(HelperError):self.bridge.configure({'save_directory':value})
        blocked=self.root/'file';blocked.write_text('keep')
        with self.assertRaises(OSError):self.bridge.configure({'save_directory':str(blocked)})
        self.assertEqual(self.bridge.save_directory,before)
    def test_pdf_saved_with_title_and_counted_only_after_written(self):
        destination=self.root/'选定目录';self.bridge.configure({'save_directory':str(destination)})
        state=self.save();paper=state['papers'][0]
        self.assertEqual(state['actual_pdf_count'],1)
        self.assertEqual(Path(paper['file']['saved_path']).name,'中文论文_ Air _ Flow_.pdf')
        self.assertEqual(Path(paper['file']['saved_path']).read_bytes(),PDF)
        self.assertEqual(paper['browser_evidence']['download_method'],'EXTENSION_FETCH')
        manifest=json.loads(Path(paper['file']['manifest']).read_text(encoding='utf-8'))
        self.assertEqual(manifest['provenance']['save_transport'],'BROWSER_FETCH_TO_LOCAL_SERVICE')
    def test_different_same_title_never_overwrites_and_same_bytes_reuses(self):
        paper={'title':'同名论文','doi':'10.1000/a'}
        first=Path(self.bridge.named_copy(PDF,paper));second=Path(self.bridge.named_copy(PDF+b'\n',paper))
        self.assertEqual(second.name,'同名论文 (2).pdf');self.assertEqual(first.read_bytes(),PDF)
        self.assertEqual(self.bridge.named_copy(PDF,paper),str(first))
    def test_filename_cannot_escape_and_windows_devices_are_sanitized(self):
        for title in ['../outside','CON','NUL.txt','COM1','..','a'*500]:
            path=Path(self.bridge.named_copy(PDF,{'title':title,'doi':'10.1000/a'}))
            self.assertEqual(path.parent,self.bridge.save_directory)
            self.assertLessEqual(len(path.stem),145)
            self.assertNotIn('/',path.name)
        self.assertTrue((self.bridge.save_directory/'_CON.pdf').exists())
    def test_html_incomplete_large_files_not_saved_or_counted(self):
        from unittest.mock import patch
        for body in [b'<html>login</html>',b'%PDF-1.4\ntruncated']:
            with self.assertRaises(PdfResponseError):self.save(body)
        with patch('literature_helper.MAX_PDF',4),self.assertRaises(HelperError):self.save()
        self.assertEqual(self.manager.status(self.sid)['actual_pdf_count'],0)
        self.assertFalse(self.bridge.save_directory.exists())
    def test_missing_identity_closed_or_wrong_index_rejected(self):
        for field,value in [('status','CLOSED'),('backend','dedicated')]:
            original=self.state[field];self.state[field]=value;self.manager.save(self.state)
            with self.assertRaises(HelperError):self.save()
            self.state[field]=original
        self.state['papers'][0]['browser_evidence']['identity_matched']=False;self.manager.save(self.state)
        with self.assertRaises(HelperError):self.save()
        with self.assertRaises(HelperError):self.bridge.receive_pdf(self.sid,9,PDF,'PDF_RESPONSE')
        with self.assertRaises(HelperError):self.bridge.receive_pdf(self.sid,0,PDF,'invalid')
    def test_failed_destination_does_not_count_library_cache_as_delivered(self):
        from unittest.mock import patch
        with patch.object(self.bridge,'named_copy',side_effect=OSError('unwritable')):
            with self.assertRaises(OSError):self.save()
        self.assertEqual(self.manager.status(self.sid)['actual_pdf_count'],0)
        self.assertEqual(self.save()['actual_pdf_count'],1)
    def test_http_requires_capability_and_checks_body_then_saves(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(self.bridge,'fixture-token'))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base='http://127.0.0.1:'+str(server.server_port);client=build_opener(ProxyHandler({}))
        headers={'Authorization':'Bearer fixture-token','Content-Type':'application/pdf','X-Papers-Session':self.sid,'X-Papers-Index':'0','X-Papers-Trigger':'PDF_RESPONSE'}
        try:
            for endpoint,data in [('/preferences',None),('/preferences',b'{}'),('/pdf-bytes',PDF)]:
                with self.assertRaises(HTTPError) as caught:client.open(Request(base+endpoint,data=data))
                self.assertEqual(caught.exception.code,401)
            with client.open(Request(base+'/preferences',headers=headers)) as response:self.assertEqual(json.load(response)['filename_rule'],'论文题名.pdf')
            with self.assertRaises(HTTPError) as caught:client.open(Request(base+'/pdf-bytes',data=b'<html>login</html>',headers=headers))
            self.assertEqual(caught.exception.code,400)
            destination=str(self.root/'HTTP目录')
            with client.open(Request(base+'/preferences',data=json.dumps({'save_directory':destination}).encode(),headers={**headers,'Content-Type':'application/json'})) as response:self.assertEqual(json.load(response)['save_directory'],destination)
            with client.open(Request(base+'/pdf-bytes',data=PDF,headers=headers)) as response:self.assertEqual(json.load(response)['actual_pdf_count'],1)
            self.assertEqual(len(list(Path(destination).glob('*.pdf'))),1)
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
