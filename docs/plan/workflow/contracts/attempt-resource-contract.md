# Attempt Context and Resource Contract v1

本文固定 Executor 获得的 Attempt Context，以及 Host Attachment、Workflow Input Resource 和输出 Artifact 之间的边界。

## 1. 资源概念

| 概念 | 来源 | 所属范围 | 关键特征 |
|---|---|---|---|
| Host Attachment | LazyMind 对话上传、Codex 对话附件或 workspace 文件 | Host | Host 私有引用，不可直接跨 Host 使用 |
| Input Resource | Host Attachment 导入后的中立资源 | 用户/Workflow 基础设施 | 内容 hash、权限和稳定 `resource_id` |
| Input Binding | Input Resource 与 Workflow material/slot 的绑定 | Workflow Session | 固定 revision，参与 lineage |
| Artifact | Attempt 产生的输出 | Workflow Session | producer、slot、revision、selected/stale |

Host 自行提供文件选择、上传和本地读取能力；共享 Runtime 统一 Input Resource、Binding 和 Artifact 语义。

## 2. Host Attachment 导入规则

1. Host 本地绝对路径、临时附件 URL 和平台访问 token 不得进入 Workflow Session 或 Attempt Context。
2. Host Adapter 必须先把附件导入共享 Resource Store，或注册一个所有目标 Executor 均可通过受控 capability 读取的不可变资源。
3. 导入结果至少包含：

```json
{
  "resource_id": "res_123",
  "name": "requirements.pdf",
  "mime_type": "application/pdf",
  "size": 123456,
  "content_hash": "sha256:...",
  "revision": 1
}
```

4. `prepare_workflow` 只接受 `resource_id` 或已规范化的中立 input reference，不解析 Host 私有附件。
5. `start_workflow` 固定 preparation 中的 resource revision/hash，形成 Session Input Snapshot。

## 3. 第一版工具边界

附件入口不作为 Workflow Agent 公共工具。第一版由 Host Adapter 在调用 `prepare_workflow` 前完成：

```text
Host-specific attachment/file picker
→ Host File Adapter
→ register/import Input Resource
→ prepare_workflow(inputs: resource_id...)
```

如果 Workflow 启动后需要替换输入，再增加版本化的 `replace_workflow_input` command；不得用 `patch_artifact` 修改输入。

底层 Resource Store 可以复用读取和 blob 存储实现，但公共领域 API 继续区分 Input Resource 与 Artifact。

## 4. Attempt Context

`get_attempt_context` 返回固定、可审计且与 Host 无关的上下文：

```json
{
  "contract_version": "workflow.v1",
  "workflow_session_id": "ws_123",
  "workflow_revision": "rev_3",
  "step": {
    "id": "outline",
    "objective": "...",
    "acceptance_criteria": ["..."],
    "required_outputs": ["outline"]
  },
  "attempt": {
    "id": "attempt_456",
    "number": 2,
    "resolved_operation": "retry",
    "lease_generation": 3
  },
  "inputs": [
    {
      "material_id": "requirements",
      "resource_id": "res_123",
      "revision": 1,
      "content_hash": "sha256:...",
      "read_capability": "cap_abc"
    }
  ],
  "prior_outputs": [],
  "instruction": "补充竞品差异",
  "partial_selector": null,
  "capabilities": ["web_search"]
}
```

Attempt Context 不得包含：

- 模型、供应商或 API key；
- LazyLLM sid；
- Host system prompt；
- Host 的完整 Conversation；
- 本地绝对路径；
- 不属于本 Attempt 的用户私有附件；
- 另一个 Host 无法解释的工具配置。

## 5. Input Snapshot 与替换

- Attempt 创建时必须保存实际消费的 input revision binding。
- retry 默认复用上一次固定输入；用户明确替换输入后创建新 binding。
- 替换输入必须增加 Session `state_version`，并按实际 lineage 将相关 succeeded Attempt 和 Artifact 标记 stale。
- Input Resource 自身不因 Workflow rewind 变 stale；失效的是 Binding、Attempt 和依赖输出。

## 6. 读取权限

- Executor 使用短期、最小权限的 `read_capability` 获取资源内容。
- capability 必须绑定 resource、actor/Executor、Attempt 和过期时间。
- Attempt lease 丢失或 Session 权限撤销后 capability 必须失效。
- 跨 Host 执行必须通过共享资源读取接口，不得要求另一个 Host 代理读取其本地文件。

## 7. Artifact 保存

- `save_artifact` 必须携带 Attempt lease、slot、content hash、cardinality/partial selector 和 `command_id`。
- 内容上传与 metadata commit 必须有明确的 finalize 边界；孤立 blob 可以异步回收。
- required Artifact 的有效性由 Runtime 在 `complete_attempt` 时验证。
- Artifact 正文不通过 Workflow SSE 推送；SSE 只推 metadata、短 preview 和 revision 信息。
- Executor SDK 必须要求 SubAgent runner 返回结构化 `ExecutionResult`，由 Supervisor 持久化其中声明的 outputs；不得要求模型记住在结束前调用 lifecycle 工具。
- 如果模型既没有产生结构化 required output，也没有通过受监督的 Artifact callback 保存输出，Supervisor 必须以 `REQUIRED_OUTPUT_MISSING` fail Attempt，不得错误标记 succeeded。
- 流式 Artifact callback、结构化最终输出和 partial output 必须经过同一 idempotent Artifact writer，防止同步工具取消或重试造成重复 revision。

## 8. 验收要求

- LazyMind 附件和 Codex workspace 文件可生成相同结构的 Input Resource fixture。
- 关闭来源 Host 后，已启动 Session 的 Executor仍能读取固定输入。
- Attempt Context snapshot 测试确保不含模型配置、私有 token 和绝对路径。
- 输入替换、retry、rewind、Agent `patch_artifact` 与产品侧 human revision 的 lineage/stale 行为有跨 Host contract tests。
