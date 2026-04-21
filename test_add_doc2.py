import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ALGORITHM_DIR = ROOT / "algorithm"
for path in (ROOT, ALGORITHM_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lazyllm.tools.rag.parsing_service.base import AddDocRequest, FileInfo
from lazyllm.tools.rag.utils import gen_docid
from parsing.build_document import ALGO_ID, build_document


DEFAULT_INPUT = ROOT / "test_doc"
DEFAULT_KB_ID = "debug_doc_ingest"
SUPPORTED_SUFFIXES = {
    ".pdf",
    ".txt",
    ".md",
    ".docx",
    ".pptx",
    ".xlsx",
    ".xls",
    ".csv",
    ".json",
    ".html",
    ".htm",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".webp",
    ".tiff",
    ".tif",
}


def iter_input_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        paths = [input_path]
    else:
        paths = [p for p in sorted(input_path.rglob("*")) if p.is_file()]
    return [p for p in paths if p.suffix.lower() in SUPPORTED_SUFFIXES]


def main() -> None:
    parser = argparse.ArgumentParser(description="Test full document ingestion for LazyRAG.")
    parser.add_argument("input", nargs="?", default=str(DEFAULT_INPUT),
                        help="File or directory to ingest.")
    parser.add_argument("--kb-id", default=DEFAULT_KB_ID, help="Knowledge base id.")
    parser.add_argument("--startup-wait", type=float, default=3.0,
                        help="Seconds to wait after docs.start().")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    files = iter_input_files(input_path)
    if not files:
        raise RuntimeError(f"No supported files found under {input_path}")

    docs = build_document()
    docs.start()
    time.sleep(args.startup_wait)

    file_infos = []
    for file_path in files:
        doc_id = gen_docid(str(file_path))
        file_infos.append(
            FileInfo(
                file_path=str(file_path),
                doc_id=doc_id,
                metadata={"kb_id": args.kb_id},
            )
        )

    req = AddDocRequest(
        algo_id=ALGO_ID,
        kb_id=args.kb_id,
        file_infos=file_infos,
    )
    resp = docs.manager.add_doc(req)

    print(f"input: {input_path}")
    print(f"kb_id: {args.kb_id}")
    print(f"file_count: {len(file_infos)}")
    print("submitted files:")
    for item in file_infos:
        print(f"  {item.doc_id}  {item.file_path}")
    print("response:")
    print(resp)


if __name__ == "__main__":
    main()


# Run example:
#
export PYTHONPATH=/home/mnt/cuishaoting/LazyLLM:/home/mnt/cuishaoting/LazyRAG:/home/mnt/cuishaoting/LazyRAG/algorithm
export LAZYRAG_MODEL_CONFIG_PATH=/home/mnt/cuishaoting/LazyRAG/algorithm/chat/runtime_models.inner.yaml
export LAZYRAG_MILVUS_URI=http://127.0.0.1:19530
export LAZYRAG_OPENSEARCH_URI=https://127.0.0.1:9200
export LAZYRAG_OPENSEARCH_USER=admin
export LAZYRAG_OPENSEARCH_PASSWORD=LazyRAG_OpenSearch123!
export LAZYRAG_DOCUMENT_PROCESSOR_URL=http://127.0.0.1:8000
export LAZYRAG_OCR_SERVER_TYPE=mineru
export LAZYRAG_OCR_SERVER_URL=http://10.119.23.139:20234

# Optional: start your custom image embedding service if runtime_models.inner.yaml points to it.
# python /home/mnt/cuishaoting/LazyRAG/emb_server2.py

python /home/mnt/cuishaoting/LazyRAG/test_doc.py /home/mnt/cuishaoting/LazyRAG/test_doc --kb-id debug_doc_ingest