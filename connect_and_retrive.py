import argparse
from pathlib import Path

from lazyllm.tools.rag import Document, Retriever
import lazyllm.tools.rag.document as document_module

from chat.pipelines.builders.get_models import get_automodel
from chat.utils.load_config import get_retrieval_settings
from parsing.image_reader import ImageReader


# =========================
# 配置
# =========================
DEFAULT_INPUT_DIR = Path("/home/mnt/cuishaoting/LazyRAG/test_doc")

IMAGE_SUFFIXES = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"
}


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
# Milvus 配置（TCP）
# =========================
def build_milvus_store_conf(embed_key):
    return {
        "vector_store": {
            "type": "milvus",
            "kwargs": {
                "uri": "tcp://127.0.0.1:19531",
                "db_name": "add_img_emb",
                "index_kwargs": {
                    "embed_key": embed_key,
                    "index_type": "IVF_FLAT",
                    "metric_type": "COSINE",
                    "params": {"nlist": 128},
                },
            },
        }
    }


# =========================
# 从 Milvus 加载
# =========================
def load_documents(input_dir: Path, embed_key):
    embed_model = get_automodel(embed_key)

    documents = Document(
        dataset_path=str(input_dir),
        embed={embed_key: embed_model},
        store_conf=build_milvus_store_conf(embed_key),
    )

    # 注册 reader（⚠️ 必须要，否则 query embedding 不一致）
    image_reader = ImageReader(
        embed_key=embed_key,
        embed_model=embed_model,
    )

    for ext in IMAGE_SUFFIXES:
        documents.add_reader(f"*{ext}", image_reader)

    documents.activate_group("image", embed_keys=[embed_key])

    # ⚠️ 关键：这里只是 load，不会重新 build
    documents.start()

    print("✅ 已连接 Milvus（直接使用已有向量数据）")

    return documents


# =========================
# 检索
# =========================
def retrieve(query, retriever):
    nodes = retriever(query)

    if not nodes:
        print("❌ No match found.")
        return

    print("\n🔍 Query:", query)

    for node in nodes:
        print(f"score={node.similarity_score:.6f} image={node.image_path}")

    best = max(nodes, key=lambda n: n.similarity_score or -1)

    print("\n🏆 Best Match:")
    print("image:", best.image_path)
    print("score:", best.similarity_score)


# =========================
# 主入口
# =========================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--topk", type=int, default=3)
    parser.add_argument("--embed-key", default=None)

    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    embed_key = resolve_image_embed_key(args.embed_key)

    # ✅ 只加载，不 build
    documents = load_documents(input_dir, embed_key)

    retriever = Retriever(
        doc=documents,
        group_name="image",
        similarity="cosine",
        topk=args.topk,
        embed_keys=[embed_key],
    )

    # 交互查询
    while True:
        query = input("\n请输入检索内容 (exit退出): ").strip()

        if not query or query.lower() == "exit":
            break

        retrieve(query, retriever)


if __name__ == "__main__":
    main()

# 确定 query 是 embedding_siglipo