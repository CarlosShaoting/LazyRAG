import argparse
import hashlib
import tempfile
from pathlib import Path
import time  
from lazyllm.tools.rag import Document, Retriever
from lazyllm.tools.rag.store.store_base import LAZY_ROOT_NAME
from PIL import Image
import lazyllm.tools.rag.document as document_module
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
# 构建 Document（dataset_path版）
# =========================
def build_image_document(input_dir: Path, image_embed_key):
    embed_model = get_automodel(image_embed_key)
    milvus_store_conf = build_milvus_store_conf()
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
            # 看起来没有效果 
            "segment_store": {  
            "type": "map",  
            "kwargs": {  
                "uri": "/tmp/vec_seg_1.db"  
            }  
        },
          'vector_store': {
              'type': 'milvus',
              'kwargs': {
                  'uri': 'tcp://127.0.0.1:19531',
                  'db_name': 'vec_seg_2',
                  'index_kwargs': {
                      'embed_key': 'siglip',
                      'index_type': 'IVF_FLAT',
                      'metric_type': 'COSINE',
                      'params': {
                          'nlist': 128,
                      }
                  }
              }
          }
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
    documents.start()

    print("\n♻️ 检测到已有 Milvus DB，直接从 DB 加载索引")
    print(f"DB: {DEFAULT_MILVUS_DB_PATH}")

    return documents, image_embed_key


# =========================
# BUILD 阶段
# =========================
def build_image_index(input_dir: Path, image_embed_key=None):

    print("\n🚧 开始 Build Index...")

    if not input_dir.is_dir():
        raise NotADirectoryError(f"Invalid dir: {input_dir}")

    image_embed_key = 'siglip'

    documents = build_image_document(input_dir, image_embed_key)
 
      
    # 等待处理完成  

    time.sleep(10)  # 等待后台处理完成  

    retriever = None
    # retriever = Retriever(
    #     doc=documents,
    #     group_name="image",
    #     similarity="cosine",
    #     topk=1,
    #     embed_keys=[image_embed_key],
    # )

    print("⚙️ 正在触发 embedding & 入库...")


    print("✅ Build 完成")
    print(f"目录: {input_dir}")
    print(f"Embedding: {image_embed_key}")
    
    return documents, image_embed_key, retriever


# =========================
# RETRIEVE 阶段
# =========================
def retrieve_best_image(query, documents, topk, image_embed_key, retriever):
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
    image_embed_key = 'siglip'

    # if DEFAULT_MILVUS_DB_PATH.exists() and not args.force_rebuild:
    #documents, image_embed_key = reload_documents_from_db(image_embed_key)
    # else:
    documents, image_embed_key, ret = build_image_index(
        input_dir,
        image_embed_key=image_embed_key,
    )

    import time
    while True:
        query = args.query or input("\n请输入检索内容 (exit退出): ").strip()

        if not query or query.lower() == "exit":
            break

        # retrieve_best_image(
        #     query,
        #     documents,
        #     args.topk,
        #     image_embed_key,
        #     ret
        # )

        args.query = None
        


if __name__ == "__main__":
    main()
   