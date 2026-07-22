# HTML → PNG → PPTX 轻量导出方案

> 目标：前端一键把 sn-ppt / ppt-multi-styles 生成的 HTML 幻灯片导出为 PNG，再由算法侧（或后端转发）拼成 PPTX。**不依赖 3.5GB Playwright Docker 镜像**。

## 背景

当前 sn-ppt-standard 的 `export_pptx/html_to_pptx.mjs` 链路：

```text
HTML → Playwright/Chromium DOM 解析 → pptxgenjs → PPTX
```

问题：

- 生产环境需要 Playwright + Chromium（镜像 ~3.5GB，或额外 ~280MB 浏览器缓存）
- WSL/容器内还常缺系统库（`libnspr4`、`libglib` 等）
- 与 LazyMind 主栈（Go core + Python chat）耦合弱，难以在前端产品化

已有可复用资产：

| 资产 | 位置 | 能力 |
|------|------|------|
| 前端 HTML→PNG 原型 | `html-to-png-tool/` | `html-to-image`，npm 仅 ~58MB |
| PNG→PPTX 脚本 | `skills/sn_ppt/sn-ppt-creative/scripts/build_pptx.py` | `python-pptx`，每页满版 16:9 |
| HTML 生成流水线 | `skills/sn_ppt/sn-ppt-standard/scripts/run_stage.py` | 产出 `pages/page_*.html` |
| 文件落盘 | Go core `LAZYMIND_UPLOAD_ROOT` | 已有 upload / signed URL 机制 |

结论：**前端负责渲染截图，算法侧负责 PPTX 拼接**，是更轻、更稳的产品化路径。

---

## 推荐架构

```text
┌─────────────┐     ① html-to-image      ┌──────────────┐
│  前端 React  │ ──────────────────────► │  PNG blobs   │
│  [导出 PPT]  │     (浏览器内 .wrapper)  │  page_001..N │
└──────┬──────┘                          └──────┬───────┘
       │ ② multipart/form-data                     │
       ▼                                           ▼
┌─────────────┐     ③ 转发/落盘          ┌──────────────┐
│  Go core    │ ──────────────────────► │ deck_dir/    │
│  POST /ppt  │                         │ preview/*.png│
└──────┬──────┘                          └──────┬───────┘
       │ ④ 调用算法侧                            │
       ▼                                           ▼
┌─────────────┐     ⑤ python-pptx        ┌──────────────┐
│ Python chat │ ──────────────────────► │  deck.pptx   │
│ build_pptx  │                         │  + 下载 URL  │
└─────────────┘                          └──────────────┘
```

### 职责划分

| 层 | 职责 | 不做 |
|----|------|------|
| **前端** | 加载 HTML、按页截图、上传 PNG、展示进度/下载 | 不拼 PPTX、不跑 Playwright |
| **Go core** | 鉴权、deck 路径校验、文件落盘、调用 Python、返回 signed URL | 不做 DOM 解析 |
| **Python 算法侧** | `build_pptx` 拼接、写 `deck.pptx`、可选保留 HTML/PNG | 不生成 HTML 内容 |

---

## 前端设计

### 入口

在 PPT 预览页（或 chat artifact 预览）增加按钮：

```text
[导出 PNG]  [导出 PPT]
```

- **导出 PNG**：仅前端 `html-to-image`，zip 下载或直接存 `preview/`
- **导出 PPT**：PNG 上传 + 调后端拼接

### 技术选型

- 库：`html-to-image`（已验证，核心包 ~520KB）
- 截图目标：`.wrapper`（1600×900，`pixelRatio: 2`）
- 离屏渲染：隐藏 `iframe` 逐页加载 `/decks/{deck_id}/pages/page_NNN.html`

### 前端伪代码

```ts
async function exportDeckToPng(deckId: string, pageNames: string[]) {
  const blobs: Blob[] = [];
  for (const name of pageNames) {
    const blob = await renderPageToPng(`/decks/${deckId}/pages/${name}`);
    blobs.push(blob);
  }
  return blobs;
}

async function exportDeckToPptx(deckId: string, blobs: Blob[]) {
  const form = new FormData();
  form.append('deck_id', deckId);
  blobs.forEach((b, i) => form.append('pages', b, `page_${String(i + 1).padStart(3, '0')}.png`));
  const res = await fetch('/api/core/ppt/decks:export', { method: 'POST', body: form });
  return res.json(); // { pptx_url, deck_id }
}
```

### 注意点

- 远程字体/CDN：HTML 应优先本地字体 fallback（sn-ppt 已要求）
- ECharts：需等 `window.__pptxChartsReady` 或额外 `setTimeout` 再截图
- 跨域：HTML/静态资源需同域或通过 core 静态路由提供

---

## 后端（Go core）设计

### API 草案

```http
POST /api/core/ppt/decks:export
Authorization: Bearer ...
Content-Type: multipart/form-data

deck_id=cyberpunk_ai_minimax
pages=@page_001.png
pages=@page_002.png
...
```

响应：

```json
{
  "deck_id": "cyberpunk_ai_minimax",
  "pptx_path": "/var/lib/lazymind/uploads/ppt_decks/cyberpunk_ai_minimax/deck.pptx",
  "pptx_url": "https://.../signed-url/deck.pptx",
  "page_count": 4,
  "html_dir": ".../pages/"
}
```

### Go core 流程

1. RBAC：校验用户对 deck / conversation / artifact 的读权限
2. 校验：`page_count`、单文件大小、总大小上限（建议单页 ≤2MB，总计 ≤20MB）
3. 落盘：`{upload_root}/ppt_decks/{deck_id}/preview/page_NNN.png`
4. 调 Python：`POST http://chat:8046/api/ppt/build`（内网）
5. 返回 signed download URL

### 为何经 Go core 而不是前端直连 Python

- 统一鉴权（Kong + RBAC）
- 统一 upload 路径与 ACL
- 与现有 chat / artifact 链路一致

---

## 算法侧（Python chat）设计

### API 草案

```http
POST /api/ppt/build
Content-Type: application/json

{
  "deck_dir": "/var/lib/lazymind/uploads/ppt_decks/cyberpunk_ai_minimax",
  "deck_id": "cyberpunk_ai_minimax",
  "output": "/var/lib/lazymind/uploads/ppt_decks/cyberpunk_ai_minimax/deck.pptx"
}
```

### 实现

复用 `skills/sn_ppt/sn-ppt-creative/scripts/build_pptx.py` 逻辑：

```python
# algorithm/lazymind/chat/engine/ppt/build_pptx.py
from pptx import Presentation
from pptx.util import Inches

SLIDE_W = Inches(13.333)  # 16:9
SLIDE_H = Inches(7.5)

def build_pptx_from_pngs(deck_dir: Path, output: Path) -> dict:
    # 读 outline.json 或按 page_001..page_NNN 排序
    # 每页 add_picture 满版
    ...
```

依赖：`python-pptx`（轻量，~数 MB，algorithm 镜像可加入）

### 可选增强

- 若 `pages/*.html` 存在但 PNG 缺失：返回 400，提示前端先截图
- 若 PNG 存在但 HTML 更新过：以 PNG 为准（截图即所见即所得）
- 后续可加 `preview/` + `deck.pptx` 一并作为 artifact 回传 chat

---

## 与 sn-ppt skill 的衔接

### 现有流水线

```text
sn-ppt-entry → sn-ppt-standard → pages/page_*.html
                                      ↓
                              （新）前端导出 PNG
                                      ↓
                              Python build_pptx → deck.pptx
```

### 替换关系

| 旧路径 | 新路径 |
|--------|--------|
| `run_stage.py export` + Playwright | 前端 `html-to-image` + `build_pptx.py` |
| `html_to_pptx.mjs` DOM 抽取 | 整页 PNG 满版贴入（视觉保真更高） |
| 3.5GB Docker | 浏览器 + python-pptx |

trade-off：

- **优点**：部署轻、效果稳定、HTML 原文件保留
- **缺点**：PPTX 内是图片页，不可编辑文字（与 creative 模式一致）

---

## 分阶段实施

### Phase 0 — 已完成（原型）

- [x] `html-to-png-tool/` 前端工具
- [x] CLI `batch-export.mjs`（Playwright 容器批量 PNG）
- [x] 验证 `cyberpunk_ai_minimax` 4 页导出效果

### Phase 1 — MVP（1～2 天）

1. 前端：把 `html-to-png-tool` 核心逻辑抽成 `frontend/src/modules/ppt/export/` 组件
2. Python：新增 `build_pptx_from_pngs()` + `/api/ppt/build` 路由
3. Go core：新增 `POST /ppt/decks:export` 转发 + 落盘
4. 前端按钮：「导出 PPT」打通全链路

验收：用户在 UI 点击一次，得到可打开的 4 页 PPTX + 保留 HTML/PNG。

### Phase 2 — 产品化（2～3 天）

1. 接入 chat artifact：sn-ppt 生成完成后自动出现「预览 / 导出 PPT」
2. deck 生命周期：与 `conversation_id` / `task_id` 绑定
3. 进度 SSE：`export_started` → `png_uploaded` → `pptx_ready`
4. 错误处理：ECharts 未渲染完、缺页、上传失败

### Phase 3 — 可选优化

1. 前端 Web Worker 并行截图多页
2. 后端异步任务（大 deck >10 页）
3. 可选「可编辑 PPT」路由到 MiniMax `pptx-generator`（native 元素，非 PNG）

---

## 依赖与体积对比

| 方案 | npm / Python 包 | 浏览器/运行时 | 总计量级 |
|------|-----------------|---------------|----------|
| **本方案（前端 PNG + python-pptx）** | ~58MB npm + ~5MB python-pptx | 用户浏览器 | **~65MB** |
| Playwright Docker 镜像 | ~15MB npm | Chromium in image | **~3.5GB** |
| Puppeteer 独立下载 | ~58MB npm | Chrome cache | **~650MB** |

---

## 风险与对策

| 风险 | 对策 |
|------|------|
| 浏览器截图与 Playwright 导出视觉不一致 | 以浏览器截图为准；统一 1600×900 + pixelRatio:2 |
| ECharts 未渲染完 | 等待 `__pptxChartsReady` 或固定 delay |
| 大 deck 上传慢 | 分页上传 + 进度条；后端异步拼接 |
| PPTX 不可编辑 | UI 明确标注「图片型 PPT」；需要可编辑时走 MiniMax 路线 |
| 安全 | 限制 deck 路径、文件类型、大小；RBAC 校验 |

---

## 建议目录结构（落地后）

```text
frontend/src/modules/ppt/
  export/
    renderPageToPng.ts      # html-to-image 封装
    uploadDeckPngs.ts       # 调 core API
    ExportPptButton.tsx     # UI 按钮

backend/core/ppt/
  handler.go                # POST /ppt/decks:export
  service.go                # 落盘 + 调 chat

algorithm/lazymind/chat/
  api/ppt_routes.py         # POST /api/ppt/build
  engine/ppt/build_pptx.py  # python-pptx 拼接
```

---

## 结论

**可以设计成「前端一个按钮 → HTML 转 PNG → 算法侧/后端拼 PPT」**，且比现有 Playwright 导出链路更适合 LazyMind 生产部署：

1. 前端：`html-to-image`（轻量，已有原型）
2. Go core：鉴权 + 落盘 + 转发（复用现有 upload 体系）
3. Python：`build_pptx.py` 逻辑（已有 sn-ppt-creative 脚本可参考）

建议 **Phase 1 优先做 Go core 转发 + Python build_pptx**，前端按钮直接复用 `html-to-png-tool/src/main.ts` 的核心逻辑。
