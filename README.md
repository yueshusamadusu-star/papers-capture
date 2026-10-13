# papers-capture：文献检索与本地收集工具

0.3.0，2026-10-13。非浙大官方项目。支持公共检索、部分来源全文自动保存、本人官网访问与本地PDF整理。代码MIT，文献内容按各自许可使用。

仓库：https://github.com/yueshusamadusu-star/papers-capture

## 推荐：检索并实际尝试保存全文

需要Python3.10+。首次使用可clone本仓库；脚本基础功能只使用标准库。

```powershell
python literature_helper.py search "ultrasonic flowmeter cycle skipping" --limit 3 --collect --open
```

这条命令会串行检索并尝试保存最多3篇的公开PDF，再打开结果清单。每篇分别显示“已保存PDF”“全文未保存”“获取出错”或“尚未尝试”；已保存的条目能直接打开本地PDF。PDF、HTML与JSON默认在项目 `downloads`，可用顶层 `--output` 指定目录。

**`search --open` 没有 `--collect` 时仍是纯检索。** 清单会明确写“仅检索，未执行全文收集”。元数据条数不等于已下载篇数，关键词检索也不自动保证相关性、年份或文献质量。返回数量1–10，建议先3篇筛选。

已有DOI时直接收集：

```powershell
python literature_helper.py collect 10.5220/0007535905680572
```

当前公开获取路线：有普通联系邮箱时用Unpaywall查询同一DOI的多个开放位置；支持位置失败可尝试下一个。随后核对Crossref公开元数据，支持SciTePress指定DOI格式的公开PDF，以及匹配当前CC许可的已声明PDF链接。自动下载仍限支持域名，每篇最多检查3个PDF候选，来源限流即停止整个检索收集队列。没有邮箱也可执行Crossref与SciTePress路线，不直接结束于登录页。

## 对两种登录/权限情况的处理

### SciTePress：可能是免费个人账号

SciTePress是会议论文出版社的数字图书馆，非跨出版社通用检索入口。其[官方说明](https://www.scitepress.org/Aboutus.aspx)与[登录页](https://www.scitepress.org/Login.aspx)说明有免费个人账号和下载额度；不要把个人账号误认为学校机构账号。

本版对截图中的 `10.5220/0007535905680572` 已实际通过公开PDF保存。适配仅支持16位数字后缀、Crossref同一DOI/出版年/官方资源域；路径约定记录在来源JSON。不能据一篇公开可读承诺全部SciTePress文献无需账号。若某篇确实要求个人账号，返回免费账号入口，由本人操作，不用学校密码，也不绕过登录或下载限制。

### ScienceDirect：机构已识别，但单篇未订阅

[官方权限说明](https://www.elsevier.support/sciencedirect/answer/what-different-access-levels-are-there-for-journals-and-books)区分机构识别与具体卷期/单篇覆盖范围。显示学校名称不证明某篇PDF可取；未取得1971年的记录也不能据此断言整本期刊未购买。

本人已确认该篇未订阅时：

```powershell
python literature_helper.py collect "10.1016/0041-624x(71)90200-9" --access-state not_subscribed
```

工具先继续查公开来源，若未取得则返回 `MANUAL_REQUIRED`、标明 `NOT_SUBSCRIBED_USER_REPORTED`，给出同一DOI的开放版本检索和[浙大文献传递](https://libweb.zju.edu.cn/55971/list.htm)入口，不再弹相同机构登录页。这个状态来自本人报告，工具没有独立验证学校采购范围，也不会自动提交付费/文献传递申请。其他论文可作替代阅读，不能冒充原篇全文。

## 启用开放版本查询：只需普通联系邮箱

[Unpaywall官方API](https://unpaywall.org/api)要求普通联系邮箱，不是学校通行证密码。可在本机PowerShell输入：

```powershell
$env:UNPAYWALL_EMAIL = Read-Host "输入普通联系邮箱（非学校密码）"
python literature_helper.py collect "你的DOI"
```

邮箱仅在本次终端环境，按API要求发给Unpaywall；源码、公开报告和结果不记录邮箱。未配置时结果明确标记 `NEED_CONTACT_EMAIL`、查询未执行，不能把它写成“没有开放版本”。`best_oa_location`不能代表所有可选位置，本版也检查当前 `oa_locations`，不使用仍在禁运中的位置。

## 本人官网访问与整理

需要时由本人在官网注册/登录、查看权限和保存PDF。是否保持登录由网站和浏览器决定；脚本不读取浏览器Cookie，不会在本人登录后自动继承订阅下载权限。

```powershell
python literature_helper.py access 10.3390/metrology5040071 --via carsi
# 或 --via webvpn；登录后按官方平台数据库导航进入
python literature_helper.py --output "D:\文献" --inbox "D:\文献收件箱" import "自己下载的一篇.pdf" --identifier 10.3390/metrology5040071
```

本人下载后可用import复制整理、保留原文件。只有文件名可传给import，来源记录和文件使用SHA256去重，不覆盖不同内容。若只要链接：`collect/access --no-open`；`search --reading-list`仅生成清单；`search --collect`可收集后不启动浏览器。

## 其他接口

```powershell
python literature_helper.py search "ultrasonic flowmeter" --limit 5
python literature_helper.py lookup 10.3390/metrology5040071
python literature_helper.py oa 10.3390/metrology5040071
python literature_helper.py --output "D:\文献" download arxiv:1706.03762
python literature_helper.py guide 10.3390/metrology5040071
```

arXiv例子仅供工具演示，不是超声研究依据。下载白名单当前为arXiv、MDPI指定域名、PMC、SciTePress，其他开放库位置仍可能需本人处理；没有实现全网通用下载器或付费出版商全文API。

## MCP

```powershell
python -m pip install ".[mcp]"
python mcp_server.py
```

使用官方Python SDK的stdio服务；本人客户端配置可参考：

```json
{
  "mcpServers": {
    "papers-capture": {
      "command": "C:/你的Python/python.exe",
      "args": ["D:/你的工具目录/mcp_server.py"],
      "env": {"LIT_OUTPUT_DIR": "D:/文献", "LIT_INBOX_DIR": "D:/文献收件箱"}
    }
  }
}
```

十个工具：`search_papers`、`lookup_paper`、`locate_open_access`、`download_open_access`、`zju_access_guide`、`import_local_pdf`、`prepare_reading_list`、`open_paper_access`、`collect_paper`、**`search_and_collect`**。

- `prepare_reading_list`仅检索；`search_and_collect`实际尝试保存全文，默认最多3篇。
- `collect_paper`可传 `access_state="not_subscribed"`，按本人报告停止重复登录引导。
- `open_browser`默认false，明确true才请求打开结果页；批次不弹逐篇登录。
- 工具不修改客户端配置。浏览器打开请求不证明登录成功，认证状态保留UNKNOWN。

## 实际验证与边界

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python tests/smoke_mcp.py
# 以下会访问公开网络并保存一个样例PDF；output需使用未存在目录
python tests/verify_acquisition_workflow.py --output verification-local/自己的验收目录
```

42项离线测试与十工具MCP验收见[0.3.0验收记录](docs/验收记录_V0_3.md)。历史见[0.2.0](docs/验收记录_V0_2.md)及[0.1.0](docs/验收记录_V0_1.md)。

请求串行、间隔至少3.1秒；429停止。PDF限25MB并检查头尾，不能代替完整解析、恶意文件检查或论文身份认证。保留来源、候选尝试与文件哈希；个人文献/清单/环境不入Git。

[浙大电子资源管理办法](https://libweb.zju.edu.cn/2016/1014/c39581a1666449/page.htm)限制自动工具下载授权资料与超量集中操作，不能据此说“自动填密码被明文禁止”。本工具的公开PDF获取与本人机构认证分别处理。校园认证、出版商接口授权和本文获取率不由离线测试证明。

官方资料：[Crossref REST](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)、[Unpaywall API](https://unpaywall.org/api)、[Unpaywall数据结构](https://unpaywall.org/data-format)、[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)。
