import argparse
import hashlib
import tempfile
from pathlib import Path

from lazyllm.tools.rag import Document, Retriever
from PIL import Image

from chat.pipelines.builders.get_models import get_automodel
from chat.utils.load_config import get_retrieval_settings
from parsing.image_reader import ImageReader

DEFAULT_INPUT_DIR = Path("/home/mnt/cuishaoting/LazyRAG/test_doc")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"}
NORMALIZED_IMAGE_DIR = Path(tempfile.gettempdir()) / "lazyrag_test_img_doc"


def list_image_files(input_dir: Path) -> list[str]:
    return [
        str(path.resolve())
        for path in sorted(input_dir.iterdir())
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]


def normalize_image_file(image_path: str) -> str:
    src = Path(image_path).resolve()
    NORMALIZED_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(str(src).encode("utf-8")).hexdigest()[:16]
    dst = NORMALIZED_IMAGE_DIR / f"{src.stem}_{digest}.jpg"
    with Image.open(src) as img:
        rgb = img.convert("RGB")
        rgb.save(dst, format="JPEG", quality=95)
    return str(dst)


def normalize_image_files(image_files: list[str]) -> tuple[list[str], dict[str, str]]:
    normalized_files = []
    normalized_to_original = {}
    for image_file in image_files:
        normalized = normalize_image_file(image_file)
        normalized_files.append(normalized)
        normalized_to_original[normalized] = image_file
    return normalized_files, normalized_to_original


def resolve_image_embed_key(explicit_key: str | None = None) -> str:
    settings = get_retrieval_settings()
    if explicit_key:
        return explicit_key
    if "siglip" in settings.embed_keys:
        return "siglip"
    image_embed_key = settings.embed_keys[-1] if settings.embed_keys else None
    if image_embed_key is None:
        raise RuntimeError("No embedding key found in retrieval settings.")
    return image_embed_key


def build_image_document(image_files: list[str], image_embed_key: str) -> Document:
    embed_model = get_automodel(image_embed_key)
    milvus_store_conf = {
  'type': 'milvus',  # 指定存储后端类型
  'kwargs': {
    'uri': 'test.db',  # 存储后端地址，本例子使用的是本地文件 test.db，文件不存则创建新文件
    'index_kwargs': {  # 存储后端的索引配置
      'index_type': 'FLAT',  # 索引类型
      'metric_type': 'COSINE',  # 相似度计算方式
    }
  },
}

    documents = Document(
        embed={image_embed_key: embed_model},
        doc_files=image_files,
        manager=False,
        store_conf={"type": "map"},
    )

    image_reader = ImageReader(
        embed_key=image_embed_key,
        embed_model=embed_model,
    )
    for ext in IMAGE_SUFFIXES:
        documents.add_reader(f"*{ext}", image_reader)
    documents.activate_group("image", embed_keys=[image_embed_key])
    return documents


def retrieve_best_image(query: str, input_dir: Path, topk: int, image_embed_key: str | None = None) -> None:
    original_files = list_image_files(input_dir)
    if not original_files:
        raise RuntimeError(f"No image files found under {input_dir}")

    image_embed_key = resolve_image_embed_key(image_embed_key)
    image_files, normalized_to_original = normalize_image_files(original_files)
    documents = build_image_document(image_files, image_embed_key=image_embed_key)
    retriever = Retriever(
        doc=documents,
        group_name="image",
        similarity="cosine",
        topk=topk,
        embed_keys=[image_embed_key],
    )
    print('Created retriver')
    nodes = retriever(query)
    if not nodes:
        print("No matched image found.")
        return

    best_node = max(nodes, key=lambda node: node.similarity_score if node.similarity_score is not None else float("-inf"))

    print("query:", query)
    print("input_dir:", input_dir)
    print("image_embed_key:", image_embed_key)
    print("indexed_images:")
    for image_file in original_files:
        print(" ", image_file)
    print("top_matches:")
    for node in nodes:
        original_path = normalized_to_original.get(node.image_path, node.image_path)
        print(f"  score={node.similarity_score:.6f} image={original_path}")
    print("best_image:", normalized_to_original.get(best_node.image_path, best_node.image_path))
    print("best_score:", best_node.similarity_score)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", default=None)
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--topk", type=int, default=3)
    parser.add_argument("--embed-key", default=None)
    args = parser.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input dir not found: {input_dir}")

    query = args.query.strip() if args.query else input("请输入检索内容: ").strip()
    if not query:
        raise ValueError("Query cannot be empty.")

    retrieve_best_image(
        query=query,
        input_dir=input_dir,
        topk=args.topk,
        image_embed_key=args.embed_key,
    )


if __name__ == "__main__":
    main()


# 运行指令
#
# export PYTHONPATH=/home/mnt/cuishaoting/LazyRAG:/home/mnt/cuishaoting/LazyRAG/algorithm
# export LAZYRAG_MODEL_CONFIG_PATH=/home/mnt/cuishaoting/LazyRAG/algorithm/chat/runtime_models.yaml
# python /home/mnt/cuishaoting/LazyRAG/test_img_doc.py "一只大象"
