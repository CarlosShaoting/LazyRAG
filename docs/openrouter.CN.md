# OpenRouter 配置指南

**[English](openrouter.md)** | **中文**

LazyMind 通过 OpenRouter 的统一 API 使用对话、视觉、向量和文生图模型。

当前 LazyMind 的 OpenRouter 适配范围是对话、图片理解、文本向量和文生图。OpenRouter 模型目录中出现 `video`、`speech`、`transcription` 或 `audio`，只表示 OpenRouter 平台具备这些输出能力，不代表它们已经接入 LazyMind 对应的语音或视频运行时。

## 连接配置

在 **设置 → 模型供应商 → OpenRouter** 中填写：

| 配置项 | 值 |
|---|---|
| Base URL | `https://openrouter.ai/api/v1/` |
| API Key | 在 [OpenRouter Keys](https://openrouter.ai/settings/keys) 创建的 Key |

官方 Base URL 必须填写 API Key。自定义或私有化 Base URL 可以留空；如果自部署服务启用了鉴权，仍应填写其 API Key。

Base URL 应填写 API 根地址，不要附加 `/chat/completions`、`/embeddings` 或 `/images`。LazyMind 会根据模型类型选择正确端点。

## 内置模型

| 用途 | 默认模型 | 费用说明 |
|---|---|---|
| 大模型 | `z-ai/glm-5.3-flash` | 以 OpenRouter 当前模型定价为准 |
| 视觉模型 | `openrouter/free` | 只路由到免费模型，并按图片输入筛选具备视觉能力的模型 |
| 向量模型 | `liquid/lfm-2.5-embedding-350m:free` | 免费，但上下文和限流更适合试用与低流量场景 |
| 文生图 | `bytedance-seed/seedream-4.5` | 收费模型，需要账户余额 |

`openrouter/auto` 仍可手动选择，但它不是免费路由器。它会根据任务选择模型，并按最终选中的模型计费。若账户没有可用余额，可能返回 HTTP 402。

OpenRouter 的模型会持续变化。添加其他模型时，请从 [OpenRouter Models](https://openrouter.ai/models) 复制完整模型 ID，并在连接分组中选择正确类型。

## 免费视觉模型

图片识别建议将系统默认视觉模型设置为 `openrouter/free`。该路由器接受文字和图片输入，并会从当前可用的免费模型中筛选支持图片理解的模型。

已有 OpenRouter 配置不会强制覆盖用户手动选择的模型。如果日志仍显示：

```text
[module=vlm] [source=openrouter] [model=openrouter/auto]
```

请进入 **设置 → 系统默认设置 → 视觉模型**，手动切换为 `openrouter/free`。

## 向量与文生图

- 向量请求使用 OpenRouter 的 `/api/v1/embeddings` 端点。
- 文生图请求使用 OpenRouter 的 `/api/v1/images` 端点。
- 不要把文生图模型配置成 VLM：VLM 用于理解图片，文生图用于生成图片。
- 文生图模型通常收费；选择前请在模型页面确认价格和账户额度。

## 常见错误

### HTTP 402

表示 OpenRouter 要求可用额度或所选模型需要付费。检查日志中的 `model=`：

- `openrouter/auto`：可能选择收费模型；无余额时改用 `openrouter/free`，或为账户充值。
- 明确的收费模型：充值或改用带 `:free` 后缀且支持相应能力的模型。
- 文生图模型：大多数需要余额，`openrouter/free` 不能替代专用文生图模型。

### HTTP 401 / 403

检查 API Key 是否正确、是否被禁用，以及 Key 或账户是否设置了额度、模型或来源限制。

### HTTP 429

免费模型的速率和每日请求限制较低。降低请求频率、稍后重试，或改用付费模型。

### 修改目录后仍看不到模型

重启 Core 服务以重新同步模型目录，重启 Algorithm 服务以加载 OpenRouter 运行时适配。已有分组会补入新增的默认模型，但不会覆盖已经手动选择的系统默认模型。

## 官方参考

- [模型目录](https://openrouter.ai/models)
- [免费模型路由器](https://openrouter.ai/docs/guides/routing/routers/free-router)
- [自动路由器](https://openrouter.ai/docs/guides/routing/routers/auto-router)
- [Embeddings API](https://openrouter.ai/docs/api/api-reference/embeddings/create-embeddings)
- [Image Generation API](https://openrouter.ai/docs/guides/overview/multimodal/image-generation)
