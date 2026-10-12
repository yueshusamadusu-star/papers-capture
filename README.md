# papers-capture：文献检索与本地收集工具

0.2.0，2026-10-13。非浙大官方项目。工具负责找文献、生成清单和整理文件；需要机构认证时打开官方页面，由用户本人完成登录。

仓库：https://github.com/yueshusamadusu-star/papers-capture 。代码采用MIT许可，文献内容按各自许可使用。

## 推荐流程：检索 → 本人登录 → 继续查看和整理

需要Python3.10+。首次获取：

```powershell
git clone https://github.com/yueshusamadusu-star/papers-capture.git
cd papers-capture
```

**1. 按主题找文献，并打开可点击的清单：**

```powershell
python literature_helper.py search "ultrasonic flowmeter cycle skipping" --limit 10 --open
```

清单包含标题、作者、年份、刊物和论文入口，同时保存JSON元数据。只打开一个清单页；点击感兴趣的论文时进入DOI对应官网。已经有权限可直接查看；官网要求机构认证时，使用 `Institutional sign in` 选择学校，由本人输入账号、密码和验证码。然后回到清单继续查看其他论文，是否保持登录由浏览器和网站决定。

**2. 已有DOI，想直接获取一篇：**

```powershell
python literature_helper.py collect 10.3390/metrology5040071
```

支持的开放全文可直接保存；没有取得可自动保存的全文时，请求默认浏览器打开论文官方页面。没有配置开放位置查询所需邮箱也会给出官网入口，不要求先登录或先交出密码。工具不把“未取得开放全文”解释成“必须机构登录”；实际入口和单篇权限由官网显示。

需要直接打开浙大官方认证入口时：

```powershell
python literature_helper.py access 10.3390/metrology5040071 --via carsi
# 或 --via webvpn；登录后从该平台的数据库导航进入
```

CARSI先选浙江大学再本人认证；WebVPN不能靠拼接普通网址变成授权链接。两者步骤见[官方指南](https://libweb.zju.edu.cn/2022/0408/c39479a2515130/page.htm)。仅打开入口不代表已认证、已订阅或接口已获授权。

**3. 本人在官网取得所需PDF后整理：**

```powershell
python literature_helper.py --output "D:\文献" --inbox "D:\文献收件箱" import "自己下载的一篇.pdf" --identifier 10.3390/metrology5040071
```

原文件保留，整理副本使用SHA256文件名并附来源JSON。默认输出为项目内 `downloads`；清单在其 `reading-lists` 子目录，每次独立保存。下载全文、个人清单和环境不提交Git。

无桌面或只想取得链接时使用 `collect/access --no-open`；`search --reading-list` 只生成清单，不打开浏览器。CLI的 `collect/access` 默认请求浏览器；原 `download` 命令仍只处理开放全文，不打开浏览器。

## 公共接口和开放全文

无需校园登录的功能：

```powershell
python literature_helper.py search "ultrasonic flowmeter" --limit 5
python literature_helper.py lookup 10.3390/metrology5040071
python literature_helper.py --output "D:\文献" download arxiv:1706.03762
python literature_helper.py guide 10.3390/metrology5040071
```

arXiv样例只用于工具演示，不作为超声研究依据。DOI开放位置查询使用Unpaywall，需在本机环境变量填写本人联系邮箱：

```powershell
$env:UNPAYWALL_EMAIL = "你的联系邮箱"
python literature_helper.py oa 10.3390/metrology5040071
```

这是公共API联系字段，不是校园密码。自动保存仅支持arXiv、MDPI指定域名和PMC；不保证所有DOI或所有开放链接可自动下载。网络错误、429、损坏PDF继续返回错误；HTTP401/403可交本人核对，不能据此断言只是未登录。

## 人工认证与自动下载的区别

[浙大电子资源管理办法](https://libweb.zju.edu.cn/2016/1014/c39581a1666449/page.htm)第三条允许合理速度的个人检索、浏览和少量存档；第四条限制自动下载工具获取授权资料，以及超出合理范围的集中操作。本文没有据此认定“自动填密码被明文禁止”。

本工具打开官方入口并由本人认证，公共元数据检索独立进行。没有读取密码、Cookie、登录页或浏览器会话，也不自动把本人浏览器登录转换为订阅全文抓取权限。有单独许可的出版商API，可再按接口授权适配。详见[访问路线说明](docs/浙大访问与接口可行性.md)。

## MCP

```powershell
python -m pip install ".[mcp]"
python mcp_server.py
```

stdio服务等待客户端连接。个人客户端配置示例，路径改成自己的：

```json
{
  "mcpServers": {
    "papers-capture": {
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

九个工具：`search_papers`、`lookup_paper`、`locate_open_access`、`download_open_access`、`zju_access_guide`、`import_local_pdf`，以及新增的 `prepare_reading_list`、`open_paper_access`、`collect_paper`。

新工具默认 `open_browser=false`；明确设置 `true` 才打开浏览器。`route`可选 `article/carsi/webvpn`。清单、下载和浏览器工具均声明有副作用；不会修改MCP客户端配置。`BROWSER_OPEN_REQUESTED`仅表示系统接受打开请求，认证和单篇权限始终保留 `UNKNOWN`，没有实现登录完成自动检测。

## 验证和限制

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python tests/smoke_mcp.py
```

- 请求串行、间隔至少3.1秒，429停止。不要用多个进程进行集中抓取。
- 下载仅允许指定HTTPS域名并检查重定向；25MB大小限制；PDF头/尾检查不是完整解析或恶意文件扫描。
- 元数据和清单中的文字全部HTML转义，论文链接只从有效DOI生成，未直接采用API给出的任意网址。
- 哈希去重，保留首次来源记录；工具不认证论文身份、全文许可或文献相关性。
- 本机浏览器可能无法启动；此时清单和链接保留，可自行打开。无法保证无桌面机器弹窗。
- 校园本人认证与订阅全文流程尚需人工实测，不以软件测试替代。验收见 [0.2.0记录](docs/验收记录_V0_2.md)；历史见 [0.1.0记录](docs/验收记录_V0_1.md)。

## 官方来源

[Crossref API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)、[Unpaywall API](https://unpaywall.org/api)、[arXiv条款](https://info.arxiv.org/help/api/tou.html)、[MCP官方Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)。出版商API授权及其他学校入口后续分别适配，不将学校密码作为通用接口。
