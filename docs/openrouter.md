# OpenRouter Configuration Guide

**English** | **[中文](openrouter.CN.md)**

LazyMind uses OpenRouter's unified API for chat, vision, embeddings, and image generation.

LazyMind currently adapts OpenRouter for chat, image understanding, text embeddings, and image generation. The presence of `video`, `speech`, `transcription`, or `audio` in OpenRouter's model catalog indicates an OpenRouter platform capability; it does not mean the corresponding LazyMind speech or video runtime is already integrated.

## Connection settings

Open **Settings → Model Providers → OpenRouter** and enter:

| Setting | Value |
|---|---|
| Base URL | `https://openrouter.ai/api/v1/` |
| API Key | A key created under [OpenRouter Keys](https://openrouter.ai/settings/keys) |

The official Base URL requires an API key. A custom or self-hosted Base URL may be used without a key; if that deployment enables authentication, enter its API key normally.

Use the API root as the Base URL. Do not append `/chat/completions`, `/embeddings`, or `/images`; LazyMind selects the endpoint for each model type.

## Built-in models

| Purpose | Default model | Cost notes |
|---|---|---|
| LLM | `z-ai/glm-5.3-flash` | Check its current OpenRouter pricing |
| Vision | `openrouter/free` | Routes only to free models and filters for vision support when an image is supplied |
| Embeddings | `liquid/lfm-2.5-embedding-350m:free` | Free, with context and rate limits better suited to evaluation and low-volume use |
| Image generation | `bytedance-seed/seedream-4.5` | Paid; available account credit is required |

`openrouter/auto` remains available for manual selection, but it is not a free router. It selects a model for the task and charges the selected model's normal price. Accounts without available credit may receive HTTP 402.

OpenRouter's catalog changes frequently. To add another model, copy its complete model ID from [OpenRouter Models](https://openrouter.ai/models) and assign the correct type in the connection group.

## Free vision usage

For image understanding, set the system-default vision model to `openrouter/free`. It accepts text and image inputs and filters the current pool of free models for image-understanding support.

LazyMind does not overwrite an existing manual model selection. If logs still show:

```text
[module=vlm] [source=openrouter] [model=openrouter/auto]
```

open **Settings → System Defaults → Vision Model** and switch it to `openrouter/free`.

## Embeddings and image generation

- Embedding requests use OpenRouter's `/api/v1/embeddings` endpoint.
- Image-generation requests use OpenRouter's `/api/v1/images` endpoint.
- Do not configure an image-generation model as a VLM: a VLM understands images, while an image-generation model creates them.
- Image-generation models are usually paid. Check model pricing and account credit before selecting one.

## Troubleshooting

### HTTP 402

OpenRouter requires available credit or the selected model is paid. Check `model=` in the LazyMind log:

- `openrouter/auto`: it may select a paid model; use `openrouter/free` or add account credit.
- An explicit paid model: add credit or choose a compatible model with a `:free` variant.
- Image generation: most models require credit, and `openrouter/free` is not a replacement for a dedicated image-generation model.

### HTTP 401 / 403

Check that the API key is valid and enabled, and that key or account limits do not block the selected model or request origin.

### HTTP 429

Free models have lower rate and daily request limits. Reduce request frequency, retry later, or select a paid model.

### Models are missing after a catalog update

Restart Core to synchronize the model catalog and restart Algorithm to load the OpenRouter runtime adapters. New defaults are added to existing groups, but an existing manual system-default selection is not overwritten.

## Official references

- [Model catalog](https://openrouter.ai/models)
- [Free Models Router](https://openrouter.ai/docs/guides/routing/routers/free-router)
- [Auto Router](https://openrouter.ai/docs/guides/routing/routers/auto-router)
- [Embeddings API](https://openrouter.ai/docs/api/api-reference/embeddings/create-embeddings)
- [Image Generation API](https://openrouter.ai/docs/guides/overview/multimodal/image-generation)
