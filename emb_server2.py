import base64
import os
import time
from io import BytesIO
from typing import List, Optional, Union

import requests
import torch
import uvicorn
from fastapi import FastAPI
from PIL import Image
from pydantic import BaseModel
from transformers import AutoModel, AutoProcessor

MODEL_PATH = "/home/mnt/cuishaoting/clipmodel/chinese-clip-vit-base-patch16"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
PORT = int(os.getenv("EMB_SERVER_PORT", "18081"))
TEXT_EMBED_DIM = 512

app = FastAPI()

processor = AutoProcessor.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = AutoModel.from_pretrained(MODEL_PATH, trust_remote_code=True).to(DEVICE).eval()


class EmbedRequest(BaseModel):
    input: Optional[Union[str, List[str]]] = None
    inputs: Optional[Union[str, List[str]]] = None
    model: Optional[str] = None
    modality: Optional[str] = None


def is_image_path(path: str) -> bool:
    return os.path.exists(path) and path.lower().endswith(
        (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tiff", ".tif")
    )


def is_image_url(url: str) -> bool:
    return url.startswith(("http://", "https://")) and any(
        url.lower().endswith(ext)
        for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".tif"]
    )


def is_data_image_url(value: str) -> bool:
    return isinstance(value, str) and value.startswith("data:image/")


def load_data_image(data_url: str):
    try:
        header, encoded = data_url.split(",", 1)
        if ";base64" not in header:
            return None
        raw = base64.b64decode(encoded)
        return Image.open(BytesIO(raw)).convert("RGB")
    except Exception as e:
        print("data image load failed:", e)
        return None


def load_image(input_str: str):
    try:
        if is_data_image_url(input_str):
            return load_data_image(input_str)

        if is_image_path(input_str):
            return Image.open(input_str).convert("RGB")

        if is_image_url(input_str):
            resp = requests.get(input_str, timeout=10)
            resp.raise_for_status()
            return Image.open(BytesIO(resp.content)).convert("RGB")
    except Exception as e:
        print("image load failed:", e)

    return None


def normalize_inputs(req: EmbedRequest) -> List[str]:
    raw = req.input if req.input is not None else req.inputs
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    return [str(item) for item in raw]


def mock_text_embedding() -> List[float]:
    return [1.0] * TEXT_EMBED_DIM


def embed_one(value: str, force_image: bool = False):
    image = load_image(value)

    if image is not None:
        inputs = processor(images=image, return_tensors="pt").to(DEVICE)
        with torch.no_grad():
            outputs = model.get_image_features(**inputs)
        return outputs[0].detach().cpu().tolist(), "image"

    if force_image:
        raise ValueError("modality=image but input is not a valid image")

    return mock_text_embedding(), "text"


def build_response(embeddings: List[List[float]], mode: str, start: float):
    end = time.time()
    data = [{"embedding": emb, "index": idx} for idx, emb in enumerate(embeddings)]
    resp = {
        "object": "list",
        "data": data,
        "model": MODEL_PATH,
        "type": mode,
        "latency_ms": (end - start) * 1000,
    }
    if len(embeddings) == 1:
        resp["embedding"] = embeddings[0]
    return resp


@app.post("/embed")
def embed(req: EmbedRequest):
    start = time.time()
    items = normalize_inputs(req)

    if not items:
        return {"error": "empty input"}

    try:
        embeddings = []
        modes = []
        force_image = req.modality == "image"

        for item in items:
            emb, mode = embed_one(item, force_image=force_image)
            embeddings.append(emb)
            modes.append(mode)

        final_mode = modes[0] if len(set(modes)) == 1 else "mixed"

        print("\n====== UNIVERSAL EMBED V2 ======")
        print(f"input: {items[0] if len(items) == 1 else f'batch[{len(items)}]'}")
        print(f"type: {final_mode}")
        print(f"dim: {len(embeddings[0]) if embeddings else 0}")
        print(f"latency: {(time.time() - start) * 1000:.2f} ms")
        print("================================\n")

        return build_response(embeddings, final_mode, start)

    except Exception as e:
        return {
            "error": str(e),
            "input": items,
        }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
