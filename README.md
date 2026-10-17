# papers-capture：提示词到文献全文

0.5.6，2026-10-17。新增MDPI对应文件的直接保存；真实网站验收仍按实际文件核对。非浙大官方项目。代码MIT；文献按各自许可使用。

## 在agent中使用

直接用中文说明研究需求，例如“查找超声气体流量计的周跳、时差估计和置信度补偿方法”。调用agent先拆成1–4条专业英文检索式，再调用 `begin_literature_collection`；不需要另买翻译模型API或向工具提交学校密码。

任务流程：多检索式 → Crossref检索 → DOI去重与题名相关性初筛 → 公开PDF优先 → 必要时本人认证 → 核对本篇身份与访问结果 → 保存或退避。最多每式10篇、每任务30篇。检索覆盖不等于综述完整性，题名词匹配也不能代替学术筛选。

工具返回session_id、清单及逐篇状态。**启动成功、元数据和摘要都不计作全文；只有实际校验并保存的PDF计数。** 文件与来源清单只写配置目录，SHA256去重，不覆盖用户文件。

## MDPI自动保存（0.5.6）

作者第二批真实任务已有两篇IEEE和一篇ScienceDirect保存；最后一篇MDPI仍走旧Chrome下载分支，触发另存为，尚未计全文。本版把可对应的MDPI文件接入浏览器接收字节→本机服务校验→按论文名直接保存→继续下一篇，沿用插件中设置的目录，不更改Chrome全局下载设置。

先在MDPI文章页核对DOI，再用卷、期、文章号对应同篇/pdf或mdpi-res.com标准article_deploy文件路径；当前支持可按该约定核对的路径，不猜测其他期刊缩写、特刊或历史格式。不匹配的最终文件、HTML、403/429均停止，不回落到可能保存网页的旧分支。扩展更新后能从本任务已核对原页恢复同篇PDF新标签，不导出登录数据或临时链接。

14组MDPI模拟及已有IEEE/ScienceDirect回归通过，134项Python和17工具stdio验证通过。**MDPI真实免弹窗保存尚待本人Chrome刷新到0.5.6后验收；不能以软件通过替代。** 已保存的前三篇不重下，无需重新配对。

## 每次接续与下载错误（0.5.5）

0.5.4实测已从旧活动任务恢复到正确论文，PII匹配通过，但取PDF失败；从官网重新进入PDF后仍未自动保存。尚无HTTP细分证据，不能直接判为过期或无订阅。

现在每次本人点“开始／接续”或“检查当前论文”建立独立下载尝试；旧标签迟到的消息不能覆盖它，同次尝试多个PDF标签只下载一次。下载进行中复用当前尝试；新建标签若已快速跳到PDF，也先恢复论文身份再接续。错误明确显示服务器HTTP状态、网络/超时、格式/完整性或本机保存阶段，不再只显示FETCH_PDF。

只在ScienceDirect临时链接的声明期限确实已过时，自动返回已登记的同篇官网更新一次；不延长或修改签名、不重复登录、不对403/验证页盲目重试。题名保存和目录设置沿用，网页/中间页仍不计全文。

134项Python与31组ScienceDirect等软件检查通过。0.5.5本人普通Chrome实测：完成网站真人验证后，工具从本篇官网自动进入ScienceDirect PDF并直接保存，未点View PDF或阅读器下载；实际HTTP200/PDF、TRANSFER_SAVED，严格解析8页、2286033字节，题名与DOI对应，题名副本与哈希归档一致，EXTENSION_FETCH / PDF_RESPONSE。该次签名LIVE，未触发过期更新；真实更新能力仍只完成受控检查。此为本人已认证会话中的一篇ScienceDirect样例，不外推所有订阅或AIP。

完成保存后PDF预览页可以继续停留，文件已经以论文名写入保存目录。任务处理到末尾即结束：保存、无权限退避和本人暂缓均可能让当前篇结束，因此应分别查看实际PDF数和逐篇状态。更多文献由agent准备下一批，再在插件选择该批开始；批内逐篇接续。

## 多任务选择与接续诊断（0.5.4）

作者回报0.5.3后仍提示PDF未对应，尚未取得本篇文件。检查代码确认旧按钮传了所选任务，但后台忽略此编号且只用旧活动任务；这是一处明确缺口，尚无浏览器诊断能证明它就是作者该次失败的实际原因。

现在检查按钮使用任务选择；在本人点击检查或所选任务的接续中，当前PDF若与唯一待处理任务的官方登记精确匹配，会恢复到该任务。多份任务匹配时按明确选择/活动任务核对，否则暂停，不猜测。不重新检索、不重开登录或要求固定标签顺序。

窗口显示实际运行版本，优先选择当前页面匹配的任务。失败显示无任务、多个任务、官方对应缺失、错PII或DOI冲突；本机私有诊断最多8条，仅固定原因、版本、任务编号及公开PII，拒收完整网址、临时签名、Cookie、密码或输入值。126项Python与22组ScienceDirect接续等软件检查通过；真实Chrome的本篇保存仍待验收。

## 刷新与机构认证后接续（0.5.3）

ScienceDirect不再只依赖原父标签中的临时对应。工具为当前任务的待处理DOI查询Crossref官方主文章登记，核对出版商PII后持久保存；已有任务无需重新检索。刷新、标签顺序改变或认证在新标签返回时，用同一PII恢复文章与最终文件对应。错误DOI、错PII、相似域及已跳过论文均拒绝接收。

已选ScienceDirect文章在加载完成、重新激活，以及可见PDF入口/机构识别改变后自动检查。页面观察仅发重新检查通知，不读取学校登录输入值；有次数和时间上限，下载失败不循环请求。临时签名地址只在当次浏览器内使用，不保存到任务。无需新增扩展权限。

本次作者已能手动打开8页全文，但0.5.2因丢失对应未自动保存；0.5.3离线回归通过后仍需本机Chrome验证实际文件。不能把用户已打开PDF或旧“最近保存”记录算作本篇下载成功。

## AIP与学校数据库说明（0.5.2）

AIP是出版平台，本次条目期刊为Review of Scientific Instruments。摘要/购买页即使声明citation_pdf_url也不等于有全文；未识别机构时提示本人确认访问，身份匹配且明确机构无权限时退避。AIP PDF按DOI或卷/期/文章号核对后才接入直接保存，HTML/登录/验证响应停止，不触发HTM另存为。

插件“浙大数据库访问说明”在AIP论文打开[浙大AIP资源页](https://libdb.zju.edu.cn/s/lib/libtb/show/490)，其他情况下打开[数据库导航](https://libdb.zju.edu.cn/)。官方列出校内IP认证及校外WebVPN/统一身份认证；资源列为订购不保证每个年份/单篇都有权限。工具不据此声称2011样例可下载，也不自动改AIP代理路线。无权限条目和其他来源继续逐篇处理。

## 保存目录与论文名（0.5.1）

在插件窗口的“保存设置”填写完整目录，如D:\文献，点“保存设置”。只需设置一次，服务重启后保留；也可在本机私有.local-browser/settings.json设置save_directory。默认目录为文献库下papers，不入Git。此项是最终PDF目录，独立于Chrome下载目录。

IEEE及ScienceDirect身份已核对的文件现在由浏览器读取PDF字节，再交给已配对的本机服务直接保存，文件名为“论文题名.pdf”，省去Chrome另存为对话框。非法文件名字符替换为下划线，过长题名截短；同名不同内容加(2)、(3)，相同内容复用，不覆盖既有文件。文献库保留校验用哈希副本，任务file.saved_path指向用户可读文件名。

此路径不修改Chrome全局下载偏好，不模拟点击保存，不导出登录凭据；传给本机服务的只有任务编号、触发类型及完整PDF字节，不传出版商临时URL。完整PDF、25MB上限、任务身份及最终目录均校验通过才计数。目录不可写、网页/部分PDF、网络/访问失败会停下，不暗中换回另存为，也不反复请求。其他来源仍按各自既有路径验证，不宣称全站支持。

0.5.0实测已自动触发IEEE下载但仍弹保存窗口，因此没有记免点击通过。0.5.1已由本人普通Chrome实际完成一篇公开IEEE Access论文的无保存弹窗下载：题名文件及归档副本均存在，严格PDF解析12页、2627401字节，题名与DOI对应、两副本SHA256一致；实际来源EXTENSION_FETCH / PDF_RESPONSE。验收针对公开IEEE样例，不代表IEEE订阅、全部网站或ScienceDirect本次新路径已通过。117项离线及15组自动保存模拟另外记录，不替代真实文件核验。扩展可用host_permissions在服务工作者内请求跨站文件，依据[Chrome官方网络请求说明](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests)。

## 自动下载与本人授权

目标流程为：检索→打开论文→需要时本人在官网完成机构认证→回论文及PDF预览→工具自动下载、校验并归档。本人仍处理网站登录和验证；自动触发失败、权限不明或网站限流不算下载成功。

0.5.0旧路径在已选、身份已核对的任务标签页观察IEEE及ScienceDirect实际PDF响应，只读取Content-Type及对应文件地址；不读取Cookie、认证请求头、登录输入值或其他标签的文献，不修改网络响应。Chrome在浏览器内发起下载，saveAs:false；不通过模拟点击受保护的内置PDF阅读器实现。

IEEE原始iel7/ielx7文件编号纳入严格身份匹配；新响应不可见时，可仅查询本篇文章编号对应的最多5条下载记录，复用其文件地址重新发起自动请求。旧手工文件不当作新自动下载结果。临时链接仅留工作者内存，不写任务或日志。下载请求每次任务打开只自动尝试一次；安全验证响应停止自动重试。

归档记录下载方式EXTENSION_REQUEST或BROWSER_NATIVE、触发来源PDF_RESPONSE/MATCHED_DOWNLOAD_URL/DOCUMENT_LINK/READER_BUTTON，以及Chrome可提供的extension_initiated标记。只有实际通过PDF检查并保存的文件计数。新实现的离线检查通过不代表网站已实测成功；ScienceDirect此前通过的是本人点阅读器下载后的自动归档，IEEE此前只验证到12页手工文件，不能把两者称为全自动。

下载接收只允许已配置目录或系统已知Downloads目录下严格的papers-capture/任务号/序号.pdf，不读取其他下载文件。Chrome采用其他自定义下载根目录时仍须配置。历史失败提示与本次结果分开显示，归档成功后会显示保存方式。

依据：[Chrome下载API](https://developer.chrome.com/docs/extensions/reference/api/downloads)、[只读响应观察](https://developer.chrome.com/docs/extensions/reference/api/webRequest)。本版新增webRequest声明，用于上述已选文件的响应观察；扩展需要本人刷新到0.5.0后才能真实验证，不索取校园凭据。

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

### 自己启动本机服务（Windows）

在源码目录双击 **启动文献服务.cmd**。已运行时复用当前服务，未运行时在后台启动；就绪后请求默认浏览器打开本机连接页。关闭启动窗口不停止后台服务，不需每次让agent启动。重启电脑或服务进程退出后再运行即可；没有设置开机自启。

启动器使用本目录已有.venv，不下载或重装依赖；缺环境或端口/配置不匹配时保留任务并显示提示。默认浏览器若不是装有扩展的Chrome，回Chrome使用扩展即可；打开127.0.0.1:8766/pair网页本身不会启动后台。

文献库优先级为命令行--output、LIT_OUTPUT_DIR环境变量、本机私有.local-browser目录的service-launcher.json中output_dir、默认downloads；配对目录可由LIT_BROWSER_DIR指定。个人路径和配对目录不入Git。本机启动配置例如：

    {"output_dir":"D:/文献库"}

安装后也可使用papers-capture-service --open；源码方式为python service_launcher.py --open。已有服务必须匹配文献库和配对目录指纹，未知或不匹配不强制关闭它。升级前的服务没有指纹时需先核对进程再更新；当前作者本机已经更新完成。

0.4.6启动入口本身未修改扩展；本次0.5.0自动下载实现修改了扩展，需要本人刷新到0.5.0。服务就绪不证明IEEE网络、学校订阅或PDF下载成功。

### 中断后继续

网络中断、停止聊天和本地服务退出分别核对。普通浏览器任务调用 `resume_collection(session_id)` 会先检查并恢复本机服务，再保留同一任务、已保存PDF和当前篇索引；不必重新运行 `use_regular_browser`，后者会重新设置浏览器接续阶段。启动失败明确报错，原任务断点保持不变。

已安装扩展且原配对仍有效时，直接点扩展读取任务并检查当前论文；不用重新安装，也不重新索取密码。普通 /pair 地址可用于检查页面是否可达，不能仅凭它的初始文字判断扩展已配对；只有配对失效时才由工具重新打开配对入口。服务尚未安装为开机自启，重启电脑或程序退出后可能需要恢复。只保存任务状态，不保证网站登录永不过期，也不能把“服务在线”记为IEEE订阅下载成功。

原下载先保存在浏览器下载目录下 `papers-capture/<任务号>/`，Python核对专用目录和完整PDF后复制到文献库，保留原文件。浏览器使用自定义下载目录时，须设置 `LIT_BROWSER_DOWNLOAD_DIR` 为真实下载根目录；无法核验时拒绝导入，不冒称成功。

本机作者已在Chrome完成扩展加载和配对；真实学校订阅样例仍在验收。其他使用者的扩展安装和学校认证需要本人参与。普通浏览器可打开页面不等于学校有全文权限，也不保证下载链接必然可用；其他来源仍可受网络、机构许可和平台规则限制。工具不授予订阅或批量使用许可。

### IEEE文章身份识别

IEEE页面可能有PDF入口和机构标识，却没有扩展原先读取的DOI元标签。0.4.3保留Crossref为该DOI登记的IEEE主文章网址，以准确文章编号核对当前页及预览/原生PDF下载；存在有效但冲突的页面DOI时仍拒绝，不从参考文献或购物入口猜身份。旧任务可从已核验的对应关系补入，不要求重复安装扩展；本次加载新代码需在扩展管理页刷新一次。

作者所选10.1109/ACCESS.2022.3181725发表于IEEE Access，为公开获取样例。这可以检验IEEE下载与归档，不作为浙江大学订阅接续成功的证据。0.4.3当前真实PDF仍待本人浏览器复验；识别修复测试通过不记为下载成功。

### IEEE校园网与代理分流

IEEE开始任务时显示访问路线提示；明确418进入NEED_IEEE_NETWORK_ROUTE，暂停并保留论文，不判断为无订阅。已经匹配的IEEE预览页没有可提取链接时，可在本人确认完整PDF可读后点阅读器下载，工具按同篇编号接收；这条退路需要本人操作。

Windows手动系统代理用户可点“IEEE校园网直连”：只向ProxyOverride添加ieee.org及*.ieee.org，保留现有条目、代理开关和代理地址。点“撤销IEEE直连例外”可移除本工具添加的条目，保留后来其他程序增加的例外。该系统例外也作用于其他遵循系统代理的应用访问IEEE；工具不会默认替新用户启用。备份只在私有浏览器目录ieee-route.json，不入Git。

PAC配置不覆盖，其他平台给出原代理软件中设置DIRECT的人工路线。浏览器专用代理、策略或TUN可能决定实际连接；本机规则已配置不等于Chrome实际直连，更不等于PDF已保存。代理客户端重写例外后，已启用该策略的任务会暂停提示，不静默覆盖未知配置。

本机CLI也可由agent显式使用（默认不改设置）：

    python ieee_network.py status
    python ieee_network.py enable
    python ieee_network.py restore

作者本机已明确要求IEEE不走代理；实际配置并核对IEEE绕过为true、聊天域名绕过为false，原代理开关及地址保持一致。一次直连HEAD响应202，未当作PDF或订阅成功。作者加载0.4.4后仍报告418；系统例外仍在，实际PDF数0。这一轮配置没有解决真实浏览器访问。

### Chrome内的IEEE直连（0.4.5，按需启用）

Chrome官方明确proxy不能列作可选权限，因此本版在manifest声明必需proxy权限，更新或加载时由本人确认浏览器权限提示；不能用运行时permissions.request索取它。扩展默认不改代理，只有在“IEEE网络设置”里点“Chrome：仅IEEE直连”才配置。先读取Chrome当前代理模式和控制来源；PAC、自动代理或更高优先级策略/扩展不自动覆盖。

已有固定代理时只追加ieee.org和*.ieee.org例外，保留原代理服务器、协议与既有例外。Chrome使用system模式时，仅在本机服务核对Windows启用了无PAC的环回手动代理后使用其当前模板；不硬编码本机端口或远端节点。系统代理开关、BatVPN配置和聊天应用设置不变。

设置后再次读回Chrome配置，完整对应且受本扩展控制才记BROWSER_RULE_CONFIGURED；失败撤销。该状态仅代表浏览器规则读回，不证明校园IP、机构授权、418消失或PDF下载。这个浏览器配置使用当前代理地址；启用期间保持原代理运行，关闭或更换代理前点“撤销Chrome的IEEE规则”。撤销只清除本扩展设置，由Chrome恢复下层最新配置；停用或卸载扩展也会清除其控制。范围包含正常Chrome窗口及继承它的无痕窗口。

“检查Chrome代理”只报告模式、控制来源及规则核对，网址、节点、IP、密码和Cookie不写入诊断。本机诊断只在私有浏览器目录，不提交Git。不修改路由器、伪造校园IP或自动处理网站验证。若规则已读回仍418，保留网络/站点拒绝未知，停止登录循环。

依据：[Chrome代理模式与例外](https://developer.chrome.com/docs/extensions/reference/api/proxy)、[设置优先级和撤销](https://developer.chrome.com/docs/extensions/reference/api/types)、[proxy不能作为可选权限](https://developer.chrome.com/docs/extensions/reference/api/permissions)。真实Chrome 0.4.5规则与IEEE下载仍需本人实测；12组代理与manifest检查不充当真实验收。

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
