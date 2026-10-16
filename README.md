# papers-capture：提示词到文献全文

0.4.3，2026-10-17。非浙大官方项目。代码MIT；文献按各自许可使用。

## 在agent中使用

直接用中文说明研究需求，例如“查找超声气体流量计的周跳、时差估计和置信度补偿方法”。调用agent先拆成1–4条专业英文检索式，再调用 `begin_literature_collection`；不需要另买翻译模型API或向工具提交学校密码。

任务流程：多检索式 → Crossref检索 → DOI去重与题名相关性初筛 → 公开PDF优先 → 必要时本人认证 → 核对本篇身份与访问结果 → 保存或退避。最多每式10篇、每任务30篇。检索覆盖不等于综述完整性，题名词匹配也不能代替学术筛选。

工具返回session_id、清单及逐篇状态。**启动成功、元数据和摘要都不计作全文；只有实际校验并保存的PDF计数。** 文件与来源清单只写配置目录，SHA256去重，不覆盖用户文件。

## 两种浏览器接续

### 专用浏览器

安装可选依赖：

```powershell
python -m pip install -e ".[mcp,browser]"
```

Windows默认使用已安装Edge；其他环境可安装Playwright Chromium，并设置 `LIT_BROWSER_CHANNEL=chromium`。工具使用独立浏览器目录；本人在网站选择机构、登录后返回论文页。工具只读取论文身份与权限指标，不读取登录输入框值、不导出Cookie。

学校名称不能证明单篇权限。已匹配DOI的论文页提供候选PDF后，实际取得完整PDF才记成功；只有机构识别加明确购买/无权限提示才退避。模糊页面、网络错误和401/403保留待本人核对。网站验证码由本人处理，来源429停止整批。

一篇卡验证或请求超时，不阻挡其他候选检查；可恢复、跳过、关闭。空闲15分钟保存进度后退出；resume可继续，已保存论文不重下。

### 普通Chrome/Edge扩展

本次实测：AIP在专用自动化浏览器反复真人验证，而作者的正常浏览器能进入。Cloudflare[明确说明生产验证不支持Playwright等自动化浏览器](https://developers.cloudflare.com/cloudflare-challenges/reference/supported-browsers/)。因此新增普通浏览器接续，不将验证循环解释成学校无订阅。

1. 调用 `use_regular_browser(session_id)`，停止原专用后端，打开本机配对页。
2. 在能正常访问论文的Chrome/Edge扩展管理页，开启开发者模式，加载本仓库 `browser-extension` 目录（一次）。
3. 刷新工具打开的本机配对页，出现“已连接”。
4. 点扩展图标，选择任务并开始。需要机构认证时本人点击网站入口并登录；返回本篇论文后自动继续。新标签页登录返回或需要重新检查时，点“我已登录，检查当前论文”。
5. 浙大用户也可点扩展的“打开浙大机构认证（CARSI）”，本人选择浙江大学和IEEE或Elsevier SD。[浙大图书馆官方指引](https://libweb.zju.edu.cn/2022/0408/c39479a2515130/page.htm)列出这些访问路线；机构认证仍不保证具体论文已订阅。

ScienceDirect优先点击官网View PDF，跳转到精确的pdf.sciencedirectassets.com文件域后按原论文PII核对，再下载新生成的临时链接；不对Chrome内置PDF阅读器注入页面脚本。下载准备页和IEEE预览页先在浏览器中打开，只有随后取得并校验的PDF计入全文；htm/html不算成功。扩展感叹号表示最近有失败，打开弹窗可看具体原因；完整PDF成功归档后清除。扩展只处理所选任务的论文标签；不申请Cookie读取、密码、调试器或学校认证网站读取权限。[浏览器下载API](https://developer.chrome.com/docs/extensions/reference/api/downloads#method-download)在浏览器内部使用当前会话，不将Cookie交给Python或agent。服务仅监听127.0.0.1:8766；配对能力凭据只在本机私有目录与扩展存储，不入Git。

若扩展下载请求返回Security verification网页，任务进入 `NEED_BROWSER_SAVE` 并停止自动重试。此时需本人在已能显示完整论文的PDF阅读器点一次下载，扩展按同篇PII接住原生文件或当前篇缓存保存，再自动校验归档；这条路径需要人工保存，不能称全自动。

### 中断后继续

网络中断、停止聊天和本地服务退出分别核对。普通浏览器任务调用 `resume_collection(session_id)` 会先检查并恢复本机服务，再保留同一任务、已保存PDF和当前篇索引；不必重新运行 `use_regular_browser`，后者会重新设置浏览器接续阶段。启动失败明确报错，原任务断点保持不变。

已安装扩展且原配对仍有效时，直接点扩展读取任务并检查当前论文；不用重新安装，也不重新索取密码。普通 /pair 地址可用于检查页面是否可达，不能仅凭它的初始文字判断扩展已配对；只有配对失效时才由工具重新打开配对入口。服务尚未安装为开机自启，重启电脑或程序退出后可能需要恢复。只保存任务状态，不保证网站登录永不过期，也不能把“服务在线”记为IEEE订阅下载成功。

原下载先保存在浏览器下载目录下 `papers-capture/<任务号>/`，Python核对专用目录和完整PDF后复制到文献库，保留原文件。浏览器使用自定义下载目录时，须设置 `LIT_BROWSER_DOWNLOAD_DIR` 为真实下载根目录；无法核验时拒绝导入，不冒称成功。

本机作者已在Chrome完成扩展加载和配对；真实学校订阅样例仍在验收。其他使用者的扩展安装和学校认证需要本人参与。普通浏览器可打开页面不等于学校有全文权限，也不保证下载链接必然可用；其他来源仍可受网络、机构许可和平台规则限制。工具不授予订阅或批量使用许可。

### IEEE文章身份识别

IEEE页面可能有PDF入口和机构标识，却没有扩展原先读取的DOI元标签。0.4.3保留Crossref为该DOI登记的IEEE主文章网址，以准确文章编号核对当前页及预览/原生PDF下载；存在有效但冲突的页面DOI时仍拒绝，不从参考文献或购物入口猜身份。旧任务可从已核验的对应关系补入，不要求重复安装扩展；本次加载新代码需在扩展管理页刷新一次。

作者所选10.1109/ACCESS.2022.3181725发表于IEEE Access，为公开获取样例。这可以检验IEEE下载与归档，不作为浙江大学订阅接续成功的证据。0.4.3当前真实PDF仍待本人浏览器复验；识别修复测试通过不记为下载成功。

## MCP接入与调用

```powershell
codex mcp add papers-capture --env "LIT_OUTPUT_DIR=D:\文献库" --env "LIT_BROWSER_DIR=D:\本机浏览器状态" -- "D:\工具\.venv\Scripts\python.exe" "D:\工具\mcp_server.py"
```

这是当前本机Codex客户端的MCP配置，不绑定某个模型。也可以使用可信项目的 `.codex/config.toml` 限定项目。按[官方说明](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)核对配置及刷新；配置完成不能代替实际工具发现和调用验收。

新流程的七个工具：

| 工具 | 用途 |
| --- | --- |
| begin_literature_collection | 中文需求+agent提供的专业英文检索式，启动收集 |
| begin_paper_downloads | 处理本人选定的DOI列表 |
| collection_status | 实际PDF数量、逐篇状态、当前需本人操作项 |
| resume_collection | 专用浏览器重试；普通扩展提示本人点检查按钮 |
| skip_collection_paper | 明确放弃当前论文，保留元数据 |
| close_collection | 停止任务，保留文件和进度 |
| use_regular_browser | 改用正常浏览器扩展，给出一次性安装与配对入口 |

原十工具保留。`search_and_collect` / `search --collect`仍是公开来源流程；新的完整认证流程使用上述begin工具。MCP默认写配置目录，不接收任意输出路径或口令。

## CLI

```powershell
python collection_workflow.py start "超声气体流量计周跳" --query "ultrasonic gas flowmeter cycle skipping" --query "ultrasonic time delay estimation envelope correlation" --per-query 5 --max-papers 10
python collection_workflow.py status <任务号>
python collection_workflow.py resume <任务号>
python collection_workflow.py skip <任务号>
python collection_workflow.py close <任务号>
python collection_workflow.py papers 10.5220/0007535905680572
```

CLI的中文输入也须显式提供英文query；专业翻译由agent完成，脚本不把固定默认词冒充完整翻译。旧版独立公开检索/下载/手工导入入口保持：

```powershell
python literature_helper.py search "ultrasonic flowmeter" --limit 3 --collect --open
python literature_helper.py collect "10.1016/0041-624x(71)90200-9" --access-state not_subscribed
```

Unpaywall可选普通联系邮箱：`UNPAYWALL_EMAIL`，不是学校密码；未配置明确标记未查询。公开路线支持指定arXiv/MDPI/PMC/SciTePress入口及Crossref匹配当前CC许可的链接；TDM链接不当OA，尚在禁运的位置不自动获取。每来源串行并遵守限流。个人账号与学校认证分开判断；未订阅可查同一论文开放版本、文献传递或舍弃，其他论文不能冒充原篇全文。

## 验证

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python tests/smoke_mcp.py
node tests/test_extension.cjs
python tests/verify_auth_browser.py
```

75项离线、17工具真实stdio、普通扩展Chrome API模拟、真实浏览器本机授权夹具通过。真实联网公开PDF与实际MCP接入已核对；AIP真人验证循环如实记录。**本机授权夹具和扩展模拟不代表真实浙江大学订阅认证已经通过。** 具体进度见各版本验收记录。0.4.2记录作者再次失败：实际保存的是安全验证HTML；停止重复下载请求，改为本人阅读器原生保存的接收退路。这个退路现已实际取得并自动归档13页ScienceDirect论文，题名/DOI/原副本哈希一致；通过的是本人阅读器保存与自动归档，ScienceDirect全自动请求仍未通过，IEEE待验。

只读参考了作者既有提示词工具，未改原项目。其摘要TXT与目标数量回报未作为本工具全文成功依据；硬编码密钥未复制。下载PDF、浏览器认证状态、能力凭据、环境与个人任务报告不进入公开Git。
