from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import torch
import time
import os
from transformers import AutoModel, AutoProcessor
from PIL import Image
import requests
from io import BytesIO

MODEL_PATH = "/home/mnt/cuishaoting/clipmodel/chinese-clip-vit-base-patch16"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

app = FastAPI()

processor = AutoProcessor.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = AutoModel.from_pretrained(MODEL_PATH, trust_remote_code=True).to(DEVICE).eval()

# 👉 单独拿 tokenizer（关键）
tokenizer = processor.tokenizer


# =========================
# Request
# =========================
class EmbedRequest(BaseModel):
    input: str


# =========================
# 工具函数
# =========================
def is_image_path(path: str):
    return os.path.exists(path) and path.lower().endswith(
        (".jpg", ".jpeg", ".png", ".bmp", ".webp")
    )


def is_image_url(url: str):
    return url.startswith("http") and any(
        url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]
    )


def load_image(input_str: str):
    try:
        if is_image_path(input_str):
            return Image.open(input_str).convert("RGB")

        if is_image_url(input_str):
            resp = requests.get(input_str, timeout=5)
            return Image.open(BytesIO(resp.content)).convert("RGB")
    except Exception as e:
        print("image load failed:", e)

    return None


# =========================
# 通用 embedding 接口
# =========================
@app.post("/embed")
def embed(req: EmbedRequest):
    start = time.time()

    if not req.input or req.input.strip() == "":
        return {"error": "empty input"}

    image = load_image(req.input)

    try:
        if image is not None:
            # ===== IMAGE =====
            inputs = processor(images=image, return_tensors="pt").to(DEVICE)

            with torch.no_grad():
                outputs = model.get_image_features(**inputs)

            mode = "image"

        else:
            return {
            "type": '纯文本mock',
            "embedding": [1 for i in range(512)],
            "latency_ms": (end - start) * 1000
        }

            # inputs = tokenizer(
            #     [req.input],
            #     padding=True,
            #     truncation=True,
            #     return_tensors="pt"
            # )

            # # 👉 Chinese-CLIP 必须要这个
            # if "token_type_ids" not in inputs:
            #     inputs["token_type_ids"] = torch.zeros_like(inputs["input_ids"])

            # inputs = {k: v.to(DEVICE) for k, v in inputs.items()}

            # # debug（可留）
            # # print("inputs keys:", inputs.keys())

            # with torch.no_grad():
            #     outputs = model.get_text_features(**inputs)

            # mode = "text"

        end = time.time()

        embedding = outputs[0].cpu().numpy()

        # ✅ benchmark
        print("\n====== UNIVERSAL EMBED ======")
        print(f"input: {req.input}")
        print(f"type: {mode}")
        print(f"dim: {embedding.shape[0]}")
        print(f"latency: {(end - start)*1000:.2f} ms")
        print("=============================\n")

        return {
            "type": mode,
            "embedding": embedding.tolist(),
            "latency_ms": (end - start) * 1000
        }

    except Exception as e:
        return {
            "error": str(e),
            "input": req.input
        }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=18080)