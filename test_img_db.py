import argparse
import time
from pathlib import Path

from lazyllm.tools.rag.parsing_service.base import AddDocRequest, FileInfo
from lazyllm.tools.rag.utils import gen_docid

from parsing.build_document import ALGO_ID, build_document, is_image_file

DEFAULT_INPUT_DIR = Path("/home/mnt/cuishaoting/LazyRAG/test_doc")
DEFAULT_KB_ID = "debug_local"


def list_image_files(input_dir: Path, recursive: bool = False) -> list[str]:
    iterator = input_dir.rglob("*") if recursive else input_dir.iterdir()
    return [
        str(path.resolve())
        for path in sorted(iterator)
        if path.is_file() and is_image_file(path.name)
    ]


def build_add_doc_request(image_files: list[str], kb_id: str) -> tuple[AddDocRequest, list[str]]:
    doc_ids = [gen_docid(path) for path in image_files]
    file_infos = [
        FileInfo(
            file_path=path,
            doc_id=doc_id,
            metadata={"kb_id": kb_id},
        )
        for path, doc_id in zip(image_files, doc_ids)
    ]
    return AddDocRequest(algo_id=ALGO_ID, kb_id=kb_id, file_infos=file_infos), doc_ids


def wait_for_group_nodes(documents, kb_id: str, doc_ids: list[str], group: str, timeout: int, interval: float):
    deadline = time.time() + timeout
    target_doc_ids = set(doc_ids)

    while time.time() < deadline:
        nodes = documents._impl.store.get_nodes(group=group, kb_id=kb_id, doc_ids=doc_ids)
        found_doc_ids = {
            node.global_metadata.get("doc_id")
            for node in nodes
            if node.global_metadata.get("doc_id") in target_doc_ids
        }
        if found_doc_ids == target_doc_ids:
            return nodes
        time.sleep(interval)
    return None


def print_group_counts(documents, kb_id: str, doc_ids: list[str], groups: list[str]) -> None:
    print("\nstore_counts:")
    for group in groups:
        nodes = documents._impl.store.get_nodes(group=group, kb_id=kb_id, doc_ids=doc_ids)
        print(f"  {group}: {len(nodes)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--kb-id", default=DEFAULT_KB_ID)
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input dir not found: {input_dir}")

    image_files = list_image_files(input_dir, recursive=args.recursive)
    if not image_files:
        raise RuntimeError(f"No image files found under {input_dir}")

    documents = build_document()
    documents.start()

    request, doc_ids = build_add_doc_request(image_files, kb_id=args.kb_id)
    response = documents.manager.add_doc(request)

    print("submitted_task:", response)
    print("algo_id:", ALGO_ID)
    print("kb_id:", args.kb_id)
    print("input_dir:", input_dir)
    print("image_count:", len(image_files))
    print("doc_ids:")
    for doc_id in doc_ids:
        print(" ", doc_id)

    image_nodes = wait_for_group_nodes(
        documents=documents,
        kb_id=args.kb_id,
        doc_ids=doc_ids,
        group="image",
        timeout=args.timeout,
        interval=args.interval,
    )
    if image_nodes is None:
        print(f"\nTimeout: no complete image-group nodes detected within {args.timeout}s.")
        print("Task was submitted, but ingestion may still be running.")
        return

    print("\ningestion_status: success")
    print_group_counts(documents, kb_id=args.kb_id, doc_ids=doc_ids, groups=["__root__", "image", "block", "line"])

    print("\nimage_nodes:")
    for node in image_nodes:
        print(f"  uid={node.uid} image={getattr(node, 'image_path', '')}")


if __name__ == "__main__":
    main()


# 运行指令
#
# export PYTHONPATH=/home/mnt/cuishaoting/LazyRAG/algorithm/lazyllm:/home/mnt/cuishaoting/LazyRAG/algorithm
# export LAZYRAG_MODEL_CONFIG_PATH=/home/mnt/cuishaoting/LazyRAG/algorithm/chat/runtime_models.yaml
# export LAZYRAG_MILVUS_URI=http://milvus:19530 
# export LAZYRAG_OPENSEARCH_URI=https://opensearch:9200 
# python /home/mnt/cuishaoting/LazyRAG/test_img_db.py --input-dir /home/mnt/cuishaoting/LazyRAG/test_doc --kb-id debug_local
