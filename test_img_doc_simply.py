from pathlib import Path
from lazyllm.tools.rag import Document, Retriever
from chat.pipelines.builders.get_models import get_automodel
from parsing.image_reader import ImageReader
from chat.utils.load_config import get_retrieval_settings

IMAGE_DIR = Path("/home/mnt/cuishaoting/LazyRAG/test_doc")
IMAGE_SUFFIX = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

def main(query: str):
    # 1. 收集图片
    image_files = [
        str(p.resolve())
        for p in IMAGE_DIR.iterdir()
        if p.suffix.lower() in IMAGE_SUFFIX
    ]

    if not image_files:
        raise RuntimeError("No images found")

    # 2. embed key
    settings = get_retrieval_settings()
    embed_key = "siglip" if "siglip" in settings.embed_keys else settings.embed_keys[-1]

    embed_model = get_automodel(embed_key)

    # 3. build document
    docs = Document(
        embed={embed_key: embed_model},
        doc_files=image_files,
        manager=False,
        store_conf={"type": "map"},
    )

    reader = ImageReader(embed_key=embed_key, embed_model=embed_model)
    for ext in IMAGE_SUFFIX:
        docs.add_reader(f"*{ext}", reader)

    docs.activate_group("image", embed_keys=[embed_key])

    # 4. retriever
    retriever = Retriever(
        doc=docs,
        group_name="image",
        similarity="cosine",
        topk=3,
        embed_keys=[embed_key],
    )

    nodes = retriever(query)

    if not nodes:
        print("No result")
        return

    best = max(nodes, key=lambda n: n.similarity_score or -1)

    print("\nQUERY:", query)
    print("\nTOP RESULTS:")

    for n in nodes:
        print(f"{n.similarity_score:.4f} -> {n.image_path}")

    print("\nBEST:")
    print(best.image_path, best.similarity_score)


if __name__ == "__main__":
    import sys
    main(" ".join(sys.argv[1:]) or input("query: ").strip())