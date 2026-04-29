import argparse
import json
import os
import sqlite3
from pathlib import Path

from pymilvus import MilvusClient


DEFAULT_SEGMENT_DB = Path("/home/mnt/cuishaoting/LazyRAG/lazyllm_milvus_test_segments.db")
DEFAULT_MILVUS_DB = Path("/home/mnt/cuishaoting/LazyRAG/milvus_test.db")


def inspect_segment_db(db_path: Path, limit: int) -> None:
    print("\n=== Segment DB ===")
    print(f"path: {db_path}")
    print(f"exists: {db_path.exists()}")
    if not db_path.exists():
        return

    print(f"size: {db_path.stat().st_size} bytes")
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("select name from sqlite_master where type='table' order by name")
        tables = [row[0] for row in cur.fetchall()]
        print("tables:", tables)

        for table in tables:
            print(f"\n-- table: {table} --")
            cur.execute(f'PRAGMA table_info("{table}")')
            columns = [row[1] for row in cur.fetchall()]
            print("columns:", columns)

            cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            print("rows:", cur.fetchone()[0])

            sample_sql = (
                f'SELECT uid, doc_id, "group", content, image_keys, global_meta '
                f'FROM "{table}" LIMIT ?'
            )
            cur.execute(sample_sql, (limit,))
            rows = cur.fetchall()
            if not rows:
                print("sample: []")
                continue

            print("sample:")
            for uid, doc_id, group_name, content, image_keys, global_meta in rows:
                item = {
                    "uid": uid,
                    "doc_id": doc_id,
                    "group": group_name,
                    "content_preview": (content[:3] + "...") if content and len(content) > 3 else content,
                    "image_keys": _safe_json_loads(image_keys),
                    "global_meta": _safe_json_loads(global_meta),
                }
                print(json.dumps(item, ensure_ascii=False, indent=2))
    finally:
        conn.close()


def inspect_milvus_db(db_path: Path, limit: int) -> None:
    print("\n=== Milvus DB ===")
    print(f"path: {db_path}")
    print(f"exists: {db_path.exists()}")
    if not db_path.exists():
        return

    print(f"size: {db_path.stat().st_size} bytes")
    client = MilvusClient(uri=str(db_path))
    try:
        collections = client.list_collections()
        print("collections:", collections)

        for collection in collections:
            print(f"\n-- collection: {collection} --")
            schema = client.describe_collection(collection)
            print("schema:")
            print(json.dumps(schema, ensure_ascii=False, indent=2, default=str))

            rows = client.query(collection_name=collection, filter="", limit=limit)
            print(f"sample_rows: {len(rows)}")
            for row in rows:
                print(json.dumps(_summarize_milvus_row(row), ensure_ascii=False, indent=2, default=str))
    finally:
        client.close()


def _safe_json_loads(value):
    if value in (None, ""):
        return value
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def _summarize_milvus_row(row: dict) -> dict:
    summary = {}
    for key, value in row.items():
        if isinstance(value, list) and value and isinstance(value[0], (int, float)):
            summary[key] = {
                "vector_dim": len(value),
                "preview": value[:8],
            }
        else:
            summary[key] = value
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect local LazyRAG segment DB and Milvus DB contents.")
    parser.add_argument("--segment-db", default=str(DEFAULT_SEGMENT_DB))
    parser.add_argument("--milvus-db", default=str(DEFAULT_MILVUS_DB))
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    # segment_db = Path(args.segment_db).expanduser().resolve()
    milvus_db = Path(args.milvus_db).expanduser().resolve()

    print("cwd:", os.getcwd())
    # inspect_segment_db(segment_db, args.limit)
    inspect_milvus_db(milvus_db, args.limit)


if __name__ == "__main__":
    main()
