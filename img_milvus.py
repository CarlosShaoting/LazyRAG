import argparse
import hashlib
import tempfile
from pathlib import Path

from lazyllm.tools.rag import Document, Retriever
from lazyllm.tools.rag.store.store_base import LAZY_ROOT_NAME
from PIL import Image

from chat.pipelines.builders.get_models import get_automodel
from chat.utils.load_config import get_retrieval_settings
from parsing.image_reader import ImageReader

# =========================
# 配置
# =========================
DEFAULT_INPUT_DIR = Path("/home/mnt/cuishaoting/LazyRAG/test_doc")
# DEFAULT_MILVUS_DB_PATH = Path("/home/mnt/cuishaoting/LazyRAG/milvus_test.db")
DEFAULT_MILVUS_DB_PATH = "tcp://localhost:19531"

IMAGE_SUFFIXES = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"
}

NORMALIZED_IMAGE_DIR = Path(tempfile.gettempdir()) / "lazyrag_test_img_doc"


# =========================
# （可选）图片规范化（现在 dataset_path 不强依赖）
# =========================
def normalize_image_file(image_path: str) -> str:
    src = Path(image_path).resolve()
    NORMALIZED_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256(str(src).encode("utf-8")).hexdigest()[:16]
    dst = NORMALIZED_IMAGE_DIR / f"{src.stem}_{digest}.jpg"

    if dst.exists():
        return str(dst)

    with Image.open(src) as img:
        rgb = img.convert("RGB")
        rgb.save(dst, format="JPEG", quality=95)

    return str(dst)


# =========================
# embedding key
# =========================
def resolve_image_embed_key(explicit_key=None):
    settings = get_retrieval_settings()

    if explicit_key:
        return explicit_key

    if "siglip" in settings.embed_keys:
        return "siglip"

    if not settings.embed_keys:
        raise RuntimeError("No embedding key found.")

    return settings.embed_keys[-1]


# =========================
# 构建 Document（dataset_path版）
# =========================
def build_image_document(input_dir: Path, image_embed_key):
    embed_model = get_automodel(image_embed_key)
    milvus_store_conf = build_milvus_store_conf()

    # ✅ 关键：用 dataset_path
    documents = Document(
        dataset_path=str(input_dir),
        embed={image_embed_key: embed_model},
        store_conf=milvus_store_conf,
    )

    # 注册图片 reader
    image_reader = ImageReader(
        embed_key=image_embed_key,
        embed_model=embed_model,
    )

    for ext in IMAGE_SUFFIXES:
        documents.add_reader(f"*{ext}", image_reader)

    # 激活 group
    documents.activate_group("image", embed_keys=[image_embed_key])

    return documents


def build_milvus_store_conf():
    return {
        "type": "milvus",
        "kwargs": {
            "uri": str(DEFAULT_MILVUS_DB_PATH),
            "db_name": '11111',
            "index_kwargs": {
                "index_type": "FLAT",
                "metric_type": "COSINE",
            },
        },
    }


def reload_documents_from_db(image_embed_key):
    embed_model = get_automodel(image_embed_key)

    documents = Document(
        dataset_path=str(DEFAULT_INPUT_DIR),
        embed={image_embed_key: embed_model},
        store_conf=build_milvus_store_conf()
    )

    image_reader = ImageReader(
        embed_key=image_embed_key,
        embed_model=embed_model,
    )

    for ext in IMAGE_SUFFIXES:
        documents.add_reader(f"*{ext}", image_reader)

    documents.activate_group("image", embed_keys=[image_embed_key])

    # root_nodes, total = documents.get_nodes(
    #     group=LAZY_ROOT_NAME,
    #     limit=10000,
    #     return_total=True,
    # )
    # doc_paths = sorted({
    #     str(getattr(node, "docpath", "")).strip()
    #     for node in root_nodes
    #     if str(getattr(node, "docpath", "")).strip()
    # })

    print("\n♻️ 检测到已有 Milvus DB，直接从 DB 加载索引")
    print(f"DB: {DEFAULT_MILVUS_DB_PATH}")
    # print(f"Embedding: {image_embed_key}")
    # print(f"Loaded docs: {len(doc_paths)} (root nodes: {total})")
    # for path in doc_paths[:10]:
    #     print(f"  - {path}")
    # if len(doc_paths) > 10:
    #     print(f"  ... and {len(doc_paths) - 10} more")

    return documents, image_embed_key


# =========================
# BUILD 阶段
# =========================
def build_image_index(input_dir: Path, image_embed_key=None):

    print("\n🚧 开始 Build Index...")

    if not input_dir.is_dir():
        raise NotADirectoryError(f"Invalid dir: {input_dir}")

    image_embed_key = resolve_image_embed_key(image_embed_key)

    documents = build_image_document(input_dir, image_embed_key)

    retriever = Retriever(
        doc=documents,
        group_name="image",
        similarity="cosine",
        topk=1,
        embed_keys=[image_embed_key],
    )

    print("⚙️ 正在触发 embedding & 入库...")
    retriever.start()  

    print("✅ Build 完成")
    print(f"目录: {input_dir}")
    print(f"Embedding: {image_embed_key}")

    return documents, image_embed_key


# =========================
# RETRIEVE 阶段
# =========================
def retrieve_best_image(query, documents, topk, image_embed_key):

    retriever = Retriever(
        doc=documents,
        group_name="image",
        similarity="cosine",
        topk=topk,
        embed_keys=[image_embed_key],
    )

    nodes = retriever(query)

    if not nodes:
        print("❌ No match found.")
        return

    best_node = max(
        nodes,
        key=lambda n: n.similarity_score if n.similarity_score else float("-inf"),
    )

    print("\n🔍 Query:", query)
    print("Top Matches:")

    for node in nodes:
        print(f"  score={node.similarity_score:.6f} image={node.image_path}")

    print("\n🏆 Best Match:")
    print("image:", best_node.image_path)
    print("score:", best_node.similarity_score)


# =========================
# 主入口
# =========================
def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("query", nargs="?", default=None)
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--topk", type=int, default=3)
    parser.add_argument("--embed-key", default=None)
    parser.add_argument("--force-rebuild", action="store_true")

    args = parser.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    image_embed_key = resolve_image_embed_key(args.embed_key)

    # if DEFAULT_MILVUS_DB_PATH.exists() and not args.force_rebuild:
    #     documents, image_embed_key = reload_documents_from_db(image_embed_key)
    # else:
    documents, image_embed_key = build_image_index(
        input_dir,
        image_embed_key=image_embed_key,
    )


    while True:
        query = args.query or input("\n请输入检索内容 (exit退出): ").strip()

        if not query or query.lower() == "exit":
            break

        retrieve_best_image(
            query,
            documents,
            args.topk,
            image_embed_key,
        )

        args.query = None


if __name__ == "__main__":
    main()
