from pymilvus import MilvusClient

URI = "tcp://127.0.0.1:19531"   # 改成你的端口
TOKEN = None                     # 如果开了认证，改成 "root:Milvus"
# URI = "/tmp/vec_seg_1.db"
client = MilvusClient(uri=URI, token=TOKEN) if TOKEN else MilvusClient(uri=URI)

# 1. 列出所有数据库
dbs = client.list_databases()
print("Databases:", dbs)

for db in dbs:
    print(f"\n===== DB: {db} =====")
    client.use_database(db_name=db)

    # 2. 列出当前 DB 下所有 collections
    cols = client.list_collections()
    print("Collections:", cols)

    for col in cols:
        print(f"\n--- Collection: {col} ---")

        # 3. 看 schema / 字段
        desc = client.describe_collection(collection_name=col)
        print("Schema:")
        for f in desc.get("fields", []):
            print(" ", f)

        # 4. 只取非向量字段，避免把大向量全打出来
        output_fields = []
        for f in desc.get("fields", []):
            t = str(f.get("type", ""))
            name = f.get("name")

            output_fields.append(name)

        print("Output fields for preview:", output_fields)

        # 5. 打印几条样例数据
        try:
            rows = client.query(
                collection_name=col,
                filter="RANDOM_SAMPLE(0.1)",
                output_fields=output_fields,
                limit=3,
            )
            print("Sample rows:")
            for r in rows:
                n = {}
                for k in r:
                    if k == 'embedding_siglip':
                        n['embedding_siglip'] = r['embedding_siglip'][:3]
                    else:
                        n[k] = r[k]
                print(n)
        except Exception as e:
            print("Query sample failed:", e)

# import argparse
# import os
# from pathlib import Path

# from pymilvus import MilvusClient


# def clear_milvus_db(uri: str, db_name: str, token: str | None = None) -> None:
#     client = MilvusClient(uri=uri, token=token) if token else MilvusClient(uri=uri)

#     print(f"Milvus URI: {uri}")
#     print("Databases:", client.list_databases())

#     client.using_database(db_name)
#     collections = client.list_collections()
#     print(f"Current DB: {db_name}")
#     print("Collections to drop:", collections)

#     for col in collections:
#         print(f"Dropping collection: {col}")
#         client.drop_collection(collection_name=col)

#     print(f"Milvus DB `{db_name}` cleared.")


# def clear_segment_db(segment_db: str | None) -> None:
#     if not segment_db:
#         return

#     path = Path(segment_db).expanduser().resolve()
#     if path.exists():
#         print(f"Removing segment DB: {path}")
#         path.unlink()
#     else:
#         print(f"Segment DB not found, skip: {path}")


# def main() -> None:
#     parser = argparse.ArgumentParser(description="Clear LazyRAG Milvus DB and optional local segment sqlite DB.")
#     parser.add_argument("--uri", default="tcp://127.0.0.1:19531")
#     parser.add_argument("--db-name", default="lazyllm")
#     parser.add_argument("--token", default=None)
#     parser.add_argument("--segment-db", default="/tmp/cst-test-lazyrag/segments.db")
#     parser.add_argument("--skip-segment-db", action="store_true")
#     args = parser.parse_args()

#     clear_milvus_db(uri=args.uri, db_name=args.db_name, token=args.token)

#     if not args.skip_segment_db:
#         clear_segment_db(args.segment_db)

#     print("Done.")


# if __name__ == "__main__":
#     main()


# import sqlite3

# conn = sqlite3.connect("/home/mnt/cuishaoting/tmp/vec_seg.db")
# cur = conn.cursor()

# cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
# print(cur.fetchall())