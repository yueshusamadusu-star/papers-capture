import json
from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import unittest
from unittest.mock import patch

from literature_helper import LiteratureHelper,HelperError
from collection_workflow import CollectionManager
from normal_browser import RegularBridge,handler_for,extension_directory


class NormalBrowserTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        root=Path(self.temp.name)
        self.manager=CollectionManager(LiteratureHelper(root/'library'))
        self.downloads=root/'Downloads'
        self.bridge=RegularBridge(self.manager,self.downloads)
        self.state=self.manager._create('试验',['ultrasonic'],[],[{'doi':'10.1000/a','identifier':'10.1000/a','title':'Fixture','article_url':'https://doi.org/10.1000/a','status':'BROWSER_PENDING'}],False,False)
        self.state['backend']='regular_extension';self.manager.save(self.state)
        self.sid=self.state['session_id']
    def tearDown(self): self.temp.cleanup()
    def file(self,body):
        p=self.downloads/'papers-capture'/self.sid/'0.pdf';p.parent.mkdir(parents=True);p.write_bytes(body);return p
    def test_only_enrolled_tasks_returned(self):
        self.assertEqual(len(self.bridge.tasks()),1)
        self.state['backend']='other';self.manager.save(self.state)
        self.assertEqual(self.bridge.tasks(),[])
    def test_complete_imports_valid_pdf_and_keeps_original(self):
        self.state['papers'][0]['reason']='旧下载失败';self.manager.save(self.state)
        p=self.file(b'%PDF-1.4\nfixture\n%%EOF')
        result=self.bridge.update({'session_id':self.sid,'index':0,'download_path':str(p)},True)
        self.assertEqual(result['actual_pdf_count'],1);self.assertEqual(result['status'],'FINISHED');self.assertTrue(p.exists());self.assertNotIn('reason',result['papers'][0])
    def test_html_is_not_counted_as_fulltext(self):
        p=self.file(b'<html>login</html>')
        html=p.with_suffix('.htm');p.rename(html);p=html
        result=self.bridge.update({'session_id':self.sid,'index':0,'download_path':str(p)},True)
        self.assertEqual(result['actual_pdf_count'],0);self.assertEqual(result['papers'][0]['status'],'ACCESS_UNKNOWN')
    def test_verification_html_enters_native_save_without_counting(self):
        source=self.file(b'<html><title>Security verification</title><script src="https://challenges.cloudflare.com/turnstile.js"></script></html>')
        target=source.with_name('init.htm');source.rename(target)
        result=self.bridge.update({'session_id':self.sid,'index':0,'download_path':str(target)},True)
        self.assertEqual(result['actual_pdf_count'],0)
        self.assertEqual(result['papers'][0]['status'],'NEED_BROWSER_SAVE')
        self.assertTrue(result['papers'][0]['native_save_required'])
    def test_native_save_success_clears_requirement(self):
        self.state['papers'][0]['native_save_required']=True;self.manager.save(self.state)
        source=self.file(b'%PDF-1.4\nfixture\n%%EOF')
        result=self.bridge.update({'session_id':self.sid,'index':0,'download_path':str(source)},True)
        self.assertEqual(result['actual_pdf_count'],1)
        self.assertNotIn('native_save_required',result['papers'][0])
    def test_arbitrary_local_file_rejected(self):
        p=Path(self.temp.name)/'secret.pdf';p.write_bytes(b'%PDF-1.4\nsecret\n%%EOF')
        with self.assertRaises(HelperError):self.bridge.update({'session_id':self.sid,'index':0,'download_path':str(p)},True)
    def test_permission_denial_requires_paper_identity(self):
        with self.assertRaises(HelperError):self.bridge.update({'session_id':self.sid,'index':0,'status':'SKIPPED_NO_ACCESS'})
        with self.assertRaises(HelperError):self.bridge.update({'session_id':self.sid,'index':0,'status':'SKIPPED_NO_ACCESS','identity_matched':True})
        result=self.bridge.update({'session_id':self.sid,'index':0,'status':'SKIPPED_NO_ACCESS','identity_matched':True,'institution_recognized':True})
        self.assertEqual(result['actual_pdf_count'],0);self.assertEqual(result['status'],'FINISHED')
    def test_resume_restores_service_and_preserves_saved_paper_and_current_index(self):
        first = dict(self.state["papers"][0])
        first["status"] = "SAVED"
        first["file"] = {"sha256": "a" * 64, "bytes": 1024}
        pending = dict(self.state["papers"][0])
        pending["doi"] = pending["identifier"] = "10.1000/b"
        pending["status"] = "ACCESS_UNKNOWN"
        pending["browser_evidence"] = {"identity_matched": False}
        self.state.update(status="ACCESS_UNKNOWN", current_index=1, papers=[first, pending])
        self.manager.save(self.state)
        with patch("normal_browser.ensure_bridge", return_value={"token": "private-fixture", "pid": 123}) as ensure:
            result = self.manager.action(self.sid, "resume")
        ensure.assert_called_once_with(self.manager)
        self.assertEqual(result["current_index"], 1)
        self.assertEqual(result["papers"], [first, pending])
        self.assertEqual(result["actual_pdf_count"], 1)
        self.assertNotIn("private-fixture", json.dumps(result))
        self.assertFalse((self.manager.directory(self.sid) / "command.json").exists())

    def test_resume_does_not_overwrite_progress_arriving_during_service_start(self):
        self.state.update(status="ACCESS_UNKNOWN", current_index=0)
        self.manager.save(self.state)
        def finish_while_service_starts(manager):
            current = manager.load(self.sid)
            current["status"] = "FINISHED"
            current["papers"][0]["status"] = "SKIPPED_BY_USER"
            manager.save(current)
            return {"pid": 123}
        with patch("normal_browser.ensure_bridge", side_effect=finish_while_service_starts):
            result = self.manager.action(self.sid, "resume")
        self.assertEqual(result["status"], "FINISHED")
        self.assertEqual(result["papers"][0]["status"], "SKIPPED_BY_USER")
        self.assertEqual(self.manager.load(self.sid)["status"], "FINISHED")

    def test_resume_service_failure_leaves_checkpoint_bytes_unchanged(self):
        self.state.update(status="ACCESS_UNKNOWN", current_index=0)
        self.manager.save(self.state)
        checkpoint = self.manager.directory(self.sid) / "state.json"
        before = checkpoint.read_bytes()
        with patch("normal_browser.ensure_bridge", side_effect=HelperError("port unavailable")):
            with self.assertRaises(HelperError):
                self.manager.action(self.sid, "resume")
        self.assertEqual(checkpoint.read_bytes(), before)

    def test_closed_task_resume_does_not_start_service(self):
        self.state["status"] = "CLOSED"
        self.manager.save(self.state)
        with patch("normal_browser.ensure_bridge") as ensure:
            result = self.manager.action(self.sid, "resume")
        ensure.assert_not_called()
        self.assertEqual(result["status"], "CLOSED")

    def test_wheel_extension_directory(self):
        root=Path(self.temp.name)
        installed=root/'prefix'/'share'/'papers-capture'/'browser-extension'
        installed.mkdir(parents=True);(installed/'manifest.json').write_text('{}')
        with patch('normal_browser.__file__',str(root/'site-packages'/'normal_browser.py')),patch('normal_browser.sys.prefix',str(root/'prefix')):
            self.assertEqual(extension_directory(),installed)
    def test_failure_code_only_stores_safe_diagnostics(self):
        result=self.bridge.update({'session_id':self.sid,'index':0,'status':'DOWNLOAD_ERROR','identity_matched':True,'extension_version':'0.4.1','failure_code':'NOT_PDF','signed_url':'https://example.invalid/?secret=fixture'})
        paper=result['papers'][0]
        self.assertEqual(paper['browser_evidence']['extension_version'],'0.4.1')
        self.assertEqual(paper['browser_evidence']['failure_code'],'NOT_PDF')
        self.assertNotIn('fixture',json.dumps(paper))
    def test_loopback_api_requires_capability(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(self.bridge,'fixture-token'))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url='http://127.0.0.1:'+str(server.server_port)
        try:
            with self.assertRaises(HTTPError) as caught:urlopen(url+'/tasks')
            self.assertEqual(caught.exception.code,401)
            with urlopen(Request(url+'/tasks',headers={'Authorization':'Bearer fixture-token'})) as response:
                self.assertEqual(len(json.load(response)['tasks']),1)
            payload=json.dumps({'session_id':self.sid,'index':99,'status':'ACCESS_UNKNOWN'}).encode()
            with self.assertRaises(HTTPError):urlopen(Request(url+'/observe',data=payload,headers={'Authorization':'Bearer fixture-token','Content-Type':'application/json'}))
        finally:server.shutdown();server.server_close()


if __name__=='__main__':unittest.main()
