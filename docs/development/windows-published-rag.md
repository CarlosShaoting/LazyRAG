# Windows RAG 手动发布与固定组件历史记录

最近更新：2026-09-28。**当前策略为 Windows 在 Actions 生成组件 ZIP、维护者手动上传；Mac ARM64 保持已发布固定版本。** 本节之后保留此前固定包与本地候选包的历史记录。Mac Intel 的独立接入范围仍见其交接文档，本次不改 Mac 脚本或清单。

## 2026-09-28：Windows 手动发布及 Milvus 持久化修复（当前执行流程）

用户要求只修改代码并 push，由用户在 Actions 打包、上传。本轮没有在本机生成新 ZIP/installer，也没有触发 Actions 或上传云资源。前一轮本地 `67973fda1e3a7518.zip` 尚未包含本次补丁，**不要将它当成修复版上传**。

### 修改范围与原因

- Windows 构建继续使用 `windows-amd64-requirements.lock` 的 175 项固定版本。每次构建固定生成当次 RAG ZIP 和匹配 catalog，不再读取仓库的旧 Windows 固定 catalog，也不再下载 `e262…` 或 `67973…` 作为构建输入。旧 `windows-amd64.json` 保留作历史版本记录；实际发布依据为 Actions 产出的清单。
- `patch-windows-milvus.py` 仅供原生 Windows 构建调用，对 `milvus-lite==3.0` 的 `storage/manifest.py` 应用 `os.rename(tmp_path, target_path)` → `os.replace(tmp_path, target_path)`。检查原源码 SHA 和 wheel RECORD；未知版本、未知源码、RECORD 不匹配立即失败；同步更新 RECORD 的哈希与大小，重复执行可验证复用，写 RECORD 失败恢复源码。保留临时文件、刷盘和备份逻辑，不修改用户数据库，不全局替换 `os.rename`。
- 补丁在裁剪和分包前执行，所以更新后的源码及 RECORD 会进入 ZIP SHA、revision 和 fingerprint。旧 staging 的 resume 不能绕过补丁验证；当前 Windows 不再提供关闭后置的构建选项。
- Windows 后置组件使用 `slim-providers-v1`：gRPC 随 RAG 后置，移除桌面不使用的 OpenSearch。火山 SDK 已从依赖锁移除，本轮不重复计算其体积收益。
- Windows 封装 installer 前，必须通过当次本地 ZIP 的 SHA/manifest、安全解压、补丁源码/RECORD、基础导入、RAG overlay 导入和 Milvus 写入/flush/重启/查询/删除。真实验证失败即停止，不将失败结果标绿。
- Actions 的 `windows-python-components` 附件包含 ZIP、清单、SHA256SUMS、完整构建锁、补丁报告及 `verification.json`。构建摘要打印精确文件名、SHA、主备地址及手动上传说明。失败任务也可能上传诊断附件，不能将其当成验收通过产物。
- Mac ARM64 固定 catalog、依赖锁、分包调用和上传流程不变；共用验证脚本只有显式传 `--require-windows-milvus-patch` 才检查本补丁。未修改 Skill 或 LazyLLM 源码/子模块 gitlink。

### GitHub Actions 操作

1. 选择 **Windows Desktop Installer**，分支 `cst/installer_opt`；构建引用留空，使用最新提交。
2. 无需勾选开关：仅保留可选 `git_ref`。Windows 固定开启案例后置、RAG 单独打包、Python 裁剪，关闭实验性依赖共享。
3. 等待构建和验证成功；下载该次运行的 installer 和 **windows-python-components** 附件。
4. 解开 Actions 附件外层 ZIP，找到里面的 **`lazymind-python-rag-windows-amd64-cp311-<revision>.zip`**。只上传这个原始内层 ZIP，不改名、不解压重压，也不上传名为 `windows-python-components.zip` 的外层附件。
5. 上传到清单中的公开 HTTPS 地址：默认主源为 ModelScope 数据集 `CarlosShaoting/lazymind-cst` 的 `master` 根目录，回退源为 HF 数据集 `LazyAGI/LazyMind` 的 `main` 根目录。ModelScope 不可用时先上传 HF；主备应使用完全相同的文件。若设置仓库变量 `LAZYMIND_PYTHON_COMPONENT_BASE_URL`，以当次摘要/清单给出的主源为准。
6. 核对云端下载文件大小和 SHA 与当次 `python-components.json` / `SHA256SUMS` 一致，再分发配套 installer。云端文件未上传时，安装后的 RAG 下载会失败；构建本身使用本地 ZIP 验证，不依赖提前上传。
7. **不需要上传后再改代码或重打一遍 installer**：同次 installer 已内置该 ZIP 的准确 URL、revision、大小、SHA。若另跑一次 Actions，应重新核对并上传那次配套 ZIP，不能假定不同运行产物身份相同。历史 ZIP 保留，供旧 installer 使用。

每次 Windows 构建默认生成组件，`LAZYMIND_DESKTOP_REBUILD_PYTHON_COMPONENTS` 不再控制 Windows。Mac 不因为 Windows 这次修改而重传资源。字体、精选素材、Workflow 和 Skill 沿用原有清单。

### Actions 后续修复：精选案例清单 UTF-8

用户回传的 Actions 日志确认 RAG 的 SHA/manifest、Windows Milvus 补丁及写入/flush/重启/查询/删除均已通过。随后 `stage-featured-assets.py` 在读取中文 `catalog.json` 时使用 runner 默认的 cp1252，报 `UnicodeDecodeError`。现将编译清单及已发布资源清单两处读取均显式指定 UTF-8；输出原本已使用 UTF-8 字节写入。

本次不改变精选资源的下载方式：封面与清单内置，完整素材按已发布清单后台或按需下载，ModelScope 主源失败后回退 HF。无需重新上传精选 ZIP。新增完整 staging 回归覆盖 cp1252 默认编码下的中文标题、中文清单字段、封面转换与原下载身份保留；Linux 和原生 Windows（关闭 Python UTF-8 模式）验证通过。本次未打包 installer，推送后重新运行 Actions 即可。

### Actions 后续修复：精选素材跨平台检出字节一致

UTF-8 修复后，Windows 又在 `academic_research_pipeline/1.1.0` 的发布清单比对处失败。仓库中的 HTML 原文件为 625,174 字节，SHA `58e05a4bbc2815c5012185e898dfd7e080ac9ceb543916e8c64c569c9d910b0c`，与已发布清单一致。使用 `core.autocrlf=true` 模拟 Windows Git 检出后，166 个 LF 变为 CRLF，文件增至 625,340 字节、SHA 变为 `1d9333abe13972197ff98239e3940a3c43f62bc5fee2efdee4474863d7e9faee`，触发清单拒绝。

`.gitattributes` 现在对 `skills/featured/**/assets/**` 指定 `-text`，保留 Git 中的原始素材字节，避免自动换行转换影响内容哈希。没有修改素材、重新生成云端 ZIP 或放宽哈希校验，HF 下载/缓存流程不变。保持发布素材原始字节也适用于嵌套 SVG、HTML 和图片。

验证：新增真实 Git 检出回归（`core.autocrlf=true`），与中文 cp1252 staging 回归一起，在 Linux 和原生 Windows 均通过。另将全部 314 个精选源文件按 Windows 换行配置检出，用原生 Windows Go 的 `showcase.CompileCatalog` 和真实锁文件绑定编译 46 个案例，再用原生 Python（`-X utf8=0`）执行 staging。全部 46 个远端包及封面身份与现有 `desktop/featured-assets.json` 完全一致：素材原始 172,009,247 字节，内置封面 1,304,579 字节，远端 ZIP 合计 77,565,150 字节。

无需重传精选案例 ZIP。请在修复分支新建一次 **Run workflow**，构建引用留空，采用最新提交；旧 Actions 的重新运行仍可能使用旧提交。本轮只验证素材编译/分离，没有本地打包完整 installer。

### Windows 构建选项收敛与日志清理

Actions 的手动入口及可复用入口移除 `defer_history`、`defer_python`、`share_python`、`prune_python` 四个输入。Windows 脚本在读取本地环境配置后固定为案例后置、RAG 分包、Python 裁剪开启，跨环境依赖共享关闭，防止旧配置启用实验模式。Python 解释器去重仍保留；关闭的是不同虚拟环境之间的依赖共享。

删除 Windows 的完整内置 RAG 分支、依赖共享审计调用、Python/最终 runtime 体积对比、包占用排名、runner 磁盘占用输出和 `windows-python-size-report` 附件。精选素材 staging 只打印完成信息，不再打印前后占用。共用脚本保持显式审计入口，Mac ARM64 与 Intel 的现有构建配置和日志不变。

保留最终 installer 的文件名、大小、SHA、签名及下载链接；保留 `windows-python-components` 的 ZIP/清单/功能验证报告、字体附件、Milvus 补丁报告和安装诊断。Python 裁剪后的豆包 HTTP mock、RAG SHA/manifest/导入、Milvus 持久化及 Windows 安装卸载门禁继续执行，失败仍阻止构建通过。未修改 Skill 内容、LazyLLM 源码或子模块 gitlink。

验证结果：Desktop 构建与裁剪入口测试 47 项通过；原生 Windows 的 Python 裁剪与精选素材回归共 12 项通过（含 junction、cp1252 和 Git 换行场景）。PowerShell 语法解析及执行初始化函数验证通过，确认旧环境变量被稳定配置覆盖；workflow YAML/复用调用参数检查、裁剪 CLI 有/无报告两种模式、精选素材静默输出路径均通过。本次未生成 installer，完整安装结果以新一次 Actions 为准。

验收时新建一次 Run workflow：确认页面只有可选构建引用，摘要没有占用对比表，功能门禁全部通过；按摘要上传当次 RAG 内层 ZIP。安装后检查案例 warmup、普通聊天、组件下载以及知识库入库和重启检索。此次配置清理不要求重传字体或精选素材。

### Pandoc 与 Electron Windows 封装修复、原生完整构建

Actions 在 `stage-pandoc.mjs` 调用 Windows PowerShell 时，使用 `-Command "param(...) ..."` 并在末尾追加路径；命令字符串不会按预期将这些参数绑定到 `$archive` 和 `$destination`，因此 `Expand-Archive` 得到空路径而失败。

修复将 ZIP 与目标路径通过子进程专用环境变量传入，PowerShell 命令只含固定代码并设置 `$ErrorActionPreference = 'Stop'`。在新建临时目录内使用 .NET `ZipFile.ExtractToDirectory`，避免路径中的空格、中文、引号、`$`、`&` 和方括号被重新解析或当作通配符。下载源、Pandoc 3.11 固定 SHA、解压后版本检查及 Mac 解压逻辑不变。

原生完整构建另复现 Pandoc 临时目录删除时的 `ENOTEMPTY`，现仅对该临时目录清理增加最多 5 次、间隔递增的重试；持续失败仍报错，不忽略清理错误。

封装又复现 electron-builder 24.13.3 的原生依赖重建器将 `pnpm.cjs` 当成 EXE 执行，报 `%1 is not a valid Win32 application`。npm 安装的 pnpm 与 Corepack pnpm 均可复现。Windows 构建入口改为 `pnpm exec electron-builder --config electron-builder.config.cjs --win <nsis|zip> --x64 --publish never`，避免 `pnpm run` 注入的 `npm_execpath`；保留原生依赖重建、打包重试及原有打包参数。未修改 Mac 构建入口或跳过 `uiohook-napi`。

新增 Windows 原生回归：真实 ZIP 在上述特殊字符目录下解压；损坏 ZIP 必须抛错且不能覆盖已有可执行文件。官方 Windows Pandoc 包另行完成实际下载、SHA 校验、解压和 Markdown → DOCX 转换。此次无需重新上传 RAG、字体或案例来修复 Pandoc；发布 installer 仍应使用同次构建生成的 RAG ZIP 和清单。

#### Actions 后续修复：Pandoc 可执行文件替换时被占用

用户回传日志确认 RAG、Milvus 与精选素材均通过，失败发生在 `pandoc.exe.<pid>.tmp` 改名为 `pandoc.exe` 时，错误为 Windows `EBUSY`。前次重试仅覆盖解压目录删除，没有覆盖刚执行 `--version` 后的文件替换；本地一次成功未覆盖这种时序。

现在直接用 rename 替换目标，删除原来的“先删旧 EXE”步骤；仅在 Windows 遇到 `EBUSY`、`EPERM`、`EACCES` 时最多重试 10 次，等待从 250 ms 递增到最多 1 秒，累计等待 8.5 秒。持续占用仍失败，其他错误立即失败，保留已有 EXE；不放宽下载 SHA 或版本检查。非 Windows 不采用该重试，正常替换同样使用 rename 保留失败时的旧文件。

原生 Windows Node 20 测试 8 项通过：包含真实 PowerShell/.NET 文件句柄禁止删除的四种场景（候选文件/已安装文件，短暂占用/持续占用）。短暂锁实际触发 `EBUSY` 和 `EPERM` 后替换成功；持续锁超过上限后必须报错且旧文件字节不变。原有真实 ZIP、中文及特殊路径、损坏 ZIP 检查继续通过。用户无需因本次脚本修复重传字体、案例等资源；RAG 仍按各次 installer 的配套清单上传。

本次修复后的本地 `resume-installer` 已重新通过 RAG、Milvus、精选资源及官方 Pandoc staging。用户随后要求先 push、由 Actions 打包，因此本轮未以新的完整 installer 作为验收结论；下方 351.16 MiB 产物属于前一轮验证。

#### 本机 Windows 原生产物与验证结果

在独立 Windows 工作目录执行完整 `installer` 构建，修复实际失败点后通过 `resume-installer` 完成封装；最终退出码 0。测试源码为 `d3ebb2a4` 基线加本节修复，所以本地产物后缀仍是基线 SHA。没有覆盖本机原有 LazyMind 安装或使用用户知识库。

- 工作目录：`C:\Users\cuishaoting\AppData\Local\LazyMindBuildChecks\installer-20260928`。
- installer：`desktop/dist/LazyMind-windows-x64-installer-0.3.0-alpha.0-20260928-134551-d3ebb2a4.exe`，368,221,478 字节（351.16 MiB）。SHA-256：`4d6f4c06bdc8965f4528b7a28388620428da0db79eecd5e97a62a140acce3f7f`。
- 配套 RAG：`desktop/dist/python-components/windows-amd64/lazymind-python-rag-windows-amd64-cp311-1ce4f110664273ea.zip`；实际 ZIP 的平台、基础导入、SHA、manifest、Milvus 补丁 RECORD、overlay 导入、插入/flush/重启/检索/删除全部通过，`verification.json` 为通过。
- Node 20 原生 Desktop 测试：268 项通过、27 项平台条件跳过、0 失败；Pandoc 原生回归 4 项通过。后续打包入口修改后，相关 47 项构建/裁剪测试与 PowerShell 语法检查通过，实际原生依赖重建与 NSIS 封装成功。
- 官方 Pandoc 包 SHA 与版本校验通过，实际 Markdown → DOCX 成功；打包后的 Electron 能加载 `uiohook-napi`，未启动输入监听。
- 用独立 `LOCALAPPDATA=...\LMBuildSmoke20260928` 启动 `win-unpacked/LazyMind.exe`：首次 Python 解压完成、所有服务 ready、Core 健康接口与实际 Markdown → LaTeX 转换通过。
- **退出边界**：正常关停曾报告两个子进程清理超时；现有 bounded cleanup 随后通过，最终全部服务 `stopped` 且网关端口关闭，smoke 退出码 0。不能表述为退出过程完全无警告。本次未修改运行时进程清理逻辑，也未执行会覆盖现有安装的 NSIS 安装、升级或卸载测试。
- 原始构建、恢复、Node 20 测试和应用 smoke 日志，以及源码 SHA/产物校验记录，保存在工作目录的 `verification-logs/`。首次 uv 0.12 安装遇到临时 PE 资源写入失败，第三次重试成功；随后工具对齐为 Node 20.19.5、pnpm 10.0.0、PowerShell 7.5.4、Go 1.26.5、uv 0.11.31。未屏蔽依赖校验或绕过原生重建。

Actions 新建构建将使用新提交编号，产物文件名、ZIP revision 和 SHA 应以该次输出为准。若使用上面的本地 installer，应上传它自己的配套 RAG ZIP；不要将本地与 Actions 的不同产物混配。字体、Workflow、精选素材无需因这些封装修复重复上传。

### 本轮验证与边界

- 在原生 Windows CPython 3.11.15 上，将现有 ZIP 解压到独立临时目录，应用同一补丁并验证 RECORD；RAG 导入，以及实际 Milvus 插入、检索、显式 flush、停止/重启、重启后检索、删除均通过。没有创建新 ZIP，也没有使用或修改用户知识库。
- Windows 原生补丁单元测试 7 项通过；组件分组/固定清单 13 项、profile 3 项、Desktop 构建测试 44 项通过；PowerShell 语法与 workflow YAML 检查通过。
- 此结果验证了补丁及持久化路径，不等于新 installer 安装、升级、UI 与全部业务验收。完整产物仍由本次 Actions 构建及门禁验证；用户安装后继续测试知识库 PDF/Office 入库、重启后检索，以及普通聊天、登录、附件和模型功能。

## 2026-09-28：Windows slim 组件原生重打（修复前历史候选）

本次从 `origin/cst/installer_opt` 的 `f8d5bd922` 强制同步后，按下方交接完成 Windows 原生依赖分包。LazyLLM 工作树检出主仓已记录的官方 `ab67c189`；没有更改或提交子模块 gitlink。下文“Windows 无 slim profile、仍复用 e262”的交接状态被本节替代。

- 新文件：`lazymind-python-rag-windows-amd64-cp311-67973fda1e3a7518.zip`。
- ZIP 大小：74,597,139 字节（71.14 MiB）；展开 284,028,099 字节（270.87 MiB）。
- SHA-256：`50c92abc8219dacbae17f3ae49b7cb13b477cf20c15c2e9be1f5537b353c7f93`。
- 平台：原生 Windows amd64 / CPython 3.11.15；不能用于 Mac 或 Linux。
- profile：`slim-providers-v1`。RAG 中新增 `grpcio==1.84.0`，移除基础环境中的 `opensearch-py`、`opensearch-protobufs`；火山 SDK 已由此前提交从安装输入移除，本次不重复计算其收益。
- 完整安装锁为 175 项，分包后 RAG 为 29 项。OpenSearch 留在完整构建锁中供现有 algorithm requirements 联合解析，随后由 desktop profile 移除；Cloud requirements 不变。
- ZIP 比旧版约增大 5.01 MiB，因为把 gRPC 从主包移入后置组件。新 installer 体积尚未实测，不能把展开体积直接当成下载节省。

### 本地交付与上传顺序

本次完整输出位于 `desktop/dist/python-components/windows-amd64-20260928/`。其中原始 RAG ZIP 是需要上传的文件；`python-components.json`、`algorithm-requirements.lock`、`SHA256SUMS`、裁剪和验证报告用于留档，不要把整个目录重新压成一个 ZIP 上传。

1. 将新 ZIP 原样上传到 Hugging Face 数据集 `LazyAGI/LazyMind` 的 `main` 分支根目录；ModelScope 可用时，将**同一文件**同步到 `CarlosShaoting/lazymind-cst` 的 `master` 分支根目录。文件名和内容均不能改。
2. 清单使用 ModelScope 主源及 HF 回退源；上传至少一个配置来源并核对下载文件的大小/SHA 后，再进行普通 installer 构建。此次仅生成本地产物，未上传，也未确认新云端 URL 可下载。
3. 原 `e262…zip` 保留，旧 installer 仍会请求它。Mac 两种架构沿用各自资源，本次不生成或替换 Mac 包；精选素材、字体、Workflow 和 Skill 无需因本次 RAG 更新重复上传。
4. 提交配套的 Windows catalog/lock 后，GitHub Actions 选择同一分支，保持 `defer_python=true`、`prune_python=true`、`share_python=false`。`LAZYMIND_DESKTOP_REBUILD_PYTHON_COMPONENTS` 保持未设置或 `false`，正常构建仍固定下载新发布版本；不要复用旧 staging。

主源：`https://modelscope.cn/datasets/CarlosShaoting/lazymind-cst/resolve/master/lazymind-python-rag-windows-amd64-cp311-67973fda1e3a7518.zip`。
回退源：`https://huggingface.co/datasets/LazyAGI/LazyMind/resolve/main/lazymind-python-rag-windows-amd64-cp311-67973fda1e3a7518.zip`。

### 验证边界

原生独立构建环境已完成 175 项依赖安装与 `pip check`，豆包图片/视频 HTTP mock 检查通过（不调用付费 API）。实际检查结果：

- 分包、固定发布清单和 profile 的 16 项 Python 单元测试通过。
- 原生验证前 5 阶段通过：平台/ABI、未安装 RAG 的基础导入、ZIP SHA、解压/manifest、官方 LazyLLM 源码配合 RAG overlay 导入；ZIP 2,998 个条目的 CRC 和依赖边界另行检查通过。
- 第 6 阶段 Milvus 在 flush 时复现已有 `WinError 183`（替换已存在的 `manifest.json` 失败）；报告保留 `passed=false`，未绕过或改写结果，未修改 Milvus wheel。重启持久化验收因此仍未通过。
- 将同一环境恢复为完整 175 项依赖后，实际运行 `stage-published-python-components.py`，使用本次 ZIP 作为已校验缓存：版本集合/分组边界及基础/overlay 导入再次通过，输出清单与仓库新清单一致，未生成第二个 ZIP。这验证固定复用流程，不代表云端已上传或下载验证通过。
- 输出包含 `verification.json`（完整验证，含失败）、`fixed-reuse-verification.json`（固定复用通过）、`BUILD-INFO.json`、`SHA256SUMS` 和原生日志。

此次只重打依赖组件，没有生成新 EXE，没有完成应用 UI 或所有知识库业务验收。

## 2026-09-28：本次 rebase 后的 Windows 打包与测试交接（交接时状态）

本节保留依赖重打前的交接状态；当前产物、清单和验证结果以上方“当前执行流程”为准。下文 2026-09-23 的构建记录及“本轮”范围亦属于历史记录。

LazyMind 已 rebase 到 upstream/main `477204829`。LazyLLM PR #1340 已合入官方仓库，子模块使用官方 `ab67c1893872fdc2895fc412d226e61a0524c985`，不再依赖个人 `cst/install_opt` 分支。主仓库仍需提交这个 gitlink；仅将 `.gitmodules` 的 branch 改成 main 不会更新 CI 实际检出的版本。

### 哪些需要重打、哪些可以复用

| 内容 | Windows 本轮处理 |
| --- | --- |
| Windows x64 安装包 | 必须从当前分支干净重建，包含新版 Core、前端、Electron、运行时管理器及官方 LazyLLM 源码；不要使用旧 staging 的 resume 封装。只更新云端资源不会更新旧安装包的代码和清单。 |
| Windows RAG ZIP | 当前仍固定 `e262c0d2f05fe09d`，锁文件和清单未迁移，可复用原发布包，无需为本次 rebase 重打。构建仍需通过基础环境与 overlay 的真实导入校验。 |
| gRPC / OpenSearch / 火山 SDK 精简 | Windows catalog 尚无 `desktopProfile: slim-providers-v1`，不能认为已经获得 Mac ARM64 的完整精简效果。Windows 如需同等优化，必须另做原生依赖包升级，见下节。 |
| 精选素材、PDF 字体及许可证 | 复用已发布的 HF `featured-assets/` 下 46 个 ZIP、字体和许可证；跨平台资源无需重复打包上传，仍按安装包清单验证大小及 SHA-256。 |
| 内置 Skill | 安装包携带锁定目录，使用时下载；无需重新把 Skill ZIP 填回 installer。 |
| 飞书 CLI、凭证辅助程序 | 继续随 Windows 安装包构建、分发，本 PR 不改为后置下载。 |

当前 Windows RAG catalog 只有 ModelScope URL，**尚未配置 HF 镜像**。共用下载器支持回退不代表该 Windows ZIP 已在 HF 可用。如需测试 Windows RAG 的 HF 回退，先将同一 ZIP 上传 HF、校验 SHA 与大小，再补清单镜像地址并重建 installer；不要用 Mac ZIP 替代。

### Windows 后续精简依赖包时必须一起更新

1. 在原生 Windows x64 / CPython 3.11.15 环境处理依赖闭包，将 Milvus 所需的 gRPC 纳入 RAG 组件，移除 Desktop 不使用的 OpenSearch 与火山 SDK；验证未安装 RAG 时基础业务可启动。
2. 重新生成 Windows 专用 RAG ZIP、manifest、revision/fingerprint，并同步 `desktop/python-components/windows-amd64.json` 和配套 `windows-amd64-requirements.lock`。只有分组与导入验证都通过后才启用 slim profile；不能只修改 profile 或复制 Mac 的清单。
3. 使用带新 revision 的文件名发布到 HF（ModelScope 恢复后同步），更新清单的 URL、大小、SHA-256 和解压大小。保留旧文件供旧安装包使用。
4. 再从更新后的主仓库提交重建 Windows installer。原生二进制不能跨 macOS/Windows 或不同架构混用。

### 构建及验收

- GitHub Actions 选择 **Windows Desktop Installer**，分支 `cst/installer_opt`，`git_ref` 留空或指定本次提交；`defer_history=true`、`defer_python=true`、`prune_python=true`、`share_python=false`。保持递归检出子模块，并核对 LazyLLM SHA 为上面的官方提交。
- 检查构建摘要中的 Windows RAG 文件名、大小、SHA 与当前清单一致；`windows-python-components` 是固定组件的清单附件，不意味着需要上传一个新 ZIP。
- 用新的测试用户目录安装，覆盖中文及带空格路径；先验证登录、普通聊天、豆包图片/视频、附件、飞书和 Skill 按需安装，再安装 RAG。
- 验证 Chat 样例优先准备、首页 Chat/Work 素材展示、其余精选后台补齐，及字体下载后的中文 PDF 导出；覆盖已配置镜像资源的主源失败回退和离线缓存复用。
- RAG 安装完成后显式重启，检查无重复运行时进程、辅助进程恢复、PDF/Office 入库、检索、落盘、退出再启动后的检索和删除。原发布包的 Milvus Windows 持久化问题仍按下文单独跟进，不视为本次已修复。
- 记录新 Windows installer 的实际下载体积和 Python 展开体积；Mac 的 484 MB 不能作为 Windows 实测值。

本次仅更新代码、开发文档及本机定向验证，未触发 Windows 安装包构建，也未宣称 Windows 真机验收通过。

## 修改原因和范围

原 Windows CI 每次解析依赖、生成组件 revision，并把对应 ZIP 的 SHA 和地址写进 installer。用户云端只有旧组件时，新 installer 即使改 URL 也因 hash/manifest 不符被拒绝。因此调整构建流程，以已发布组件为固定依赖版本基线，不放宽安装时的校验。

- `desktop/python-components/windows-amd64.json`：固定云端组件清单，原 manifest/fingerprint/ZIP SHA 保持不变。
- `desktop/python-components/windows-amd64-requirements.lock`：与旧组件配套的 Windows algorithm 全部 176 项 distribution 版本，包括共用基础依赖。由已有配套环境及发布 ZIP 的 metadata 导出；构建时在 Windows venv 安装并验证，当前本地验证进度见下文。auth-service/channel-gateway 的独立 requirements 不改；不同版本仍隔离。
- `build-windows-x64.ps1`：后置模式从锁文件和现有业务 requirements 一起安装，冲突立即失败；不再运行 `lazyllm install rag` 动态选择依赖，也不运行 `build-python-components.py` 生成 ZIP。非后置的完整包对照流程保留。
- `stage-published-python-components.py`：校验 Windows x64、CPython 3.11.15、精确依赖版本/集合和 RAG 分组边界；下载固定 ZIP 并验证大小、SHA、安全解压及原 manifest。在移除 optional 文件后的精简环境实际验证基础导入和云端 overlay 导入，失败恢复被移出的文件，成功才启用原清单。
- `resume` / `resume-installer` 也核对 staging 清单与固定版本；旧 `4a318…` staging 不能直接重新封装，需执行干净构建。
- 下载缓存位于 `desktop/cache/published-python/windows-amd64/`；损坏缓存构建失败，不允许使用未验证内容。清理错误缓存后重新构建。下载与验证目录不会复制进 installer。
- 构建输出 `desktop/dist/python-components/windows-amd64/` 只有固定清单、校验文件和来源说明；Actions 继续提供 `windows-python-components` 附件以供审计，干净构建没有新 ZIP。已有上传文件无需替换。
- 前端组件弹窗显示固定 URL 和文件名，无输入框；API 只接收组件 ID，只用服务端 catalog URL 下载，自定义 URL 请求返回 400。保留取消、失败重试、安装后显式重启；修复弹窗 `confirmLoading` 导致“取消下载”被 UI 库阻止的问题。

原 `baseFingerprint` 是发布包的一部分；本轮用“固定完整依赖版本 + 构建时真实基础/overlay 导入验证”确立与它的配套关系，而不是将任意当前环境伪装为兼容。运行时仍严格检查下载 SHA、大小、平台、ABI、revision、fingerprint。未来升级任何锁定依赖必须显式验证并发布新的配套版本，不自动漂移，也不跳过校验。锁定版本并不等于永远不需要维护依赖。

## 固定云资源

- 文件：`lazymind-python-rag-windows-amd64-cp311-e262c0d2f05fe09d.zip`
- URL：`https://modelscope.cn/datasets/CarlosShaoting/lazymind-cst/resolve/master/lazymind-python-rag-windows-amd64-cp311-e262c0d2f05fe09d.zip`
- 大小：69,342,263 字节（66.13 MiB）。
- SHA-256：`258944a85d5aa29c0eb662ab21888c5c2894fdfb2c503d51f2129efa4e083bed`。

本轮实际从 ModelScope 下载并核对大小/SHA 一致，不只是验证本地旧文件。用户无需上传新 RAG ZIP。旧的 417 MiB installer 仍携带 `4a318…` 清单，必须重新构建安装；不会通过改云端文件名或覆盖旧资源使旧 installer 自动变兼容。

`LAZYMIND_PYTHON_COMPONENT_BASE_URL` 不再控制 Windows 固定组件来源；要迁移托管地址需明确修改版本清单并重建。Mac 原有构建变量与独立原生组件继续有效。

## 验证与用户验收

本轮已完成：

- 实际从 ModelScope 下载上述 ZIP，文件大小和 SHA-256 与固定清单一致。
- 固定 176 项依赖与当前 algorithm requirements 联合解析成功。
- Python 固定组件测试 5 项通过，覆盖版本变化拒绝、清单约束及失败恢复；前端组件测试 5 项通过，覆盖只读来源、取消、重试等行为。
- Go 组件相关测试通过；原生 Windows Go 测试 7 项通过，真实完整组件集成测试因未提供完整环境跳过。
- Desktop Node 测试 143 项通过、10 项跳过；PowerShell 语法及 resume 清单匹配/不匹配检查通过。

尚未完成：完整的新 Windows installer 构建、原生精简环境与云端 overlay 联合验证及应用业务验收。本机 uv 安装遇到 Windows PE launcher 资源写入错误；pip 替代安装亦未完成，因此本轮不宣称原生端到端验证通过。GitHub 构建会执行实际基础/overlay 导入检查，失败时停止打包。导入检查通过也不能替代下列业务测试。

### GitHub 构建步骤

1. 选择 `cst/installer_opt` 分支，构建引用留空，使用该分支最新提交。
2. 勾选 `Use the published RAG component from ModelScope (fixed version)`；首次使用本次修改执行完整构建，不复用旧 staging。
3. 检查构建摘要的 RAG 文件名为 `e262c0d2f05fe09d.zip` 对应完整名称，SHA 与上文一致，再下载安装包。
4. 现有 ModelScope Windows RAG ZIP 无需重新上传。`windows-python-components` 附件用于核对固定清单，不再产生需要上传的新 RAG ZIP。其他可选资源是否需上传仍按各自清单判断。


用户安装新构建后需确认：

1. “安装组件”弹窗显示 ModelScope `e262…zip`，没有链接输入框；安装时不再请求 `4a318…`。
2. 从干净的用户 runtime 安装 RAG，下载完成后显式重启；错误/断网有提示，取消后可重试；不会隐式重启正在运行的任务。
3. 普通聊天、登录、文件附件、Ark、飞书及常用 Skill 保持可用；安装 RAG 前后分别验证。
4. 新知识库 PDF/Office 入库与检索、显式落盘、退出重启后的检索和删除集合必须实际测试；保存原有数据，使用测试知识库。
5. 旧组件升级行为取决于新旧 catalog：匹配固定版本的完整安装可复用，其他 revision 不冒充兼容组件，不删除旧数据。

已知发布包含 `milvus-lite==3.0` 的 Windows `WinError 183` 持久化缺陷，原始未经裁剪 wheel 亦可复现；本轮不修改用户已上传 ZIP、第三方库内容或 checksum。该问题影响 flush/重启检索验收，需要单独修复并按受控依赖升级流程发布；不能因本轮固定版本而宣称解决。

## Mac 后续接入

本次只切换 Windows 构建的 RAG 来源；共用前后端的只读下载来源界面也会用于 Mac。Mac 目前仍沿用原有分包流程，尚未切换为固定发布包。

后续需分别为 macOS Apple Silicon（arm64）和 Intel（amd64）确认已上传 ZIP、URL、SHA、manifest 及配套版本锁；各自原生构建验证后再启用固定来源。不能复用 Windows ZIP，也不能让两个 Mac 架构共用含原生二进制的组件。接入时保留安装校验、失败恢复和构建前导入检查，并分别记录两个架构的验收结果。

2026-09-23 Mac 后续接入：Apple Silicon 已按本方案接入固定 `53a1c2e770966b71` 组件，配套 173 项依赖锁及原生验证见 [Mac 开发记录](macos-published-rag.md)。上文“Mac 尚未切换”描述的是 Windows 提交时的范围；Intel 仍待独立发布包接入。
