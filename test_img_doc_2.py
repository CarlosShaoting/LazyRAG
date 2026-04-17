import argparse
from pathlib import Path

from lazyllm.tools.rag import Document, Retriever
from chat.pipelines.builders.get_models import get_automodel

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

DEFAULT_INPUT_DIR = Path("/home/mnt/cuishaoting/LazyRAG/test_doc")


def list_images(input_dir: Path):
    return [
        str(p.resolve())
        for p in sorted(input_dir.iterdir())
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    ]


def build_documents(image_files):
    embed_model = get_automodel("siglip")

    return Document(
        embed={"siglip": embed_model},
        doc_files=image_files,
        manager=False,
        store_conf={"type": "map"},
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--topk", type=int, default=3)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)

    images = list_images(input_dir)
    if not images:
        raise RuntimeError("No images found")

    docs = build_documents(images)

    retriever = Retriever(
        doc=docs,
        group_name="image",
        similarity="cosine",
        topk=args.topk,
        embed_keys=["siglip"],
    )

    nodes = retriever(args.query)

    print("\nquery:", args.query)
    print("top results:\n")

    for n in nodes:
        print(f"score={n.similarity_score:.4f} image={n.image_path}")


if __name__ == "__main__":
    main()