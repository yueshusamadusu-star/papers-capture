# papers-capture：文献检索与本地收集工具

第一版 0.1.0，2026-10-12。非浙大官方项目。功能：公开元数据检索、单篇开放全文下载、人工下载文件整理、stdio MCP 接口。

仓库：https://github.com/yueshusamadusu-star/papers-capture

开源代码使用 MIT 许可；文献内容各自的许可独立于代码许可。学校通行证不是统一的全文下载 API，当前不实现校园密码登录或订阅网页爬虫。

## 为什么没有学校密码输入框

[浙大电子资源使用管理办法第四条](https://libweb.zju.edu.cn/2016/1014/c39581a1666449/page.htm)明确禁止使用自动下载软件/机器人下载授权资料。统一身份登录、WebVPN、CARSI 是本人访问入口，并不代表取得自动爬取许可。此工具提供[官方校外访问指引](https://libweb.zju.edu.cn/2022/0408/c39479a2515130/page.htm)，由本人在浏览器中登录、按许可手动下载单篇全文，再导入整理。不会读取浏览器 Cookie 或绕过验证。

其他学校未来可以增加自己的人工访问入口。若机构另有获授权的出版商 API，可再做专门适配，不能仅凭校园通行证假设所有数据库通用。

## 两分钟看懂用法

CLI 核心只用 Python 标准库，无须安装依赖。先克隆项目，再在目录中执行（将 `python` 换为自己的 Python 3.10+）：

```powershell
git clone https://github.com/yueshusamadusu-star/papers-capture.git
cd papers-capture
```

```powershell
python literature_helper.py search "ultrasonic flowmeter cycle skipping" --limit 5
python literature_helper.py lookup 10.3390/metrology5040071
python literature_helper.py --output "D:\文献" download arxiv:1706.03762
python literature_helper.py guide 10.1109/TIM.2025.3595225
python literature_helper.py --output "D:\文献" --inbox "D:\文献收件箱" import "自己下载的一篇.pdf" --identifier 10.1109/TIM.2025.3595225
```

第三条是公开 arXiv 下载示例，用于验证工具，不表示这篇论文是超声研究依据。默认保存目录为本目录的 `downloads`；实际保存为全文 SHA256 文件名，同时保存同名 JSON 来源清单，不覆盖已有不同内容。下载文件仅本地使用，不随开源项目再分发。

需要通过 DOI 找开放版本时，Unpaywall 要求联系邮箱。可在**本机进程环境变量**填写本人邮箱（不是学校账号密码，不提交配置值）：

```powershell
$env:UNPAYWALL_EMAIL = "你的联系邮箱"
python literature_helper.py oa 10.3390/metrology5040071
python literature_helper.py --output "D:\文献" download 10.3390/metrology5040071
```

当前无需付费 API 密钥。没有邮箱时返回 `NEED_CONTACT_EMAIL`，不会编造邮箱。只有明确公开来源且在首版支持列表中的 PDF 才自动下载；其他开放链接返回人工处理。不存在开放版本时给出人工入口，不保证任何 DOI 都能下载。

## MCP 接口

核心与 MCP 共用实现。安装官方 SDK 的维护版依赖：

```powershell
python -m pip install ".[mcp]"
python mcp_server.py
```

服务通过 stdio 等待客户端连接，不是普通命令行输出页面。建议在个人虚拟环境安装。经验证的 SDK 版本见 `requirements-mcp-tested.txt`。客户端配置示例（路径改成自己的，**本项目未替你改动任何客户端设置**）：

```json
{
  "mcpServers": {
    "literature-helper": {
      "command": "C:/你的Python/python.exe",
      "args": ["D:/你的工具目录/mcp_server.py"],
      "env": {
        "LIT_OUTPUT_DIR": "D:/文献",
        "LIT_INBOX_DIR": "D:/文献收件箱"
      }
    }
  }
}
```

六个工具：`search_papers`、`lookup_paper`、`locate_open_access`、`download_open_access`、`zju_access_guide`、`import_local_pdf`。下载/导入会写本地文件，已在 MCP 注解声明；导入只允许读取启动时指定收件箱中的文件名。

## 验证与当前限制

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python tests/smoke_mcp.py
```

- 下载单篇、请求串行且间隔至少3.1秒；429直接停止，403/验证码转人工。不要同时启动多个进程做批量下载。
- 只接受 HTTPS 和明确支持的公共域名；每次重定向重新验证。大小限制25MB；PDF文件头/结束标记检查不等同完整PDF解析或恶意文件扫描。
- 首版自动全文来源列表：arXiv、MDPI指定域名、PMC；并非每条链接/重定向都受支持。禁止任意网址下载，不支持机构代理地址。
- SHA256用于相同文件去重，已有来源清单保留首次记录。记录来源、时间和字节数；未认证论文身份、全文许可、引文质量或研究创新。
- 不包含校园账号密码、模型训练、研究数据、受限全文、浏览器会话。检索词会发给 Crossref；联系邮箱只发给 Unpaywall。
- MCP传输验收与联网全文验收分开；离线测试通过不代表浙大登录成功。本版验收范围见 [验收记录](docs/验收记录_V0_1.md) 和 [版本说明](CHANGELOG.md)。

## 来源与开放准备

- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)：公开书目信息，无需注册。
- [Unpaywall API](https://unpaywall.org/api)、[字段格式](https://unpaywall.org/data-format)：单篇 DOI 开放位置查询，须联系邮箱。
- [arXiv 使用条款](https://info.arxiv.org/help/api/tou.html)：按速率和再分发限制使用。
- [MCP 官方 Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)：stdio 服务与客户端。

本仓库只包含工具代码、测试与说明，不包含研究项目、论文全文或认证资料。许可证见 [LICENSE](LICENSE)。下一轮学校/数据库接入路线见 [浙大访问与接口可行性](docs/浙大访问与接口可行性.md)。

## 后续迭代

1. 校园网中先确认单篇目标文献的人工访问权限，区分机构识别和实际全文覆盖。
2. 有许可的出版商 API：按平台单独申请、验证最小接口，API 密钥仅放本机环境变量。
3. 学校配置与出版商适配分开，逐步加入其他学校的官方入口；不承诺一套通行证登录全部平台。

4. 获得相应接口许可后，加入访问状态检测与官方认证引导，区分未登录、无订阅、无API授权和网络错误。当前尚未实现此流程。
