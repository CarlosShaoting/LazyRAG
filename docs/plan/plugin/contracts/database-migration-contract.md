# Workflow Database Migration Contract v1

本文定义 Plugin → Workflow 重构及多 Host Runtime 所需的数据库演进。目标是在不重命名、不搬迁既有核心数据的前提下补齐新协议，并保证滚动发布期间新旧进程可以共存。

本文所称“前向兼容”至少包含：

1. 旧版本服务面对已执行 expand migration 的数据库仍可正常读写旧链路。
2. 新版本服务能够读取 migration 前产生的旧数据，并为缺失的新字段提供确定性默认映射。
3. 新能力只有在 schema capability 和服务 capability 均满足后才启用。
4. 新版本写入的数据在兼容窗口内不得破坏仍运行的旧 reader/worker。
5. 回滚应用版本不要求回滚 schema；新增表、列和索引对旧版本保持无害。

## 1. 强制迁移策略

所有数据库变化使用：

```text
expand → backfill/shadow → compare → switch → observe → contract later
```

本计划的 15 个 PR 只允许执行 expand、必要 backfill/shadow、switch 和 observe。删除旧表/列、改名、收紧 nullability、改变旧字段类型等 contract 操作不属于本轮，必须在所有旧二进制和旧 worker 退出后另立迁移计划。

### Expand 阶段必须满足

- 只新增表、nullable 列、有安全默认值的列和非阻塞索引。
- 不 rename/drop 旧表、旧列、旧索引。
- 不改变旧字段已有值的含义。
- 新增非空列必须有旧程序可接受的数据库默认值。
- 大表索引使用数据库支持的 online/concurrent 方式；不在长事务中回填。
- migration 必须幂等，并能安全判断已应用状态。

### Rolling deploy 顺序

```text
1. 部署 expand migration
2. 验证 schema capability
3. 部署兼容新旧 schema 的新服务
4. shadow/compare
5. 按 Workflow/用户 canary 启用新写路径
6. default-on
7. 保留旧 reader/adapter 一个明确观测窗口
8. 后续独立 contract migration 才允许删除旧结构
```

应用回滚只关闭 feature flag 并回滚二进制；不得依赖 schema down migration。

## 2. 旧表和旧列保留策略

以下物理表继续作为现有数据的权威存储，不在本轮改名：

```text
plugin_sessions
plugin_session_steps
plugin_slot_revisions
plugin_attempt_input_bindings
plugin_route_decisions
plugin_transition_commands
plugin_run_outbox
plugin_slot_order
plugin_step_intents
plugins
plugin_blobs
plugin_revisions
plugin_revision_entries
plugin_drafts
```

`plugin_id`、`plugin_ref`、`plugin_revision_id`、`plugin_session_id` 等旧列继续保留。Go 使用明确 `gorm:"column:plugin_*"` 映射到 `Workflow*` 领域字段；Python SQL 使用 alias/row mapper。原始旧名不得越过 persistence boundary。

## 3. `plugin_sessions` 的兼容扩展

现有 `conversation_id` 保持原类型和 `NOT NULL`，避免旧 binary scan/insert 失败；由 Codex、schedule 或 API 创建且没有 LazyMind Conversation 的 Session 写入空字符串 `''`，不得写入伪造 Conversation ID。

新增列均使用旧程序无害的默认值：

```text
origin_host          varchar(...) NOT NULL DEFAULT 'lazymind'
origin_ref           varchar(...) NOT NULL DEFAULT ''
controller_host      varchar(...) NOT NULL DEFAULT 'lazymind'
controller_ref       varchar(...) NOT NULL DEFAULT ''
executor_host        varchar(...) NOT NULL DEFAULT 'lazymind'
contract_version     varchar(...) NOT NULL DEFAULT 'workflow.v1'
```

兼容读取规则：

- 旧行 `origin_host` 默认映射为 `lazymind`。
- `origin_ref` 为空且 `conversation_id` 非空时，新 reader 将其映射为该 Conversation。
- 新 Session 如果由 LazyMind 创建，继续同时写 `conversation_id` 和中立 origin/controller 字段。
- 新 Session 如果由 Codex 等 Host 创建，`conversation_id=''`，仅通过 `origin_host/origin_ref` 关联来源任务；不得创建 LazyMind Conversation，旧 UI 不得把它查询为某个对话的活动 Session。
- 在旧版本仍运行时，不向旧 `status` 列写入其无法识别的新枚举；新增状态先通过兼容映射或 feature gate 引入。

需要索引：

```text
(origin_host, origin_ref)
(controller_host, controller_ref)
(executor_host, status)
```

## 4. `plugin_session_steps` 的兼容扩展

该表继续作为第一版 Workflow Attempt 的物理基础。保留 `task_id` 及旧状态语义，新增：

```text
executor_host          varchar(...) NOT NULL DEFAULT 'lazymind'
executor_ref           varchar(...) NOT NULL DEFAULT ''
resolved_operation     varchar(...) NOT NULL DEFAULT 'execute'
claim_owner            varchar(...) NOT NULL DEFAULT ''
lease_token_hash       varchar(...) NOT NULL DEFAULT ''
lease_generation       bigint NOT NULL DEFAULT 0
lease_expires_at       timestamp NULL
last_heartbeat_at      timestamp NULL
progress_json          json/jsonb NULL
terminal_command_id    varchar(...) NOT NULL DEFAULT ''
```

前向兼容规则：

- 旧行默认视为 `executor_host=lazymind`。
- LazyMind 兼容期继续写旧 `task_id`；Codex Attempt 可以令 `task_id=''`，但启用前必须确认所有旧 reader 对空值安全，若当前约束为非空则先以空字符串默认 expand。
- lease/fencing 只在新 Executor feature flag 启用时生效；旧派发路径不得被新 reclaimer 抢占。
- 不修改旧 worker 依赖的 status 含义；claim/running 的更细状态可以先由 lease 字段推导，待旧 worker 退出后再决定是否扩展枚举。
- 新索引至少覆盖 queued claim 扫描和 lease expiry；创建方式不得长时间阻塞生产写入。

## 5. 新增表

新增表使用 Workflow 命名，因为它们没有历史兼容负担。

### `workflow_preparations`

保存 `prepare_workflow` 的短期、可审计启动准备：

```text
id
actor_id
workflow_ref
workflow_revision_id
request_hash
input_snapshot_json
capability_snapshot_json
status
expires_at
consumed_session_id
created_at
updated_at
```

`start_workflow` 必须通过 preparation ID + request hash + command ID 幂等消费；同一 preparation 不得创建多个 Session。

### `workflow_events`

保存可重放的持久 Workflow 事件：

```text
id
workflow_session_id
cursor
event_type
state_version
contract_version
payload_json
created_at
```

必须有唯一约束 `(workflow_session_id, cursor)`。领域事务在同一事务中直接追加对应持久事件；SSE gateway 从该日志发布和重放。需要外部执行或额外投递时，同一领域事务再写 `workflow_outbox`。高频 ephemeral progress 不要求逐条落此表。

### `workflow_outbox`

保存中立 Attempt dispatch/event delivery，不保存 LazyMind 专属 `SubAgent RunRequest`：

```text
id
workflow_session_id
attempt_id
event_type
payload_json
status
available_at
claim_owner
lease_generation
lease_expires_at
last_error
created_at
updated_at
```

旧 `plugin_run_outbox` 在兼容窗口内继续服务旧路径；禁止让旧 worker 消费新表，也禁止让新 Executor 把 Host 私有 payload 写入新表。

### `workflow_input_bindings`

保存 Session 级外部 Input Resource snapshot：

```text
id
workflow_session_id
material_id
resource_type
resource_id
resource_revision
content_hash
validity
created_by_command_id
created_at
```

现有 `plugin_attempt_input_bindings` 继续保存 Attempt 实际消费 witness，并增量增加中立 source 字段：

```text
source_type          varchar(...) NOT NULL DEFAULT 'artifact'
source_id            varchar(...) NOT NULL DEFAULT ''
source_revision      varchar(...) NOT NULL DEFAULT ''
content_hash         varchar(...) NOT NULL DEFAULT ''
```

旧 `material_revision_id` 保留。对于旧 Artifact binding 继续写该列；对于 Input Resource binding 使用新 source 字段，并在所有旧 reader 能安全处理前由 feature flag 隔离。

## 6. Resource Store 复用

优先复用现有：

```text
uploaded_files
personal_resources
personal_resource_blobs
personal_resource_revisions
```

不要求新建一套 Workflow blob store。Host File Adapter 将不同来源规范化为 `(resource_type, resource_id, revision, content_hash)`；Runtime 只保存中立引用和权限 capability，不保存 Host 临时 URL、本地路径或访问 token。

## 7. Schema capability gate

新服务启动时必须检测所需 schema capability，而不是假设 migration 已完成。建议以 migration registry 加代码内 capability map 实现，例如：

```text
workflow.session.host_refs.v1
workflow.attempt.lease.v1
workflow.events.replay.v1
workflow.inputs.resource_binding.v1
```

规则：

- capability 缺失时，相关 feature flag 保持关闭并报告明确健康检查错误。
- 只读旧路径可继续服务，不得因某个新 capability 缺失导致整个 LazyMind 不可用。
- Runtime 不得在请求中途才发现缺表后自动 DDL。
- MCP/Host Adapter 只声明 Runtime 已启用的 capability。

## 8. Backfill 与 shadow

- 旧 Session host refs 可以按 `conversation_id` 分批回填为 LazyMind 来源；未回填行仍通过读取默认规则正确解释。
- 大表 backfill 必须分批、可恢复、限速，并记录 cursor；不得在 schema migration 事务中全表更新。
- 新旧 projection shadow compare 只读同一旧事实，禁止为了对比进行无去重 dual-write。
- 事件表启用前，可以从 Outbox 起点开始记录，不要求伪造完整历史；旧 Session 首次连接通过当前 snapshot 建立新 cursor 基线。

## 9. 回滚和 contract gate

回滚顺序：

1. 关闭新 Workflow/Executor/Event feature flag。
2. 停止新 claim，不删除 queued 数据。
3. 等待或取消已 claim Attempt 到安全终态。
4. 恢复旧 dispatch/client 路径。
5. 保留所有新增表列，供后续恢复和审计。

只有同时满足以下条件，未来 contract migration 才能删除旧结构：

- 所有旧 binary、worker 和脚本已停止；
- compatibility adapter 调用量在约定观测窗口内为零；
- rollback 已不再依赖旧结构；
- 数据保留/审计方案已批准；
- 有独立备份、验证和恢复演练。

## 10. 数据库验收测试

必须覆盖：

- 旧 schema fixture 执行 expand migration 后，旧版本核心读写测试仍通过；
- 新 reader 正确读取未 backfill 的旧 Session/Attempt；
- 新 LazyMind Session 同时写旧引用与中立引用；
- Codex Session 使用 `conversation_id=''` 且不被旧对话查询误关联；
- 新字段默认值不改变旧 worker 行为；
- preparation 幂等消费；
- Attempt lease/fencing 与旧 dispatch feature 隔离；
- Workflow event cursor 唯一、重放和 snapshot 基线；
- Input Resource binding 与旧 Artifact binding 共存；
- 新二进制回滚后旧路径仍能服务旧 Workflow；
- migration 重复执行安全，大表索引/回填不持有不可接受的锁。
