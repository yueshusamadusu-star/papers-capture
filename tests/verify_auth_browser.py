"""真实浏览器+本机HTTP夹具验收。不是浙大/出版商真实授权验收。"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import sys
from playwright.sync_api import sync_playwright

from literature_helper import LiteratureHelper
from browser_worker import BrowserProcessor

PDF=b'%PDF-1.4\nfixture browser authorization\n%%EOF\n'
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        authorized='fixture=ok' in self.headers.get('Cookie','')
        if self.path=='/authorize':
            self.send_response(302); self.send_header('Set-Cookie','fixture=ok; HttpOnly; SameSite=Lax; Path=/'); self.send_header('Location','/paper'); self.end_headers(); return
        if self.path in ['/paper.pdf','/download']:
            self.send_response(200 if authorized else 403)
            if authorized:
                self.send_header('Content-Type','application/pdf'); self.send_header('Content-Disposition','attachment; filename=fixture.pdf')
            self.end_headers(); self.wfile.write(PDF if authorized else b'Login required'); return
        self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.end_headers()
        if self.path=='/hidden-form':
            body='<meta name="citation_doi" content="10.1000/test"><form style="display:none"><input type="password"></form><a href="/paper.pdf">Download PDF</a>'
        elif self.path=='/challenge':
            body='<p>Verify you are human</p>'
        elif self.path=='/denied':
            body='<meta name="citation_doi" content="10.1000/denied"><p>Brought to you by: Fixture University</p><a>Purchase PDF</a>'
        elif self.path=='/wrong':
            body='<meta name="citation_doi" content="10.1000/wrong"><a href="/paper.pdf">PDF</a>'
        elif self.path=='/click':
            body='<meta name="citation_doi" content="10.1000/test"><button onclick="location.href=\'/download\'">Download PDF</button>'
        else:
            body='<meta name="citation_doi" content="10.1000/test">'
            body+=('<p>Brought to you by: Fixture University</p><a href="/paper.pdf">Download PDF</a>' if authorized else '<a href="/authorize">Institutional sign in</a>')
        self.wfile.write(body.encode('utf-8'))


def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    origin='http://127.0.0.1:'+str(server.server_port)
    try:
        with tempfile.TemporaryDirectory() as directory:
            helper=LiteratureHelper(Path(directory)/'library')
            with sync_playwright() as pw:
                context=pw.chromium.launch_persistent_context(str(Path(directory)/'profile'),channel='msedge' if sys.platform=='win32' else 'chromium',headless=True,accept_downloads=True)
                try:
                    page=context.new_page(); page.goto(origin+'/paper')
                    p=BrowserProcessor(context,helper,test_origin=origin)
                    assert p.inspect(page,'10.1000/test')['status']=='NEED_USER_AUTHENTICATION'
                    assert p.download(page,'10.1000/test',origin+'/paper.pdf')['status']=='NEED_USER_AUTHENTICATION'
                    # 仅夹具的合成按钮；真实账号输入由用户本人完成。
                    page.get_by_role('link',name='Institutional sign in').click()
                    assert p.inspect(page,'10.1000/test')['status']=='PDF_CANDIDATE'
                    result=p.download(page,'10.1000/test',origin+'/paper.pdf')
                    assert result['status']=='SAVED' and Path(result['path']).read_bytes()==PDF
                    page.goto(origin+'/hidden-form'); hidden=p.inspect(page,'10.1000/test'); assert hidden['status']=='PDF_CANDIDATE' and not hidden['password_form']
                    page.goto(origin+'/denied'); assert p.inspect(page,'10.1000/denied')['status']=='NO_ACCESS'
                    page.goto(origin+'/wrong'); assert p.inspect(page,'10.1000/test')['status']=='PAPER_IDENTITY_UNKNOWN'
                    page.goto(origin+'/click'); clicked=p.click_pdf(page,'10.1000/test')
                    assert clicked['status']=='ALREADY_EXISTS',clicked
                    manifest=json.loads(Path(result['manifest']).read_text(encoding='utf-8'))
                    assert 'Cookie' not in json.dumps(manifest) and 'fixture=ok' not in json.dumps(manifest)
                    from collection_workflow import CollectionManager
                    from browser_worker import run_browser
                    manager=CollectionManager(helper)
                    state=manager._create('batch fixture',['ultrasonic'],[],[
                      {'doi':'10.1000/challenge','identifier':'10.1000/challenge','title':'Challenge','article_url':origin+'/challenge','status':'BROWSER_PENDING'},
                      {'doi':'10.1000/test','identifier':'10.1000/test','title':'Open PDF','article_url':origin+'/paper','status':'BROWSER_PENDING'}],True,False)
                    run_browser(manager,state,context,timeout_seconds=0.2,test_origin=origin)
                    result_batch=manager.status(state['session_id'])
                    assert result_batch['actual_pdf_count']==1,result_batch
                    assert result_batch['papers'][0]['status']=='CHALLENGE_REQUIRED'
                    print(json.dumps({'batch_challenge_does_not_block_other_pdf':'PASS','status':'PASS' ,'actual_browser':True,'login_then_same_session_pdf':'PASS','visible_download_button':'PASS','institution_no_access':'PASS','wrong_paper_rejected':'PASS','credentials_exported':False,'scope':'local fixture only; not ZJU/publisher live authentication'},ensure_ascii=False))
                finally: context.close()
    finally: server.shutdown(); server.server_close()


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8'); main()
