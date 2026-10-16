"""普通浏览器扩展的本机接续服务；仅接收选定论文的状态和下载文件。"""
from __future__ import annotations

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen
import webbrowser

from literature_helper import LiteratureHelper, HelperError, MAX_PDF, PdfResponseError
from collection_workflow import CollectionManager, atomic_json, now
from browser_worker import TERMINAL

ORIGIN = "http://127.0.0.1:8766"


def downloads_directory():
    explicit = os.environ.get("LIT_BROWSER_DOWNLOAD_DIR")
    if explicit:
        return Path(explicit).resolve()
    if os.name == "nt":
        import ctypes, uuid
        class GUID(ctypes.Structure):
            _fields_=[("a",ctypes.c_ulong),("b",ctypes.c_ushort),("c",ctypes.c_ushort),("d",ctypes.c_ubyte*8)]
        guid=GUID.from_buffer_copy(uuid.UUID('374de290-123f-4565-9164-39c4925e467b').bytes_le)
        result=ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid),0,None,ctypes.byref(result))==0:
            try: return Path(result.value).resolve()
            finally: ctypes.windll.ole32.CoTaskMemFree(result)
    return (Path.home()/"Downloads").resolve()


def extension_directory():
    candidates = (Path(__file__).resolve().parent / "browser-extension",
                  Path(sys.prefix) / "share" / "papers-capture" / "browser-extension")
    for candidate in candidates:
        if (candidate / "manifest.json").is_file():
            return candidate
    raise HelperError("未找到浏览器扩展文件；请完整安装papers-capture或使用源码仓库")


class RegularBridge:
    def __init__(self, manager, download_root=None):
        self.manager=manager
        settings=manager.browser_dir/'settings.json'
        configured=json.loads(settings.read_text(encoding='utf-8')).get('download_directory') if settings.is_file() else None
        self.download_root=Path(download_root or os.environ.get('LIT_BROWSER_DOWNLOAD_DIR') or configured or downloads_directory()).resolve()
        self.lock=threading.Lock()

    def tasks(self):
        result=[]
        if self.manager.root.exists():
            for path in self.manager.root.glob('*/state.json'):
                state=self.manager.load(path.parent.name)
                if state.get('backend')=='regular_extension' and state['status'] not in {'FINISHED','CLOSED'}:
                    result.append({k:state[k] for k in ['session_id','original_prompt','papers','status']})
        return result

    def update(self, data, completed=False):
        with self.lock:
            state=self.manager.load(data.get('session_id',''))
            if state.get('backend')!='regular_extension' or state['status']=='CLOSED':
                raise HelperError('任务未授权普通浏览器接续')
            index=data.get('index')
            if type(index) is not int or not 0<=index<len(state['papers']):
                raise HelperError('论文序号无效')
            paper=state['papers'][index]
            if paper['status'] in {'SAVED','ALREADY_EXISTS'}:
                return self.manager.status(state['session_id'])
            state['current_index']=index
            if completed:
                source=Path(data.get('download_path','')).resolve()
                expected=self.download_root/'papers-capture'/state['session_id']
                if source.parent!=expected or source.is_symlink() or not re.fullmatch(r'(?:'+str(index)+r'(?: \(\d+\))?\.pdf|[^\x00/\\]+\.html?)',source.name,re.I) or not source.is_file():
                    raise HelperError('下载文件不在本任务专用收件目录；可设置LIT_BROWSER_DOWNLOAD_DIR匹配浏览器目录')
                with source.open('rb') as f: body=f.read(MAX_PDF+1)
                try:
                    result=self.manager.helper._save_pdf(body,paper['doi'],{'origin':'regular_browser_extension',
                           'paper_identity':'EXPECTED_PAPER_IDENTITY_MATCHED_BEFORE_DOWNLOAD','entitlement_evidence':'BROWSER_DOWNLOAD_COMPLETE_AND_VALID_PDF',
                           'note':'在本人正常浏览器内下载；不导出Cookie/密码，保留原下载文件'})
                except PdfResponseError:
                    if b'security verification' in body.lower() or b'challenges.cloudflare.com' in body.lower():
                        paper['status']='NEED_BROWSER_SAVE';paper['native_save_required']=True
                        paper['reason']='下载请求返回网站安全验证页；停止自动重试，请在已打开的PDF阅读器点下载'
                    else:
                        paper['status']='ACCESS_UNKNOWN'
                        paper['reason']='下载结果不是完整PDF，可能为预览/登录/验证页；未计入全文'
                else:
                    paper['status'],paper['file']=result['status'],result
                    paper.pop('reason',None)
                    paper.pop('native_save_required',None)
                    paper.get('browser_evidence',{}).pop('failure_code',None)
            else:
                observed=data.get('status')
                allowed={'NEED_USER_AUTHENTICATION','CHALLENGE_REQUIRED','ACCESS_UNKNOWN','SKIPPED_NO_ACCESS','SKIPPED_BY_USER','DOWNLOADING','DOWNLOAD_ERROR','NEED_BROWSER_SAVE'}
                if observed not in allowed:
                    raise HelperError('不支持的浏览器观察状态')
                if observed=='SKIPPED_NO_ACCESS' and (data.get('identity_matched') is not True or data.get('institution_recognized') is not True):
                    raise HelperError('缺少本篇身份或机构识别，不接受无权限结论')
                if observed=='DOWNLOAD_ERROR' and paper.get('native_save_required'):observed='NEED_BROWSER_SAVE'
                if observed=='NEED_BROWSER_SAVE':paper['native_save_required']=True
                paper['status']=observed
                paper['browser_evidence']={'identity_matched':bool(data.get('identity_matched')),'backend':'regular_extension','observed_state':observed,
                    'institution_recognized':data.get('institution_recognized') is True, 'visible_auth_form':data.get('visible_auth_form') is True,
                    'pdf_candidates':min(6,max(0,data.get('pdf_candidates',0))) if type(data.get('pdf_candidates',0)) is int else 0}
                if re.fullmatch(r'\d+\.\d+\.\d+',str(data.get('extension_version',''))):
                    paper['browser_evidence']['extension_version']=data['extension_version']
                if data.get('identity_source') in {'PAGE_DOI','IEEE_ARTICLE_URL','VERIFIED_PDF_VIEWER'}:
                    paper['browser_evidence']['identity_source']=data['identity_source']
                reasons={'NOT_PDF':'网站返回网页，未取得论文PDF','LOCAL_API':'本机接续或下载目录校验失败','BROWSER_OPERATION':'浏览器操作失败','DOWNLOAD_SECURITY':'下载请求返回安全验证页，请在已打开PDF的阅读器点下载'}
                if data.get('failure_code') in reasons:
                    paper['browser_evidence']['failure_code']=data['failure_code'];paper['reason']=reasons[data['failure_code']]
                elif observed=='DOWNLOADING':paper.pop('reason',None)
                if data.get('download_method') in {'EXTENSION_REQUEST','BROWSER_NATIVE'}:
                    paper['browser_evidence']['download_method']=data['download_method']
            pending=[i for i,p in enumerate(state['papers']) if p['status'] not in TERMINAL]
            state['status']='FINISHED' if not pending else paper['status']
            state['current_index']=pending[0] if pending else None
            self.manager.save(state)
            return self.manager.status(state['session_id'])


def handler_for(bridge, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def send_json(self,code,data):
            body=json.dumps(data,ensure_ascii=False).encode('utf-8')
            self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
        def authorized(self):
            return hmac.compare_digest(self.headers.get('Authorization',''), 'Bearer '+token)
        def do_GET(self):
            if self.path=='/pair':
                body=b'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>papers-capture pairing</title><h1>papers-capture</h1><p id="status">Install the local browser extension, then reload this page to pair. No school password is requested.</p></html>'
                self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body); return
            if not self.authorized():
                self.send_json(401,{'status':'UNAUTHORIZED'}); return
            if self.path=='/health':
                self.send_json(200,{'status':'READY','service':'papers-capture','version':'0.4.3'}); return
            if self.path=='/tasks':
                self.send_json(200,{'tasks':bridge.tasks()}); return
            self.send_json(404,{'status':'NOT_FOUND'})
        def do_POST(self):
            if not self.authorized():
                self.send_json(401,{'status':'UNAUTHORIZED'}); return
            if self.path not in {'/observe','/complete'}:
                self.send_json(404,{'status':'NOT_FOUND'}); return
            try:
                count=int(self.headers.get('Content-Length','0'))
                if not 0<count<=8192: raise HelperError('请求大小不合要求')
                data=json.loads(self.rfile.read(count))
                self.send_json(200,bridge.update(data,self.path=='/complete'))
            except (HelperError,OSError,ValueError,TypeError):
                self.send_json(400,{'status':'REJECTED','message':'状态或下载文件校验失败，未冒称已保存；浏览器自定义下载目录需配置LIT_BROWSER_DOWNLOAD_DIR'})
    return Handler


def ensure_bridge(manager):
    config=manager.browser_dir/'bridge.json'
    def live():
        try:
            data=json.loads(config.read_text(encoding='utf-8'))
            request=Request(ORIGIN+'/health',headers={'Authorization':'Bearer '+data['token']})
            with urlopen(request,timeout=1) as response:
                if json.load(response).get('service')=='papers-capture': return data
        except (OSError,ValueError,KeyError): pass
        return None
    data=live()
    if data: return data
    manager.browser_dir.mkdir(parents=True,exist_ok=True)
    options={'stdin':subprocess.DEVNULL,'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL}
    if os.name=='nt': options['creationflags']=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP
    else: options['start_new_session']=True
    subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--output',str(manager.helper.output),'--browser-dir',str(manager.browser_dir)],**options)
    for _ in range(30):
        time.sleep(0.1)
        data=live()
        if data: return data
    raise HelperError('普通浏览器本机接续服务未启动；请检查8766端口是否被占用')


def use_regular_browser(manager, sid, open_browser=True):
    state=manager.load(sid)
    if state['status'] not in {'CLOSED','WORKER_ERROR','TIMED_OUT','BROWSER_BUSY','BROWSER_UNAVAILABLE','NEED_BROWSER','CREATED','FINISHED'}:
        manager.action(sid,'close')
        for _ in range(50):
            time.sleep(0.1)
            state=manager.load(sid)
            if state['status']=='CLOSED': break
        else: raise HelperError('专用浏览器尚未停止；稍后再接续，避免两种后端同时写入')
    state=manager.load(sid)
    state['backend']='regular_extension'
    state['status']='NEED_BROWSER_EXTENSION'
    state['current_index']=None
    manager.save(state)
    info=ensure_bridge(manager)
    if open_browser:
        webbrowser.open(ORIGIN+'/pair#'+info['token'],new=2)
    return {'status':'NEED_BROWSER_EXTENSION','session_id':sid,'extension_directory':str(extension_directory()),
            'pairing_page_requested':open_browser,'steps':['在能正常访问论文的Chrome或Edge里加载本地browser-extension目录（只做一次）','重新加载已打开的本机配对页','点扩展图标，选择任务并开始；需机构认证时本人登录，返回论文后自动继续'],
            'note':'扩展不申请Cookie读取权限；使用浏览器自身下载API。还需本人安装并完成真实订阅样例验收'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',required=True); parser.add_argument('--browser-dir',required=True)
    args=parser.parse_args()
    manager=CollectionManager(LiteratureHelper(args.output),args.browser_dir)
    previous=manager.browser_dir/'bridge.json'
    try:
        token=json.loads(previous.read_text(encoding='utf-8')).get('token','')
    except (OSError,ValueError):token=''
    if not re.fullmatch(r'[-_a-zA-Z0-9]{40,60}',token):token=secrets.token_urlsafe(32)
    server=ThreadingHTTPServer(('127.0.0.1',8766),handler_for(RegularBridge(manager),token))
    manager.browser_dir.mkdir(parents=True,exist_ok=True)
    atomic_json(manager.browser_dir/'bridge.json',{'token':token,'pid':os.getpid(),'started_at':now()})
    server.serve_forever()
