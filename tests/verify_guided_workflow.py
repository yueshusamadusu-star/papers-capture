"""少量公共联网验收：CLI交接与真实MCP生成清单，不测试校园认证。"""
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
    project = Path(__file__).resolve().parents[1]
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    env = {k:v for k,v in os.environ.items() if k != 'UNPAYWALL_EMAIL'}
    env.update({'PYTHONIOENCODING': 'utf-8', 'LIT_OUTPUT_DIR': str(root / 'lists')})
    checks = {}
    for command in ('access', 'collect'):
        r = subprocess.run([sys.executable, str(project / 'literature_helper.py'), command,
                            '10.3390/metrology5040071', '--no-open'], env=env,
                           capture_output=True, text=True, encoding='utf-8', timeout=20, check=True)
        data = json.loads(r.stdout)
        access = data if command == 'access' else data['access']
        assert access['authentication'] == 'UNKNOWN' and 'browser' not in access
        checks['CLI_' + command] = {'status': 'PASS', 'result_status': data['status']}
    params = StdioServerParameters(command=sys.executable, args=[str(project / 'mcp_server.py')], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool('prepare_reading_list', {
                'query': 'ultrasonic flowmeter cycle skipping', 'limit': 3, 'open_browser': False})
            assert not result.isError
            data = result.structuredContent
            assert data['status'] == 'READING_LIST_READY' and data['papers'] > 0
            page, manifest = Path(data['path']), Path(data['manifest'])
            body = page.read_text(encoding='utf-8')
            records = json.loads(manifest.read_text(encoding='utf-8'))
            assert 'https://doi.org/' in body and 'https://ds.carsi.edu.cn/' in body
            assert len(records['papers']) == data['papers']
            checks['MCP_真实公共检索与清单'] = {
                'status': 'PASS', 'papers': data['papers'], 'path': str(page),
                'manifest': str(manifest), 'html_sha256': hashlib.sha256(page.read_bytes()).hexdigest()}
    report = {'time_utc': datetime.now(timezone.utc).isoformat(), 'checks': checks,
              'scope': 'CLI及真实MCP；仅一次Crossref公共查询；未启动实际浏览器或认证机构'}
    (root / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(main())
