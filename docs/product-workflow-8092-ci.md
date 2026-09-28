# 8092 产品 Workflow 本地 CI 记录

本记录对应 `TangyRyan/LazyRAG:product-workflow-two-router-shared-artifacts`，目标为
`CarlosShaoting/LazyRAG:workflow_dev`，对应 PR：
<https://github.com/CarlosShaoting/LazyRAG/pull/6>。

## 基线与变更范围

- 目标基线：`CarlosShaoting/LazyRAG workflow_dev`，提交 `8d1ba2793500de43af6b70d1957367434d5096c8`。
- 当前提交来自 8092 产品 Workflow 分支，包含两层路由、共享产物视图、阶段回退/续接以及产品工作区衔接实现。
- 相对目标基线的当前 PR 规模：104 个文件，新增 22,213 行，删除 1,896 行，共 24,109 行变更，满足 9k+ 范围要求。
- B03、B04、B05 只在 `product_solution_delivery` 产品 Workflow 的条件分支中生效；公共承载点保持上游默认路径，通用主链路不改变。

## 本地 CI 通过记录

执行环境：macOS ARM64，Node/pnpm、Go 和 Python 3 均使用本机已安装版本。迁移检查按 PR 的真实目标分支执行：
`GITHUB_BASE_REF=workflow_dev make lint`。

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| Python/Go/边界/命名/迁移 lint | `GITHUB_BASE_REF=workflow_dev make lint` | PASS |
| 文档检查 | `python3 -m pytest tests/doc_check -q` | PASS（2 passed） |
| 前端 ESLint | `cd frontend && pnpm lint` | PASS |
| 前端类型检查 | `cd frontend && pnpm typecheck` | PASS |
| WorkflowPanel 前端回归 | `cd frontend && pnpm test:workflow-panel` | PASS（21 files，179 tests） |
| Go Workflow、Doc、Skill v2 | `cd backend/core && go test ./workflow/... ./doc ./skillv2/...` | PASS |

Go 测试仅出现 macOS SDK 的系统 API deprecated warning，没有失败或新增编译错误。

## 基线误报处理

直接执行不带基线参数的 `make lint` 会使用本地 `origin/main`。当前仓库的 `origin` 是
`LazyAGI/LazyMind`，而 PR 的目标仓库和目标分支是 `CarlosShaoting/LazyRAG:workflow_dev`，
因此迁移不可变检查会把两个仓库之间的历史差异误报为删除。将 `origin/workflow_dev` 指向目标
分支后，以 `GITHUB_BASE_REF=workflow_dev make lint` 重跑，迁移检查通过；这不是产品代码缺陷。

## CI 修复内容

- 修复 Python lint 的长行、悬挂缩进、缺少空行和闭包变量绑定问题，均不改变运行时协议。
- 前端保留上游 WorkflowPanel 语义：外部执行预览只读，原生面板继续使用实际编辑器状态；测试文案改为读取当前 i18n，避免与最新文案冲突。
- 没有把 Python 大回归套件加入本 PR；该套件按需求保持为本地验证项，不影响上述本地 CI 结果。
