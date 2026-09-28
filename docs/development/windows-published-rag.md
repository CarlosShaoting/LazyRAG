# Windows 固定复用已发布的 ModelScope RAG 组件

日期：2026-09-23。用户要求：测试并复用现有云端 Windows ZIP，不再动态打包；安装界面仅告知下载来源，不提供修改链接功能。本轮不修改 Mac 的分包方式、Skill、LazyLLM 源码或子模块 gitlink。

## 2026-09-28：本次 rebase 后的 Windows 打包与测试交接

本节为当前状态；下文 2026-09-23 的构建记录及“本轮”范围属于历史记录。

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
