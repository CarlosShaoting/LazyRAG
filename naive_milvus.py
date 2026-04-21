from __future__ import annotations

import argparse
import os
import socket
import sys
import traceback
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parent
ALGORITHM_ROOT = PROJECT_ROOT / "algorithm"

DEFAULT_MILVUS_URI = os.getenv("LAZYRAG_MILVUS_TCP_URI", "tcp://127.0.0.1:19531")
DEFAULT_MILVUS_DB_NAME = os.getenv("LAZYRAG_MILVUS_DB_NAME", "add_img_emb")
DEFAULT_NAIVE_SERVICE_URL = os.getenv("LAZYRAG_NAIVE_SERVICE_URL", "http://10.119.16.66:9003")
DEFAULT_NAIVE_DATASET_NAME = os.getenv("LAZYRAG_NAIVE_DATASET_NAME")
DEFAULT_QUERY = os.getenv(
    "LAZYRAG_NAIVE_TEST_QUERY",
    "冠忠巴士集團 2024 年上半年收入增長 24.5%，但除稅前溢利卻由 19,646 千港元下降至 10,407 千港元。"
    "請分析造成此「增收不增利」現象的主要原因，並指出哪一業務分類的表現惡化最顯著",
)
DEFAULT_TIMEOUT = float(os.getenv("LAZYRAG_TEST_TIMEOUT", "15"))


def bootstrap_pythonpath() -> None:
    for path in (str(PROJECT_ROOT), str(ALGORITHM_ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Test Milvus TCP connectivity and run the naive RAG pipeline without modifying source code."
    )
    parser.add_argument("--milvus-uri", default=DEFAULT_MILVUS_URI, help="Milvus TCP URI.")
    parser.add_argument("--milvus-db-name", default=DEFAULT_MILVUS_DB_NAME, help="Milvus database name.")
    parser.add_argument("--milvus-token", default=os.getenv("LAZYRAG_MILVUS_TOKEN"), help="Milvus auth token.")
    parser.add_argument(
        "--service-url",
        default=DEFAULT_NAIVE_SERVICE_URL,
        help="Algorithm service base URL used by algorithm/chat/pipelines/naive.py.",
    )
    parser.add_argument(
        "--dataset-name",
        default=DEFAULT_NAIVE_DATASET_NAME,
        help="Remote dataset name for get_ppl_naive(). Defaults to --milvus-db-name if unset.",
    )
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Test query sent to the naive pipeline.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Network timeout in seconds.")
    parser.add_argument(
        "--describe-limit",
        type=int,
        default=3,
        help="How many collections to describe after connecting to Milvus.",
    )
    parser.add_argument(
        "--text-limit",
        type=int,
        default=800,
        help="How many characters of the answer text to print.",
    )
    parser.add_argument("--debug", action="store_true", help="Pass debug=True to the naive pipeline.")
    parser.add_argument("--require-sources", action="store_true", help="Fail if the pipeline returns no sources.")
    parser.add_argument("--skip-socket-check", action="store_true", help="Skip the algorithm service TCP check.")
    parser.add_argument("--skip-milvus-check", action="store_true", help="Skip the Milvus connectivity check.")
    parser.add_argument("--skip-naive-check", action="store_true", help="Skip the get_ppl_naive() call.")
    parser.add_argument("--verbose", action="store_true", help="Print full stack traces on failure.")
    return parser


def print_section(title: str) -> None:
    print(f"\n=== {title} ===", flush=True)


def format_exception(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def echo(*args: Any) -> None:
    print(*args, flush=True)


def resolve_dataset_name(args: argparse.Namespace) -> str:
    dataset_name = args.dataset_name or args.milvus_db_name
    if not dataset_name:
        raise ValueError("dataset_name is empty. Pass --dataset-name or --milvus-db-name.")
    return dataset_name


def build_naive_url(service_url: str, dataset_name: str) -> str:
    return f"{service_url.rstrip('/')},{dataset_name}"


def check_service_socket(service_url: str, timeout: float) -> tuple[str, int]:
    parsed = urlparse(service_url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError(f"Invalid service URL: {service_url!r}")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    with socket.create_connection((parsed.hostname, port), timeout=timeout):
        pass

    return parsed.hostname, port


def check_milvus(uri: str, db_name: str, token: str | None, describe_limit: int) -> list[str]:
    from pymilvus import MilvusClient

    client = MilvusClient(uri=uri, token=token) if token else MilvusClient(uri=uri)

    databases = client.list_databases()
    echo(f"Milvus URI: {uri}")
    echo(f"Databases: {databases}")

    if db_name not in databases:
        raise RuntimeError(f"Milvus database {db_name!r} does not exist. Available databases: {databases}")

    client.use_database(db_name=db_name)
    collections = client.list_collections()
    echo(f"Current DB: {db_name}")
    echo(f"Collections: {collections}")

    for collection_name in collections[: max(0, describe_limit)]:
        desc = client.describe_collection(collection_name=collection_name)
        fields = [field.get("name") for field in desc.get("fields", [])]
        echo(f"Collection {collection_name}: fields={fields}")

    return collections


def build_query_payload(query: str, debug: bool) -> dict[str, Any]:
    return {
        "filters": {},
        "query": query,
        "files": [],
        "image_files": [],
        "history": [],
        "debug": debug,
        "priority": 0,
    }


def summarize_result(result: Any, text_limit: int) -> None:
    if not isinstance(result, dict):
        echo(f"Result type: {type(result).__name__}")
        echo(result)
        return

    echo(f"Result keys: {sorted(result.keys())}")

    sources = result.get("sources")
    if isinstance(sources, list):
        echo(f"Source count: {len(sources)}")
        for index, source in enumerate(sources[:5], start=1):
            echo(f"  [{index}] {source}")
        if len(sources) > 5:
            echo(f"  ... {len(sources) - 5} more")
    else:
        echo(f"Sources: {sources}")

    text = result.get("text")
    if text is None:
        echo("Text: None")
        return

    text = str(text).strip()
    if text_limit > 0 and len(text) > text_limit:
        text = text[:text_limit] + "..."

    echo("\nAnswer preview:")
    echo(text)


def run_naive_pipeline(service_url: str, dataset_name: str, query: str, debug: bool, text_limit: int) -> Any:
    bootstrap_pythonpath()

    from chat.pipelines.naive import get_ppl_naive

    naive_url = build_naive_url(service_url, dataset_name)
    payload = build_query_payload(query=query, debug=debug)

    echo(f"Naive URL: {naive_url}")
    echo(f"Query: {query}")

    rag_ppl = get_ppl_naive(naive_url, stream=False)
    result = rag_ppl(payload)
    summarize_result(result, text_limit=text_limit)
    return result


def validate_naive_result(result: Any, require_sources: bool) -> None:
    if not isinstance(result, dict):
        raise RuntimeError(f"Unexpected pipeline result type: {type(result).__name__}")

    text = str(result.get("text") or "").strip()
    if not text:
        raise RuntimeError("Naive pipeline returned empty text.")

    if require_sources and not result.get("sources"):
        raise RuntimeError("Naive pipeline returned no sources.")


def main() -> int:
    args = build_parser().parse_args()
    dataset_name = resolve_dataset_name(args)

    echo("Project root:", PROJECT_ROOT)
    echo("Algorithm root:", ALGORITHM_ROOT)
    echo("Milvus DB name:", args.milvus_db_name)
    echo("Naive dataset name:", dataset_name)

    try:
        if not args.skip_socket_check:
            print_section("Algorithm Service Socket Check")
            host, port = check_service_socket(args.service_url, args.timeout)
            echo(f"Algorithm service is reachable: {host}:{port}")

        if not args.skip_milvus_check:
            print_section("Milvus Check")
            check_milvus(
                uri=args.milvus_uri,
                db_name=args.milvus_db_name,
                token=args.milvus_token,
                describe_limit=args.describe_limit,
            )
            echo("Milvus connectivity check passed.")

        if not args.skip_naive_check:
            print_section("Naive Pipeline Check")
            result = run_naive_pipeline(
                service_url=args.service_url,
                dataset_name=dataset_name,
                query=args.query,
                debug=args.debug,
                text_limit=args.text_limit,
            )
            validate_naive_result(result, require_sources=args.require_sources)
            echo("Naive pipeline check passed.")

    except Exception as exc:
        echo("\n[FAIL]", format_exception(exc))
        if args.verbose:
            traceback.print_exc()
        return 1

    echo("\n[OK] All enabled checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
