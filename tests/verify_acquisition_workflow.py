"""截图案例的少量联网验收：真实MCP检索保存PDF、CLI未订阅退避。"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    project = Path(__file__).resolve().parents[1]
    env = {k:v for k,v in os.environ.items() if k != 'UNPAYWALL_EMAIL'}
    env.update({'PYTHONIOENCODING': 'utf-8', 'LIT_OUTPUT_DIR': str(root / 'library')})
    params = StdioServerParameters(command=sys.executable, args=[str(project/'mcp_server.py')], env=env)
    checks = {}
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert len(tools.tools) == 10
            result = await session.call_tool('search_and_collect', {
                'query': 'Construction of a Ultrasonic Gas Flowmeter', 'limit': 1, 'open_browser': False})
            assert not result.isError, result
            data = result.structuredContent
            assert data['mode'] == 'COLLECT_FULLTEXT'
            records = json.loads(Path(data['manifest']).read_text(encoding='utf-8'))
            paper = records['papers'][0]
            assert paper['doi'].lower() == '10.5220/0007535905680572', paper['doi']
            collected = paper['collection']
            assert collected['status'] == 'SAVED', collected
            pdf = Path(collected['path'])
            payload = pdf.read_bytes()
            assert payload.startswith(b'%PDF-') and b'%%EOF' in payload[-2048:]
            digest = hashlib.sha256(payload).hexdigest()
            assert digest == collected['sha256']
            page = Path(data['path'])
            assert '打开已保存PDF' in page.read_text(encoding='utf-8')
            provenance = json.loads(Path(collected['manifest']).read_text(encoding='utf-8'))
            assert provenance['identifier'] == paper['doi']
            checks['SciTePress_MCP_search_and_collect'] = {
                'status': 'PASS', 'doi': paper['doi'], 'pdf_bytes': len(payload), 'pdf_sha256': digest,
                'pdf_path': str(pdf), 'reading_list': str(page), 'manifest': data['manifest'],
                'html_sha256': hashlib.sha256(page.read_bytes()).hexdigest()}
    command = [sys.executable, str(project/'literature_helper.py'), 'collect',
               '10.1016/0041-624x(71)90200-9', '--access-state', 'not_subscribed', '--no-open']
    process = subprocess.run(command, env=env, capture_output=True, text=True,
                             encoding='utf-8', timeout=75, check=True)
    result = json.loads(process.stdout)
    assert result['status'] == 'MANUAL_REQUIRED'
    assert result['subscription_access'] == 'NOT_SUBSCRIBED_USER_REPORTED'
    assert 'access' not in result
    assert result['open_access_result']['attempts'] == []
    assert any(c['status'] == 'NEED_CONTACT_EMAIL' for c in result['open_access_result']['checks'])
    checks['ScienceDirect_CLI_not_subscribed_fallback'] = {
        'status': 'PASS', 'doi': result['doi'], 'result': result['status'],
        'subscription_access': result['subscription_access'],
        'open_access_checks': result['open_access_result']['checks'],
        'note': '未取得此篇全文；无邮箱时Unpaywall未执行，不将此写成没有开放版本。未启动浏览器、未验证学校订阅'}
    report = {'time_utc': datetime.now(timezone.utc).isoformat(), 'checks': checks,
              'scope': '一次Crossref主题查询、两次DOI元数据查询、一个SciTePress公开PDF；无账号认证或订阅全文抓取'}
    (root/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(main())
