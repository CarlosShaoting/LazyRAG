# LazyMind Windows 问题清单核查

> **2026-10-26 upstream main 复查说明（北京时间）**：本次已执行 `git fetch upstream main`，核对主仓库 `04e5c4bef8e134483611ef48040418e690a2fd4b` 及该提交锁定的 LazyLLM 子模块 `fd4465ec8a6922d9cb1c88e509ec45650ac2e1ed`。复查阶段使用独立源码快照；后续按用户要求创建了 `cst/fix_1026` 分支并实施修复，见文末记录。LazyLLM 子模块没有改动或提交。工作区未找到 `question_list.md`，`test_LIST.md` 为空，因此以本报告已有的 41 项为复查输入，无法核对缺失清单中的额外细节。
>
> **阅读方式**：下表新增“复查”列是最新判断；其余四列及后续 Windows 部署记录保留为 **2026-10-22 历史报告**，其中“本机”“已复现”“健康检查”等不表示本次执行结果。此次运行环境是 Linux，采用源码追踪、离线最小复现和针对性的既有 Go 测试；没有启动 Windows 桌面、真实模型请求或大文件导入。源码位置均相对上述锁定版本；标注“子模块”的路径相对 `algorithm/lazyllm/lazyllm/`。
>
> **优先结论**：#16 URL 丢路径、#32 动态 rerank 地址错误、#35 多 JSON 解析失败均仍存在；#7 不复用连接已复现，但耗尽未证明；#4 安装失败重建旧 venv 的代码风险仍在。特别纠正历史报告 #23：仓库存在 Office 转换服务源码；#30 的请求限制应区分客户端 15 MiB 与服务端 16 MiB。#35 有规则回退，不能等同于整个聊天崩溃。

核查日期：2026-10-22（北京时间）。源码：`C:\Users\bujiadong.vendor\LazyMind`，主仓库 `7683f8ec`，LazyLLM 子模块 `655cb3ba`。对照用户提供的 41 项清单。

## 核查范围与结论

这份清单不能原样套用到本机。它描述的 `D:\agent\LazyMind`、DSH、F 盘工作区和某些自定义脚本不属于本次源码运行环境。

本机最初运行的是安装目录中的桌面版，使用已打包的 LazyLLM 1.3.0；更新源码没有更新该安装包。按用户后续要求，已关闭桌面应用及其后台进程，并在 `.lazymind-local\audit-20261022` 建立独立的源码验证环境。没有改动桌面数据库，没有下载 Tutorial 子模块。

**已复现的源码问题**包括 URL 拼接丢失 `/v1`、SiliconFlow 动态重排误用 embeddings 路径、任务分类处理多段 JSON 失败、SQLite 代理不复用连接。**本机环境问题**包括源码算法 venv 中存在两份 pyarrow 分发信息，以及 uv 安装可执行入口时发生 Windows PE 资源更新错误。

另一些条目已经改变：Excel 有原始文件读取路线，动态模型地址会在调用时传递，`preparing` 不是可立即审批的状态，权限模式也会在服务端保存。

状态含义：**确认**表示有本机或最小复现证据；**条件风险**表示相应代码仍在，但没有证明本机发生原清单中的完整故障；**未发现/已改变**不代表对所有环境作保证；**待验证**表示证据不足。

## 41 项逐项结果

| 编号 | 清单问题 | 本项目结果 | 证据与适用边界 | 复查：upstream main（2026-10-26） |
|---|---|---|---|---|
| 1 | Git / submodule 必须代理 | 未发现当前故障 | 本次已成功获取主仓库和 LazyLLM 更新。GitHub 连通性属于环境条件，不能据此要求所有部署配置代理。Tutorial 保持禁用。 | **环境项，不能认定上游缺陷。** 本次 `git fetch upstream main` 成功；代理需求取决于网络。未做新的子模块网络下载。 |
| 2 | GOTMPDIR 不存在导致 Go 构建失败 | 未复现所述故障 | 当前 `runtime_env.go` 使用宿主 GOCACHE/GOMODCACHE，不再看到清单描述的默认 `build/cache/go-tmp` 设置。本次源码 manager、Core、代理已编译。验证脚本使用独立 Go 临时目录。 | **未发现清单所述默认配置。** `local/local-runtime-manager/runtime_env.go:37` 设置宿主 Go 缓存，未设置 GOTMPDIR；上游快照的相关 Go 测试可编译运行。用户自行指定不存在目录仍属环境错误。 |
| 3 | Windows pnpm isolated 必然缺依赖 | 未发现当前故障 | 本机实际为 isolated，frontend/node_modules 是指向 local/build 的 junction。Vite 启动、已有前端测试和转换均成功，不能把 junction 本身认定为根因。 | **“isolated 必然失败”不成立。** `local/local-runtime-manager/frontend.go:238` 按 pnpm 虚拟目录检查依赖；链接本身不证明缺包。本次未在 Windows 安装 pnpm，原机器的成功记录不作为本次结果。 |
| 4 | Python 安装、缓存、并发问题 | **确认本机安装阻塞；部分机制已有保护** | uv 安装 LazyLLM 1.4.0 时 `Failed to update Windows PE resources`；官方失败回退随后清空并重建源码算法 venv，种子包安装再次失败。`acquireAlgorithmPythonLock` 已用锁串行化共享 venv 的算法安装。详见后文。 | **代码风险确认，PE 故障待 Windows 验证。** `local/local-runtime-manager/algorithm_service.go:280` 在任意安装错误后调用 `createVenv(..., true)`，仍可能破坏旧环境；同文件的共享安装锁已存在，不能再断言没有并发保护。 |
| 5 | faiss / pystemmer / fonttools 安装坑 | 未复现所述特定错误 | 本次 pip 重建成功安装 pystemmer 3.1.0。faiss/fonttools 所述故障未复现，Milvus/RAG 可选组件未做完整部署；没有应用 `--no-deps` 或关闭隔离构建。 | **环境/依赖安装项，待验证。** 本次没有在 Windows 安装 faiss、pystemmer、fonttools，无法确认原特定错误，更不能凭旧机器的成功安装判定最新上游全部正常。 |
| 6 | NumPy 与 pyarrow 冲突 | **确认环境异常，未确认清单中的 ABI 因果** | 启动前 uv pip check 报 `pyarrow-19.0.1.dist-info` 与 `pyarrow-26.0.0.dist-info` 同时存在；NumPy 分发为 1.26.4。重复分发信息不等于已证明实际加载 pyarrow 26，也没有复现原清单中的 NumPy ABI 崩溃。 | **环境项，未确认上游 ABI 缺陷。** 重复 dist-info 是原机器状态；本次未取得该 venv，也未复现 NumPy/pyarrow ABI 错误。 |
| 7 | SQLite HTTP 连接耗尽 | **确认连接未复用；耗尽未压测** | 实际调用 `sqlite_proxy.Connection._call` 12 次，服务端看到 12 个客户端端口，Connection 均为 close。仍使用 urllib.urlopen；没有诱发本机 socket 耗尽或写操作重试。 | **连接不复用已复现；端口耗尽未证实。** `algorithm/lazymind/common/database/sqlite_proxy.py:342` 仍逐次 urlopen；本次 12 次真实 `_call` 对临时 HTTP 服务产生 12 个客户端端口，均为 Connection: close。 |
| 8 | Relay 命令行超长 | 已有 Windows 处理 | `algorithm_service.go` 在 Windows 设置 `LAZYLLM_PASS_ARGS_BY_FILE=1`；Relay 支持参数文件。此处无需重复加同一开关。 | **已有处理。** `local/local-runtime-manager/algorithm_service.go:761` 为 Windows 设置参数文件开关；锁定子模块 `components/deploy/relay/base.py:16` 支持该开关。没有复现其他来源的命令行超长。 |
| 9 | 源码 worker 缺 site-packages | 未复现；源码没有所述兜底 | 缺少组件 catalog 时，`pythonComponentSites` 返回 nil，environment 没有清单建议的 venv site-packages 回退。但 Relay 使用 sys.executable，实测源码 venv 的普通子进程保留同一 prefix 并可找到 requests。不能仅凭 catalog 缺失就断言 worker 一定丢包；完整 Relay/DSH 场景未测。 | **缺兜底代码仍在，但不足以认定 worker 缺包。** `local/local-runtime-manager/python_components.go:132` 无 catalog 返回 nil；Relay 使用 `sys.executable`（子模块 `components/deploy/relay/base.py:86`）。嵌入式/DSH 环境仍需专门验证。 |
| 10 | DSH 的 PYTHONPATH 泄漏 | 本机未发现 | 当前会话无该 DSH PYTHONPATH。算法服务会显式构建 PYTHONPATH，网关还会清理继承的 PYTHONHOME/PYTHONPATH/VIRTUAL_ENV。没有 `D:\LazyLLM` 泄漏证据。 | **未证实 DSH 泄漏。** `local/local-runtime-manager/algorithm_service.go:620` 构建算法 PYTHONPATH；`channel_gateway_service.go:183` 清理继承的 Python 环境变量。外部 DSH 启动链不在本次复现范围。 |
| 11 | SQLiteQueue 软锁死锁 | 条件风险，遗留锁行为已复现 | 仍用 SoftFileLock、共享 `.lazyllm_filesystem_queue.db`，没有 60 秒获取超时。临时样本中预存锁文件让 SoftFileLock 超时，FileLock 可获取未持有的同名文件锁；没有复现应用运行中的死锁。多个进程共享锁本身是正常同步。给数据库加 PID 后缀可能改变跨进程队列语义。 | **遗留软锁风险仍在，应用死锁未复现。** 锁定子模块 `common/queue.py:131` 仍使用共享 DB 和 SoftFileLock，未设置有界获取超时。本次 Python 环境没有 filelock，未重跑遗留锁实验；保留跨进程同步语义。 |
| 12 | Caddy 2.10.2 panic | 未复现指定构建问题 | 源码默认仍为 2.10.2；本机已有 caddy 的 Go 构建信息为 go1.25.11，不是清单的 go1.27.2。本次源码前端由 Vite 运行，没有证据支持“版本号相同就会 panic”。 | **仅确认版本仍为 2.10.2。** `desktop/scripts/build-windows-x64.ps1` 固定该版本；版本号不能证明指定 Go 构建的 panic。本次未执行 Windows Caddy。 |
| 13 | manager 不兼容 hoisted | 条件风险，当前未触发 | `prepareFrontendNodeModules` 仍建立链接；`frontendNodeModulesReady` 要求 .modules.yaml 和匹配的 virtualStoreDir。当前是可用的 isolated 环境；没有将其改成 hoisted。本次直接启动 Vite，避免为核查而重建现有依赖树。 | **布局兼容风险仍在。** `local/local-runtime-manager/frontend.go:238` 要求 `.modules.yaml` 含匹配的虚拟目录路径；不满足该条件的 hoisted 布局会被判未就绪。未复现完整 hoisted 启动失败；链接相关 Go 测试通过。 |
| 14 | esbuild TEMP 写入被拒 | 未复现所述故障 | Vite 和现有前端测试可执行。源码验证使用独立 TEMP/TMP；uv 的 PE 更新错误另列 #4，不能等同于 esbuild 缓存权限错误。 | **环境项，待 Windows 验证。** 本次没有运行 Windows esbuild，无法将 TEMP 权限拒绝认定为上游通用缺陷。 |
| 15 | Docker .env 污染本地模式 | 未发现当前污染 | local/config.env 使用 SQLiteStore、pipeline；算法环境由 manager 提供 SQLite proxy 和本机向量服务地址。没有把现有库删除或清空。 | **配置项，未确认上游必然污染。** manager 的 SQLite alias 环境相关 Go 测试通过；不代表用户现有 `.env` 无污染，需结合实际启动配置判断。 |
| 16 | SenseNova base_url 拼接 | **确认 URL 问题** | 实际调用源码 `_get_chat_url`：`https://token.sensenova.cn/v1` 变成 `https://token.sensenova.cn/chat/completions`，加末尾斜杠后保留 /v1。图片协议分支需要具体供应商请求验证，本次未发送模型请求。 | **确认仍存在，离线复现。** 锁定子模块 `module/llms/onlinemodule/base/onlineChatModuleBase.py:78` 的 urljoin 将无尾斜杠的 `/v1` 丢弃；有尾斜杠正常。图片协议分支未验证。 |
| 17 | 公网与本地自动登录冲突 | 设计边界，本机未触发 | auto-login 默认只允许 loopback；本机 LAN 自动登录开关为 false，验证通过本机前端和代理入口，没有部署公网穿透。Chat 的监听地址另见部署说明。 | **设计限制。** `local/local-proxy/internal/server/admin_session.go:23` 默认拒绝非 loopback 自动登录；公网使用不能假设继承本机自动登录，不等于鉴权缺陷。 |
| 18 | 公网登录降级/循环 | 条件风险仍在 | localSession.ts 对非 2xx 统一抛错；local 模式 /login 直接重定向聊天，仍保留 localSessionInitialized。清单描述的远程场景有依据，但本次没有公网穿透部署，不能声称已复现完整循环。 | **远程登录降级风险仍在，循环未端到端复现。** `frontend/src/runtime/localSession.ts:81` 非 2xx 统一报错，`frontend/src/router/index.tsx:104` 在本地模式将 /login 重定向聊天。失败后的远程人工登录路径仍需验证。 |
| 19 | 公网 Origin 被 CORS 拒绝 | 配置行为 | 默认白名单是 localhost / 127.0.0.1 / 配置的 LAN origin，没有用户清单中的公网域名。本次未部署该域名；拒绝未知 Origin 是当前配置预期。 | **预期配置行为。** `local/local-proxy/internal/config/config.go:101` 默认只允许本地 Origin；公网域名须显式配置，拒绝未知 Origin 本身不是 bug。 |
| 20 | 改 admin 密码后自动登录失败 | 条件风险 | 代理仍读取 bootstrap 用户名/密码获取或刷新管理员会话。改密后若缓存会话无法续期、环境仍是旧密码，会失败。本次没有修改现有用户密码。 | **条件故障仍在。** `local/local-proxy/internal/auth/admin_session.go:58` 刷新失败后用配置密码重新登录；改密但未同步配置会使重新登录失败，缓存仍有效时不一定立即发生。 |
| 21 | 中文注释 + GBK 吞配置 | 本机不适用 | 本机 .env、local/config.env、local-win.ps1 全部为 ASCII；系统默认代码页 936 下与 UTF-8 读取的配置键一致（21 / 123 项）。清单的 start-local.ps1 不在当前源码中。 | **待 Windows 配置实测。** 原报告的 ASCII 文件和代码页记录不能外推到最新部署；本次未用含中文注释的配置在 GBK PowerShell 下复现吞键。 |
| 22 | 缺 office-convert 导致 DOCX/XLSX 不能聊 | **已改变，广泛结论不成立** | 本地聊天 DOCX/PPTX 可走原生读取；xls/xlsx 绕过 Office 转 PDF，使用 pandas。Office 转换服务仍不属于此源码基线，老格式或真正的 PDF 转换需求另行处理。 | **广泛结论不成立。** `algorithm/lazymind/chat/engine/document_extractor.py:37` 原生读 DOCX/PPTX，`chat_excel_extractor.py:66` 用 pandas 读表格；旧 `.doc` 和真实 PDF 转换需求仍有外部依赖。 |
| 23 | office-convert Windows 五处适配 | 当前部署不适用 | 本仓库 compose 引用独立的 office-convert 镜像，当前没有该转换服务的本机 Python 实现可核对。不能把别处修改当成本项目已存在的源码。 | **原报告“无服务源码”需纠正；Windows 原生适配有风险。** 实际存在 `backend/office-convert-service/main.py`；`:53` 默认字体路径面向 Linux，`:538` 硬编码 libreoffice，`:553` 未传隔离环境。已使用 `Path.as_uri()` 和独立临时 profile；不能在缺原始清单时逐一确认所谓“五处”。Docker 路线不等于原生 Windows 路线。 |
| 24 | relocatable Python 启 soffice 必失败 | 待验证 / 当前不适用 | 本机未发现 LibreOffice 安装，也没有启动转换服务。没有证据支持“venv Python 必失败”这一普遍结论。 | **继承环境风险存在，“必失败”未证实。** `backend/office-convert-service/main.py:553` subprocess.run 未传 env，可能继承宿主 Python 变量；是否影响 soffice 取决于实际安装与环境。本次未运行 LibreOffice。 |
| 25 | soffice 残留占锁 | 本机未发现 | 未启动 soffice，也没有为本次检查杀任何其他 Office 程序。 | **未证实残留占锁；部分预防已存在。** `backend/office-convert-service/main.py:532` 每次转换使用独立 profile，并设子进程超时；未见同处显式清理整个进程树，超时后残留子进程仍需 Windows 验证。 |
| 26 | 文件夹选择弹窗根目录失败 | 条件风险，未复现 GUI 故障 | picker 脚本仍没有显式 RootFolder/SelectedPath；已使用 powershell -STA。未弹出交互选择框。CREATE_NO_WINDOW 本身不等于已证明桌面隔离或无法调用 GUI。 | **代码形态仍在，GUI 故障待验证。** `local/local-proxy/internal/server/workspace_picker_windows.go:12` 未指定 RootFolder/初始 SelectedPath，但已经使用 -STA；仅凭这些不能确认弹窗根目录失败。 |
| 27 | builtin shell 与 workflow 分工 | 设计行为，原描述需细化 | trusted_local_mode 默认 false；当前还有工作区绑定、逐操作授权和 workflow 条件控制。不能简化成“所有 workflow 都禁用 shell”或“只有 trusted 模式才可能有 shell”。 | **设计行为，原描述过宽。** `algorithm/lazymind/chat/engine/subagent/runner.py:416` 将 trusted、有效工作区权限和 workflow_full_trust 分别纳入宿主访问判断；工作区 workflow/host access 相关 Go 测试通过。 |
| 28 | Excel 经 PDF/OCR 导致结构丢失 | **主要路径已修复，并通过合成样本** | Core 的 isSpreadsheetDocument/normalizeSpreadsheetDirectParse 保留原工作簿。实际调用聊天提取器：两张表共 3 行完整读取，205 行文件返回预览并要求从原文件用 Python 分析；没有经过 PDF/OCR。仍需注意公式缓存、隐藏行和合并单元格等语义。 | **主要路径已处理。** `backend/core/doc/task_convert.go:51` 表格绕过 PDF 转换；`algorithm/lazymind/chat/engine/chat_excel_extractor.py:66` 读原始各 sheet，超过内联阈值转预览。本次核对代码，未重做原报告 Excel 合成样本。 |
| 29 | PID 复用误杀 | 已有部分防护，仍有边界 | 注册表持久化 StartID，枚举时会比较；installer 的 ForceKillTree 使用身份检查。但通用 forceKillProcessTree 仍按 PID 调 taskkill，pidFileRecords 会读取当前 StartID，不能据此宣称所有 PID 复用竞态都已消除。没有进行杀进程压力测试。 | **部分防护存在，仍有竞态边界。** `local/local-runtime-manager/process_registry.go:21` 保存 StartID；`:167` PID 文件路线取当前身份；`process_native_windows.go:47` 通用强杀仍直接 taskkill /PID。没有通过真实误杀实验确认发生概率。 |
| 30 | 大 Excel 知识库切块失败链 | 条件风险 / 未做大数据压测 | 当前已能原始表格读取，SQLite executemany 也按请求大小分批；15 MiB 请求边界仍在，超大的单行不能靠分批解决。没有导入 81 MB 或真实患者数据，45 分钟 embedding 链路未复现。 | **完整故障链未证实，超大单行限制仍在。** `sqlite_proxy.py:17` 客户端 15 MiB，`local/local-runtime-manager/sqlite_server.go:26` 服务端 16 MiB；executemany 已按编码大小分批，单行过大仍报错。未做 81 MB 导入或慢 embedding 压测。 |
| 31 | Milvus manifest os.rename | **源码部署条件下存在风险；覆盖语义已复现** | 检查前现有源码算法 venv 的 milvus_lite/storage/manifest.py 仍用 os.rename(tmp_path,target_path)；临时文件覆盖测试在本机返回 WinError 183。桌面打包流程已有 patch-windows-milvus.py，不能据此认为普通 pip 源码环境也自动打补丁。本次未启动可选 Milvus。 | **桌面打包已有补丁，普通源码安装待核实。** `desktop/scripts/build-windows-x64.ps1:582` 调用补丁；`patch-windows-milvus.py:49` 把 manifest rename 改为 replace。未安装最新源码环境的 Milvus，不能沿用旧机器结论断言当前 wheel 一定未修复。 |
| 32 | SiliconFlowRerank 缺 type | **确认** | 该 supplier 未覆写 type，基类返回 EMBED。动态基础地址 /v1 被解析成 /v1/embeddings；显式 /v1/rerank 则不受影响。 | **确认仍存在，继承方法离线复现。** 锁定子模块 `supplier/siliconflow.py:118` 未覆盖 type，rerank 基类也未覆盖；继承 EMBED 导致动态 `/v1` 解析到 `/v1/embeddings`，显式 `/v1/rerank` 正常。 |
| 33 | SQLite 事务 TTL 仅 5 分钟 | 条件风险，清单表述过宽 | 常量仍是 5 分钟，但 withExecutor 每次事务操作会 touch 并重置计时器，是空闲过期机制，不是每个活跃事务固定 5 分钟终止。慢 embedding 造成超过 5 分钟无数据库活动仍可能受影响。过期释放队列的现有用例通过。 | **空闲超时风险仍在，固定总时长说法不成立。** `local/local-runtime-manager/sqlite_server.go:25,418` 使用 5 分钟 TTL，并在每次事务请求重置；长时间无 SQL 可过期。本次过期事务释放等 SQLite Go 测试通过，不证明慢 embedding 全链路安全。 |
| 34 | WORKING / DELETING 毒药状态 | 当前桌面数据未发现 | 只读检查桌面 app.db：documents、knowledge_bases、doc_parse_state、doc_service_tasks 均为 0 行。没有卡死任务或同名残留的本机证据，没有改状态或删库。 | **待恢复场景验证。** 原机器空表不能排除上游状态恢复缺陷；本次未制造进程崩溃/删除中断，也未检查用户数据，因此不能判定已修复或确认仍会卡死。 |
| 35 | 任务分类 JSON 脆弱 | **确认，触发条件需修正** | 单个 JSON 后跟普通解释文本可以成功；后面再出现第二个花括号对象，会被 find/rfind 一并截入并产生 Extra data。详见源码最小复现。 | **解析缺陷确认，业务影响需收窄。** `algorithm/lazymind/chat/engine/prompts/task_profile.py:674` 多个未被单一代码块隔离的 JSON 对象触发 Extra data；单对象后普通说明正常。`:864` 会捕获异常并回退规则，不能直接写成整个聊天崩溃。 |
| 36 | dynamic supplier 没绑定 URL | **不能按原根因认定** | 构造函数仍用 self._base_url，但 dynamic_router.forward 会调用 _merge_dynamic_forward_kwargs，把 bucket.url 传给供应商 forward；聊天 forward 使用 runtime_url。本次最小复现确认动态 URL 已传递。无末尾斜杠时仍受 #16 影响。 | **原根因不成立。** 锁定子模块 `module/llms/onlinemodule/dynamic_router.py:114` 将 bucket.url 注入 forward，聊天 forward 使用运行时 URL。无尾斜杠丢路径归 #16，不是没有绑定动态地址。 |
| 37 | preparing 不显示审批 | **不能直接视为过滤 bug** | 后端 completePreparingOperation 正常会转成 pending/allowed；projectOperation 还故意将已被决策认领的 pending 投影为 preparing，避免重复审批。后端 Decide 本身拒绝非 pending。若长期 preparing，应查状态完成/索引/认领恢复，而不是直接让前端可审批。 | **过滤 preparing 本身不是 bug。** `backend/core/localworkspace/operations.go:184` 完成准备后转可决策状态；`approvals.go:289` 将已认领 pending 投影为 preparing。准备恢复相关 Go 测试通过，长期卡 preparing 仍需具体现场。 |
| 38 | Python 低完整性级别 | 本次检查的进程未发现 | 检查当时 3 个源码 Python 进程 token，均为 S-1-16-12288（High），不是 Low。这些进程由本次排查启动，不能据此推断普通桌面启动的权限；没有修改任何目录完整性级别或 ACL。 | **Windows 进程环境项，待验证。** 本次在 Linux，未检查 Windows token/ACL；旧报告的 High 进程记录不能证明普通桌面启动总是正常。 |
| 39 | write 的三个叠加 bug | **部分代码形态相同，完整结论未成立** | 见下文拆分。没有将“看到相同条件判断”直接等同于真实写入死锁。 | **不能确认“三个叠加 bug”。** `LocalWorkspaceControl.tsx:372` 保存权限；`backend/core/chat/conversation_logic.go:337` 读取服务端偏好；`algorithm/lazymind/chat/service/chat_service.py:1223` 构造 execution identity。授权前提不等于正常链路漏传；write 卡住未做真实模型复现。 |
| 40 | 动态 embedding 未配置、绑定跟会话 | 当前桌面未发现未配置证据 / 绑定是设计行为 | 桌面库中有通过验证的 embed_main、embed_image、reranker 等角色各 1 条；不能认定本机缺 embedding。KB 和工作区绑定按会话及用户隔离符合当前实现。独立源码环境不继承桌面模型配置。 | **配置状态待验证；会话隔离是设计行为。** 本次没有用户模型库，不能沿用旧机器角色记录认定已配置；工作区 owner scope/resolve 相关 Go 测试通过，不能因会话绑定就认定缺陷。 |
| 41 | DeepSeek 模型名称经验 | 内置目录已更新，服务端可用性未验证 | 当前 model_catalog.yaml 已有 deepseek-flash、deepseek-v4-pro、deepseek-v4-flash，清单所说内置只剩旧名称不适用于当前代码。具体供应商实时支持、权限及返回质量需其 API 验证，本次没有推断。 | **“内置仅旧模型名”不成立。** `backend/core/config/model_catalog.yaml:140,143,1049` 存在 deepseek-flash、deepseek-v4-pro、deepseek-v4-flash；只确认目录内容，未调用供应商验证名称、账号权限及效果。 |

## 需要优先处理的实际问题

### A. uv 自举失败会损失已有源码 venv

本次启动经历：已有环境出现两个 pyarrow 分发目录；Chat 要求安装当前源码的 LazyLLM 1.4.0；uv 安装入口程序时报 PE 资源更新失败；`preparePython` 随后调用 `createVenv(clear=true)` 清空现有环境，重建种子包再次遇到同类错误。

这比“pip 卡住”更具体。故障日志保存在 `chat-bootstrap-uv-failure.log`。后续恢复改用 pip 安装当前源码要求的依赖，桌面安装目录未改动。应考虑让安装失败保留既有 venv，使用新目录准备成功后再切换。

### B. URL / reranker / 分类 JSON

- `onlineChatModuleBase.py:78`：基础地址拼接需规范化末尾斜杠，保留调用方路径前缀。
- `siliconflow.py:118`：SiliconFlowRerank 的类型应与 RERANK 路由一致，同时覆盖静态/动态地址测试。
- `task_profile.py:674`：当前提取逻辑无法可靠处理多个 JSON 片段。修复需要明确选择对象及验证 schema，而不应仅依赖首尾花括号。

### C. SQLite 连接与文件锁

- `sqlite_proxy.py:342` 的每次 urlopen 建连已复现，连接池/会话复用应优先考虑；写 SQL 的重试还要处理幂等性，不能直接无条件重试。
- `common/queue.py:131` 的共享 SoftFileLock 有崩溃遗留锁风险；需要有界等待及恢复策略，同时保持跨进程队列语义。
- 普通源码环境安装可选 Milvus 时，要核实 Windows 补丁是否应用；当前打包脚本的修复只覆盖其负责的产物。

## #39 的三个子问题

1. **请求参数只在后台任务发送：代码确实如此，但“allow_all 必然失效”不成立。** LocalWorkspaceControl 会通过 saveUserPermissionPreference / updateWorkspacePermission 保存；conversation_logic.go:335 会读取服务端 UserPermission 并写入新会话。已有会话有冻结的权限/版本语义，需区分新对话、已有对话和权限更新时点。
2. **缺少 execution identity 会被拒绝：已用实际 guard 复现，这是授权前提。** chat_service.py:1254 会构建 `_workspace_execution`；是否走正常 Core 请求链、history_id/run_id 是否被上游传入，才决定是否触发问题。
3. **allow_all 下 write 卡住：未复现。** 现有工作区后端测试通过，但本次未用真实模型和现有用户会话完成完整写入链路，因此不将其标成已修复或确认故障。

## 已完成的验证与证据文件

- `source-probes.json`：真实源码函数的离线最小复现，SQLite 测试仅向临时本机模拟服务发请求。
- `native-probes.json`：当前 Excel 提取器、遗留文件锁以及 Windows rename 的合成样本测试。
- `http-probes.json`：Vite 模块转换及本机自动登录返回 200；受信 Origin 返回 200，未知 Origin 返回 403。
- `frontend-regressions.log`：localSession 与 LocalWorkspaceControl 共 53 项现有测试通过。
- `workspace-go-tests.log`：现有工作区授权/操作相关 Go 测试通过。
- `sqlite-go-tests.log`：SQLite 事务过期测试通过。
- `desktop-data-summary.json`：桌面库只读统计，不包含 API key、密码、用户对话或文档正文。
- `process-integrity.json`：源码 Python 进程实际完整性级别。
- `worker-import-probe.json`：源码 venv 与普通 Python 子进程的 prefix、requests 可用性和依赖版本。
- `dependency-check.log`：重建后的源码基础 Python 环境通过 pip check。
- `health.json`：服务健康检查，最终状态见下节。

## 源码部署与本次变更

隔离数据目录：`C:\Users\bujiadong.vendor\LazyMind\.lazymind-local\audit-20261022`。

前端入口：<http://127.0.0.1:5173/>。代理：127.0.0.1:5024。SQLite：19081。认证：18000。Core：18001。网关：18085。Chat：18046。

本次使用已有前端依赖直接启动 Vite，并编译当前源码 manager / Core / 代理。RAG、Milvus、解析服务、Evo 不属于本次基础服务启动范围。隔离环境不复制桌面的账号、模型密钥和业务数据。

最终检查时间：2026-10-22 11:16（北京时间）。前端、代理、SQLite、认证、Core、网关、Chat 的健康检查全部为 HTTP 200；安装版桌面进程剩余 0 个。本机自动登录与 Vite 模块转换也返回 200。

Chat 沿用源码 manager 的 `--host 0.0.0.0` 默认值；前端及代理入口使用 127.0.0.1。本次未配置公网穿透或外部域名。

源码算法 venv 曾被官方安装失败回退清空，本次已重建为当前源码所需的**基础环境**：LazyLLM 1.4.0、NumPy 2.4.6、pandas 2.3.3，pip check 无依赖冲突。原有可选 RAG/Milvus 依赖没有在这次基础部署中恢复，也没有复制桌面安装包中的依赖来伪装为源码环境。

本次没有修复上述业务源码，只增加排查脚本和证据文件、编译本地二进制，并恢复部署所需 Python 依赖。原有未提交代码改动保留。

停止本次服务：

```powershell
& C:\Users\bujiadong.vendor\LazyMind\outputs\windows-local-audit-20261022\start-audit-services.ps1 stop
```

启动基础服务与 Chat：

```powershell
& C:\Users\bujiadong.vendor\LazyMind\outputs\windows-local-audit-20261022\start-audit-services.ps1 baseline
& C:\Users\bujiadong.vendor\LazyMind\outputs\windows-local-audit-20261022\start-audit-services.ps1 chat
```

## 2026-10-26 本次复查验证记录

版本固定链接：[LazyMind 主仓库](https://github.com/LazyAGI/LazyMind/tree/04e5c4bef8e134483611ef48040418e690a2fd4b)。LazyLLM 使用主仓库 gitlink 指定提交，未使用子模块当前工作目录或其最新分支来替代。

- **离线最小复现**：从固定快照用 Python AST 提取原始 `_get_chat_url`、embedding URL 方法和 `_extract_json` 执行，保留方法体；重排同时检查供应商和 rerank 基类没有覆盖 type。这验证局部函数行为，不代表完整供应商网络请求。
  - `https://token.sensenova.cn/v1` → `https://token.sensenova.cn/chat/completions`；加尾斜杠 → `/v1/chat/completions`。
  - 继承 EMBED 的 rerank URL 处理：`https://api.siliconflow.cn/v1` → `/v1/embeddings`；完整 `/v1/rerank` 保持不变。
  - `{"ok":true} explanation` 成功；`{"ok":true} explanation {"extra":1}` 报 `JSONDecodeError: Extra data`。外层异常处理回退规则的结论来自源码核对。
- **SQLite HTTP 实测**：直接加载快照 `sqlite_proxy.py`，向临时 loopback HTTP/1.1 服务执行 12 次原始 `Connection._call`；12 个不同客户端端口，Connection 请求头均为 close。未连接实际业务数据库，也没有做端口耗尽压测。
- **运行管理器现有测试通过**：在快照 `local/local-runtime-manager` 执行 `go test ./... -run 'Test(SQLiteServer|PythonComponent|PrepareFrontendNodeModules|AlgorithmServiceEnv)' -count=1`，涵盖 SQLite 事务释放、组件安装识别、前端链接和算法环境；其他子包可能显示 no tests to run，不计为功能验证。
- **工作区现有测试通过**：在快照 `backend/core` 执行 `go test ./localworkspace -run 'Test(WorkspacePrepare|WorkspaceResolve|HostAccessSensitive|WorkflowHostAccess)' -count=1`，涵盖准备阶段恢复、工作区解析及宿主权限策略。
- **未执行的验证**：本次 Python 缺 filelock，未重复 SoftFileLock 实验；未安装 Windows Python/RAG/Milvus/LibreOffice，也未复跑历史报告中的 Excel、前端、GUI、token 完整性和健康检查。相关条目保留条件风险或待验证，不能引用历史机器状态证明当前上游无问题。

## 2026-10-26 `cst/fix_1026` 修复与实际部署验证

本节记录复查后的新工作；前文 2026-10-22 Windows 本机记录仍是历史资料。分支以 upstream main `04e5c4bef` 为起点，子模块检出该提交锁定的 `fd4465ec`，子模块工作区保持干净，没有提交子模块。

- **#4 已修复破坏性重试路径**：`local/local-runtime-manager/algorithm_service.go` 在已有算法 Python 可执行文件时，依赖安装失败立即返回错误，不再执行 `uv venv --clear`。新建 venv 首次安装失败后仍保留一次清空重试。新增 Go 回归测试确认原有 Python 文件不会被清空；已运行管理器全部 Go 测试通过（`go test ./... -count=1`，64.6 秒）。这是防止失败后清空的修复；安装器在报错前对旧环境做过的局部包修改仍需后续通过暂存目录安装方案解决，不能称为完全原子升级。
- **#7 已修复每次 SQLite HTTP 调用新建连接**：`algorithm/lazymind/common/database/sqlite_proxy.py` 改为每个代理 Connection 持有并关闭一个 HTTP(S) 连接；错误后关闭底层连接，**不会自动重试写请求**。新增真实本机 HTTP/1.1 服务测试，连续 12 次调用使用同一个客户端端口。Python 回归测试 1187 项通过。真实高并发、长时间空闲连接与网络中断后的业务链路尚未压测。
- **#35 已修复多 JSON 解析**：分类器按 `JSONDecoder.raw_decode` 读取第一个完整 JSON 对象；新增第二个 JSON 出现在说明文字中时仍保留有效分类结果的回归测试。既有异常回退逻辑保持不变。
- **Docker 中的当前源码测试通过**：现有 LazyMind 算法镜像作为一次性运行环境，挂载本分支 `algorithm`、锁定的 `algorithm/lazyllm` 与 `tests`，安装一次性 pytest 后执行上述 Python 测试，结果 1187 passed。镜像内原有 LazyLLM 版本与锁定提交不同，因此必须挂载本分支子模块才能测试当前代码。
- **Docker 服务部署与转换通过**：独立容器挂载当前 `backend/office-convert-service` 源码和临时目录，`GET /health` 返回 200；合成 DOCX 调用 `POST /v1/office/to-pdf` 返回 200，生成 16,974 字节 PDF。测试后已停止并移除独立容器；未修改原有 Docker 项目的业务数据。尝试重新构建该镜像时基础镜像下载较慢，随后改用已有镜像挂载当前源码完成实际服务验证；此项不代表已验证 Dockerfile 的从零构建。
- **Windows 原生启动未完成**：在 WSL 中 `make local-win-doctor` 通过；`make local-win-up` 调用 Windows Go 编译时，对 `\\wsl.localhost\Ubuntu\...\go.mod` 返回 `RLock ... Incorrect function`，没有进入服务启动。Windows C 盘剩余约 4.6 GiB，当前仓库约 16 GiB，无法在本机安全复制整仓到 NTFS 目录重跑。请在有足够空间的 Windows 本地盘检出该分支后执行 `make local-win-up`，再检查 `make local-win-status`、桌面登录、模型请求及文件读写链路。

**仍需用户或上游处理**：#16 URL 拼接和 #32 SiliconFlow 动态 rerank 位于 LazyLLM 子模块，本分支未改动或提交子模块；需在 LazyLLM 上游修复并升级主仓库 pin。#11/#13/#18/#23/#24/#25/#29/#30/#33 的条件风险，及 Windows 安装、Excel 大文件、Milvus、真实模型、GUI/权限链路，仍需相应场景验证。以上 Docker 验证只能证明被测功能，不能代替完整 `docker compose up` 的跨服务测试。

## 2026-10-26 `cst/ppt_template` 合并、主 Chat 工作流增强与 #869 修复

本节为 macOS 当前源码验证，不能代替前文 Windows 实机结果。当前分支为 `cst/ppt_template`。

### 合并记录

- 已合入 `upstream/main` 的 `6423896b5`（PR #868），合并提交 `56dfff210`。
- 已合入 `origin/cst/fix_1026` 的 `d63f7d34d`，合并提交 `6696a519b`。前一节的 Python 环境保护、SQLite 连接复用和分类 JSON 解析修复均已包含。
- `runner.py` 冲突保留上游规则：工作流根据真实产物、包内后置检查和配置的人审判断完成，普通 SubAgent 保留模型完成审核。合并前本地修改已恢复，没有覆盖现有 demo/chat 修改。新增修复仍在工作区，尚未提交或推送。

### 主 Chat 指令范围与 composite 联动

- 增加 `patch_artifact_text`：根据具体产物引用和唯一原文片段局部替换，保留其余正文及元数据；携带 revision 和 draft version 防止覆盖并发修改。完整 Markdown 的“只修改第一节”可局部修改，composite 则定位具体列表项。禁止空匹配、不唯一匹配和 HTML 全文误编辑。
- 主 Chat 和下发步骤的指令明确保留编辑范围，显式页码优先于当前焦点；仅修改大纲时停止，不自动重跑后续步骤。新增/插入/删除/重新生成按已有步骤执行，并传递页范围与关联素材要求；本次未新增通用的跨素材增删页事务，不将提示词约束描述为模型端到端保证。
- PPT 的 composite 标签声明同一个 `page_group: presentation`，共享当前页。拖动/交换页序时将已生成的关联列表一次提交；空的可选列表跳过，非空但页数不一致则拒绝。
- 后端要求完整有效的页序排列，并在一个事务中修改所有关联列表；任一版本冲突整体回滚，成功后通知界面刷新。主 Chat 可直接调用 `reorder_artifact_pages`，不用回退步骤。SDK 读取产物同样遵循保存后的视觉顺序，避免界面与工具按不同页码读取。
- 页序使用稳定 `list_index` 与视觉顺序映射，不改写产物身份。已经导出的 PPTX 二进制不会因面板排序自动变化，仍须重新导出；磁盘中按页码命名的生成源文件与全部增删页场景尚需端到端验证。

### Issue #869

问题来源：[image_generator UNAVAILABLE、10 条 outline 失败、素材分析失败](https://github.com/LazyAGI/LazyMind/issues/869)。

1. **GLM 图片生成调用路径已修复。** 旧适配器依赖 `zhipuai`，且将 `image_size`、`batch_size`、`priority` 等内部参数传入供应商 SDK。增加应用层 GLM 图片 HTTP 适配器，使用本次请求所选模型、base URL 和该角色密钥，只提交 `model/prompt/size`；多图按单图请求逐次执行，不自动重试生成请求。返回图片下载后沿用现有上传、签名及公开结果脱敏逻辑；批次失败清理已下载文件。其他供应商继续原有路径。
2. **不通过降级 PyJWT 修复依赖。** [PyPI zhipuai 元数据](https://pypi.org/pypi/zhipuai/json)中的旧 SDK 要求 `pyjwt>=2.8,<2.9`，与当前 MCP 依赖冲突。此图片路径直接使用已有 `requests`，无需新增旧 SDK 或改变 PyJWT。接口参数参考[智谱 CogView-4 官方文档](https://docs.bigmodel.cn/cn/guide/models/image-generation/cogview-4)。
3. **补齐失败日志。** 外部工具记录可用性、schema、执行及请求异常阶段；GLM 路径记录生成/下载阶段、HTTP 状态和异常类型。不记录密钥、提示词、供应商异常正文或图片 URL，前端继续使用安全的公开错误。
4. **10 条 outline 的完成误判已随 #868 修复并补回归。** 新增 9/10/11 条真实产物的 runner 测试，最终摘要包含“全部通过，无失败项”仍成功，不调用额外模型裁判。没有发现或新增“最多 9 页”的限制。
5. **素材收集分支补回归。** 测试读取当前 PPT 工作流的真实输出声明，全部必需产物存在、可选 `skip_material_collection` 缺失时成功；缺少必需 `requirement_analysis` 且无可提交正文时仍失败。不能用跳过素材收集来规避完成判定。
6. **复现边界。** 当前源码中注入有效 `text2image` 后，`image_generator` 可用性检查可通过，未复现所有配置下都为 false。新增测试使用真实注册表、ToolManager、配置注入及图片结果处理，只在供应商 HTTP/下载边界模拟；没有调用用户付费模型，也没有在 Windows 0.4.0 安装包中实测。若实机仍不可用，新增阶段日志用于进一步定位，不能宣称所有 UNAVAILABLE 原因均已消除。

### 本次验证

Python 使用仓库算法环境 `local/build/deps/python/algorithm/bin/python`，并设置 `PYTHONPATH=algorithm:algorithm/lazyllm`，明确使用仓库锁定的 LazyLLM 源码。只使用 `PYTHONPATH=algorithm` 时本机安装版 LazyLLM 缺 `MCPToolNameError`，导致两个接口测试失败；改用仓库源码后通过，没有以跳过测试规避。

- runner、外部工具、GLM 图片、按需媒体配置、SQLite proxy、任务分类器：**1332 passed**。其后补充静态 GLM 配置和下载失败清理用例。
- GLM 图片（含补充用例）、工作流选择、SDK、Toolkit：**186 passed**。两组有重叠，不合并计算总数。
- `frontend` 的 `vitest.workflow-panel.config.ts`：**22 文件 / 181 测试通过**。
- `backend/core`：`go test ./workflow ./externalcapability ./modelconfig -count=1` 全部通过，包含关联排序事务/冲突以及外部模型配置传递测试。macOS Security API 存在既有弃用编译警告。
- `local/local-runtime-manager`：`go test ./... -run 'TestAlgorithmPreparePython' -count=1` 通过，验证已有 Python 环境在依赖安装失败时保留；其他包的 no tests to run 不算功能覆盖。
- 新增图片适配器、图片测试及外部工具文件 flake8 通过；改动的工作流面板、分组工具、store/request 的 ESLint 通过；`git diff --check` 通过。
- runner 测试文件原有多处 lint 报错仍存在，新增回归部分没有增加这些错误。此前全量前端类型检查有其他文件错误；PPT 广义契约测试有既有 `exposed: false` 预期冲突；命名检查会命中现有未跟踪 demo 文件。未修改这些既有内容来取得全绿结果。
- 尚未验证：Windows 原生运行、真实 GLM 出图、真实模型对主 Chat 中文指令的全流程执行、所有增删插入与重新导出 PPTX 场景，以及完整 CI 平台矩阵。

### 2026-10-26 取消 PPT 导出页数上限

- 移除 `/api/workflow/ppt/export` 对超过 30 页的固定拒绝逻辑；这是 HTML 转可编辑 PPTX 的导出限制，与 #869 的 10 页完成误判不同。
- 新增 31 页、100 页回归，使用真实路由和临时文件，仅模拟导出服务边界，确认所有页面完整传给导出器并返回文件。没有实际渲染 100 页。
- 使用仓库 LazyLLM 和本机 Pandoc 执行 `test_workflow_smoke_tools.py`：11 passed。文件内既有 E306 lint 问题未改动；新增部分无 lint 错误。

## 2026-10-26 智谱模型目录与 LazyLLM supplier 补齐

依据[智谱官方模型概览](https://docs.bigmodel.cn/cn/guide/start/model-overview)及对应 API 文档更新。本节替代前述 #869 中“应用层 GLM 图片 HTTP 适配器”的最终实现描述：图片适配已下沉到 LazyLLM，删除本次此前新增的临时 `glm_image_generation.py`，LazyMind 恢复通过统一 `AutoModel` 调用。按用户要求，**本轮没有重启服务**，运行中的进程尚未加载这些修改。

### LazyLLM

- 更新 GLM 模型清单和类型映射，识别 GLM-5.3/Flash/FlashX/Legal、5.2、5.1、5V-Turbo、4.6V、AutoGLM-Phone、GLM-Image、ASR-2512 等。将 CogVideoX/Vidu 从图片类型修正为视频类型。
- 新增 `GLMTTS` 和 `GLMText2Video` supplier，沿用基类自动注册。TTS 使用 `/audio/speech` 返回编码音频文件；视频使用 `/videos/generations` 创建任务、`/async-result/{id}` 轮询并下载结果，覆盖 CogVideoX 与 Vidu 的文生视频、图生视频、首尾帧、参考图对应模型。
- GLM 图片与 STT 改用已有 requests，不再依赖旧 zhipuai SDK/PyJWT。图片转换工具参数为供应商参数，多图逐次请求，内部调度字段不传入 API；STT 发送 multipart 并关闭文件句柄。
- 动态角色继续使用请求所选模型、base URL、角色密钥；同一模型对象在后续请求换密钥/地址时重新读取配置。生成请求不自动重试，视频轮询有截止时间；失败信息与日志不包含供应商原始正文或密钥，下载生成文件不附带模型鉴权头。
- 修正聊天、Embedding、Rerank 自定义 base URL 的路径保留；标准模型名称按 API 名称发送。新视觉模型可发送图片，远程图片 URL 不再被错误包装成 `data:None;base64,...`。
- 图片生成结果在整批下载成功后才写临时文件，失败批次不会留下前几张图片的临时文件；后续上传签名仍由 LazyMind 负责。

### LazyMind

- GLM 目录新增 `glm-5.3-flashx-legal`、`cogvideox-3`、`cogvideox-flash`、`viduq1-text/image/start-end`、`vidu2-image/start-end/reference`；增加实际 API 名 `cogview-4-250304`，保留旧 `CogView-4` 条目和 supplier 别名，避免目录同步清掉现有 CogView 选择。
- 按官方文档将直连 GLM-5.3-Flash/FlashX/Legal 上下文标为 1M，Embedding-2/3 上下文从原配置的 512/3072 修正为官方标注的 8K。不同供应商的同名托管模型参数不随此变更。
- 动态 runtime_models 增加 `tts` 角色，使默认模型设置中的 TTS 能注入 supplier；不为用户自动选择付费模型或写入密钥。
- 移除默认目录中误标为普通 TTS 的 `GLM-4-Voice` 和 `GLM-TTS-Clone`。它们与 Realtime、GLM-OCR 分别使用音频对话、音色管理、实时会话或 layout_parsing 接口；本次没有实现这些独立协议，也不将它们冒充已支持的普通模型角色。现有目录同步规则会在后续启动时清理已移出的内置默认条目及其默认选择；自定义模型不在此清理范围。

### 验证与交付状态

- 使用 `PYTHONPATH=algorithm:algorithm/lazyllm`：supplier、真实外部图片工具注册/配置注入、动态模型配置、运行角色、模型验证接口及工作流能力声明相关测试 **100 passed**。
- 测试覆盖目录中所有 GLM 模型可实例化到对应 supplier；视频一次创建、多次轮询、失败、空结果、超时；STT 文件释放；TTS 音频返回；生成文件下载不泄漏鉴权；请求密钥/地址隔离；视觉图片消息与自定义 endpoint。只模拟 HTTP 边界，没有真实付费模型调用。
- LazyLLM `tests/basic_tests/Models/test_online_chat_model_runtime.py`：**70 passed**。
- Core `go test ./modelprovider ./modelconfig -count=1`：通过。
- 新增 supplier 与 Python 测试 flake8 通过；主仓库及子模块 `git diff --check` 通过。
- 本轮已修改 LazyLLM 子模块工作区（`supplier/glm.py`、`map_model_type.py`），尚未提交子模块、更新 gitlink 或推送。此前未跟踪的子模块文件保持原样。服务未重启，亦未验证 Windows 或真实 GLM 服务。

接口依据：[GLM-TTS](https://docs.bigmodel.cn/cn/guide/models/sound-and-video/glm-tts)、[GLM-ASR-2512](https://docs.bigmodel.cn/cn/guide/models/sound-and-video/glm-asr-2512)、[视频异步生成](https://docs.bigmodel.cn/api-reference/模型-api/视频生成异步)、[Vidu Q1](https://docs.bigmodel.cn/cn/guide/models/video-generation/viduq1)、[Vidu 2](https://docs.bigmodel.cn/cn/guide/models/video-generation/vidu2)。

## 2026-10-26：Workflow 启动输入绑定协议修复

- 复查本机 Chat 日志，14:52:28 和 14:52:37 两次 `trigger_ppt_workflow` 均在创建 Session 前失败：`input_bindings["generate_background_images"]: unknown field "name"`。当时尚未进入 analyze，并非依赖工具检测提前执行。
- PPT 的 `runtime.post_step_checks` 仍配置在 `analyze_requirements` 完成后调用 `check_ppt_workflow_capabilities`，按分析产物决定实际需要的能力，保持此机制。
- 根因：upstream #868 的输入绑定解析严格限制字段为 `resource_id`、`revision`、`content_hash`，Chat 的文字及附件导入却通过 `asdict(InputResource)` 额外提交 `name`、`mime_type`、`size`，形成接口不兼容。
- 修复 Chat 两条导入路径，仅提交固定资源引用；完整文件描述仍保留在资源存储，不放宽后端校验。
- 回归测试不再直接模拟已裁剪的绑定，而让真实 Chat 导入转换接收完整 `InputResource`，覆盖文字/附件以及对象/JSON 字符串两种工具参数输入。
- 验证：相关文件 flake8 和 git diff --check 通过；`test_workflow_selection.py`、`test_workflow_full_trust.py` 共 74 项通过，其中包括分析后能力检查的真实 PPT 脚本测试。未调用付费模型进行整套 PPT 生成。
- 按本轮授权完成 `make local-down` 后重新 `make local-up`（使用宿主 Go skill-bundler，避免依赖未运行的 Docker）；15:09 本地启动成功，8090 HTTP 200，加载本轮修复及之前的 GLM supplier/模型目录修改。

## 2026-10-26：统一输入预处理与澄清字段启动修复

- 增加 SDK 统一输入预处理，Workflow preparation 和外部 Skill task 入口共用，Chat 的文字/附件转换也复用同一逻辑。完整资源描述转换为引用，支持多文件列表并保留顺序、重复引用与版本哈希，不修改调用者数据；仅移除已知展示元数据，未知字段和非法引用继续交给 Core 严格校验。
- 15:17 日志确认另一处启动错误：`input must name an external material: target_customer`。发现模式把澄清字段提示为外部材料，模型提交后未按实际 package 分类。
- 现在启动前读取真实包契约：外部材料导入为引用；已声明但不属于外部材料的澄清答案追加到请求上下文，交给 analyze 使用；未知字段在导入前拒绝。修正发现模式的工具描述，避免将澄清字段称作外部材料。
- 新增 SDK HTTP 边界预处理测试，以及使用真实 PPT 澄清声明的发现/显式选择两种启动回归；验证原始请求和受众、风格答案均保留。
- 验证：新增/修改 Python 文件 flake8、git diff --check 通过；SDK、预处理、Chat 选择与分析后检查共 170 项测试通过。15:18 重启 Chat 成功，运行状态 ready，8090 返回 HTTP 200；未做真实模型完整 PPT 生成验收。

## 2026-10-26：多对话 Workflow 隔离检查

- 用户澄清是在询问另开图片工作流是否会与运行中的 PPT 对话冲突，尚未报告图片工作流实际失败。检查日志确认 PPT 已通过启动与 analyze，正在生成页面。
- 检查 Chat 每次请求绑定独立 LazyLLM SID（ContextVar）、每次 Workflow 工具注入创建独立 session_holder，后端步骤与产物按 session_id 查询。
- 新增两个线程同时启动同一图片工作流的回归，使用 barrier 强制 preparation 重叠，验证各对话分别绑定自己的 session，重复 trigger 不会串到另一对话，agentic_config 也保持隔离。后端请求用现有客户端边界模拟，未进行真实双模型端到端并发验收。
- 未修改运行时代码，未重启或打断正在生成的 PPT。

## 2026-10-26：图片工作流素材排版

- 截图中的材料摘要被挤在约 200px 的窄列内，右侧大片空白：网格 auto-fill 在空材料隐藏后仍保留空列。
- 通用 Workflow 网格改为 auto-fit，空列自动折叠；文字/JSON 材料占满整行，图片材料继续网格显示。最小列宽受容器宽度约束，避免窄屏溢出；显式配置的网格列规则仍保留。
- 仅修改前端布局，不改变工作流会话或生成逻辑。
- 验证：WorkflowPanel ESLint、git diff --check 通过；按本地模式环境变量完成 Vite 构建，8090 HTTP 200。前端静态资源已更新，刷新生效，无需重启 Chat；尚未对用户当前会话刷新后做视觉验收。

## 2026-10-26：真实图片搜索缺少配置的明确阻断

- 图片工作流的 image_search_tool / image_search_and_validate 在实际需要搜索且没有配置任何支持的搜索引擎时，抛出既有结构化能力缺失标记，包含网络搜索设置链接、配置 Tavily/Bocha 后重试的提示。
- PPT 的 ppt_search_web_images 使用相同检查（按它实际支持的 Tavily/Bocha 检查）。已有候选图片 URL 直接进入验证，不要求配置搜索；配置存在但没有图片结果仍返回 empty，和缺少配置区分。
- 更新素材收集提示：缺配置必须停止并提示，不能静默跳过、用生成图片替代或将 Wikipedia 文本当成真实图片收集；配置后重试收集步骤并保留已有产物。
- 新增测试覆盖图片旧/批量/PPT 三入口无配置阻断、配置存在但无结果、已有 URL 无需搜索。测试不访问真实网络或使用真实密钥。
- 尚未重启/重新加载运行时，避免打断用户现有生成任务；新工作流包提示需在服务重新加载后使用新会话验证，旧会话固定版本不会自动替换。
- 用户确认任务完成并授权重启后，16:04 已完成 local-down / local-up，加载本轮搜索检查与工作流包更新；服务启动成功。

## 2026-10-26：智谱多模态与 GLM-Image 编辑能力复核（未重启）

- 官方文档 https://docs.bigmodel.cn/cn/guide/models/vlm/glm-5.3-flash 明确 Flash/FlashX/Legal 接受图像、视频、文本、文件，输出文本；当前 catalog 已为三者保留 llm + vision=true，GLM-V 系列已有 vlm 类型。
- 官方开源仓库 https://github.com/zai-org/GLM-Image 明确支持图像编辑、多图条件输入，并给出自部署 SGLang /v1/images/edits 示例。
- 智谱托管模型页 https://docs.bigmodel.cn/cn/guide/models/image-generation/glm-image 仍注明文本输入；图像生成 API https://docs.bigmodel.cn/api-reference/模型-api/图像生成 只公开 images/generations，未找到托管编辑参数/接口。不能将开源模型能力直接作为当前供应商 API 能力。
- 更新 catalog 中英供应商说明与模型注释，说明托管/开源区别；修正 LazyLLM 过于笼统的“不支持编辑”报错，明确是当前托管 API adapter 只接入文生图。未虚增不可调用的 image_editing 条目，未改正在运行的配置，未重启。

## 2026-10-26：LazyLLM CI 与子模块合并修复

- 为 GLMTTS、GLMText2Video 补齐中英文 API 文档注册，修复 doc_check 无法生成构造函数文档。
- GLM supplier HTTP/下载层移除 catch-all、重复日志与 RuntimeError 包装，使用 raise_for_status 并直接向上抛出原始请求异常；不在 supplier 内重试或恢复。新增异常类型/对象保持一致、只发送一次请求的回归测试。
- 视频生成拆为输入图片转换、模型输入约束、尺寸映射和轮询方法，保留协议行为，满足现有 C901 复杂度阈值 12，不增加忽略规则。
- LazyLLM 合入上游 98ad0da5（微信滑动图片组功能），主仓库将引用包含双方修改的后代提交，解决与 upstream/main 的子模块指针冲突。
- 合并后的全量 doc_check 暴露额外 4 处文档注册缺口（ImageGroup.validate_images、MilvusStore.rebuild、LocalFileSpanExporter、LocalConsumeBackend），已补中英文文档，不改业务实现或检查规则。
- 最终验证：flake8 使用仓库 .flake8（max-complexity=12）通过；英文/中文完整 tests/doc_check 各 1476 passed、19 xpassed；GLM supplier 与图片调用回归 46 passed。
- LazyMind 已合入 upstream/main 87a859b5d，子模块引用包含 98ad0da5 及 GLM 修复/文档的后代提交。原有本地 demo 改动已恢复并保留备份 stash，本轮未重启服务。
