# LazyRAG Startup, Ingestion, And Retrieval Notes

## 1. Core Concepts

- `build_document()` defines the document-processing rules:
  - which readers handle which file types
  - which node groups exist
  - which embeddings are used
  - which stores are used
- `docs.start()` does **not** mean "scan a folder and ingest everything now".
- `python algorithm/parsing/parsing.py` does:
  - wait for `DocumentProcessor`
  - build the `Document`
  - start the local algo service
  - register `algo_id=general_algo` into `DocumentProcessor`

So:

- `build_document()` = define rules
- `parsing.py` = register and start the parsing algorithm service
- actual ingestion happens later when `/doc/add` is called

## 2. Service Mode vs Local Test Mode

### Service mode

Used by current `LazyRAG` parsing service:

- `Document(dataset_path=None, manager=DocumentProcessor(...), ...)`
- files are uploaded or submitted later through `DocumentProcessor`
- ingestion is triggered by `POST /doc/add`

### Local test mode

Used when you just want to verify reader / parsing / retrieval locally:

```python
docs = Document(
    dataset_path=MyData,
    embed=embed,
    manager=False,
    store_conf={'type': 'map'},
)
```

This can skip:

- `DocumentProcessor`
- `DocumentProcessorWorker`
- PostgreSQL

But may still require:

- embedding model service
- `ffmpeg`
- ASR service if audio reader depends on one

## 3. What Services Are Needed

For the full `parsing.py` service chain, usually these are needed:

- PostgreSQL
  - used by `DocumentProcessor` / worker task queue
- Milvus
  - vector storage
- OpenSearch
  - segment / keyword / text retrieval storage
- DocumentProcessor
- DocumentProcessorWorker
  - if not embedded into processor
- embedding model service(s)
  - depends on `runtime_models.yaml` / `runtime_models.inner.yaml`
- OCR service
  - only if PDF OCR is enabled
- ASR service
  - only if audio/video-audio reader depends on it
- local `ffmpeg`
  - required by `VideoFrameReader`

## 4. Important Environment Variables

Common required ones:

- `LAZYRAG_DATABASE_URL`
- `LAZYRAG_MILVUS_URI`
- `LAZYRAG_OPENSEARCH_URI`
- `LAZYRAG_DOCUMENT_PROCESSOR_URL`
- `LAZYRAG_ALGO_SERVER_PORT`
- `LAZYRAG_MODEL_CONFIG_PATH`

Optional / feature-specific:

- `LAZYRAG_OCR_SERVER_TYPE`
- `LAZYRAG_OCR_SERVER_URL`
- `LAZYRAG_MINERU_UPLOAD_MODE`

## 5. Suggested Startup Order

1. Start PostgreSQL
2. Start Milvus
3. Start OpenSearch
4. Start `DocumentProcessor`
5. Start `DocumentProcessorWorker`
6. Ensure embedding models are available
7. Ensure OCR / ASR services are available if needed
8. Ensure `ffmpeg` is installed
9. Start parsing algorithm:

```bash
python /home/mnt/cuishaoting/LazyRAG/algorithm/parsing/parsing.py
```

## 6. What `parsing.py` Starts

Running:

```bash
python /home/mnt/cuishaoting/LazyRAG/algorithm/parsing/parsing.py
```

will:

- wait for `DocumentProcessor /health`
- run `build_document()`
- run `docs.start()`
- expose a local algo service
- register `general_algo` into `DocumentProcessor`

It does **not** automatically ingest a directory.

## 7. How Files Are Actually Ingested

Files are ingested by calling:

```http
POST /doc/add
```

against `DocumentProcessor`.

Typical flow:

1. file path or uploaded file is prepared
2. request is sent to `DocumentProcessor`
3. processor chooses the registered algorithm by `algo_id`
4. files are matched to readers by suffix
5. readers produce nodes
6. transforms / embeddings run
7. data is stored

In other words:

- files -> reader
- reader -> nodes
- nodes -> transform / embed
- transform / embed -> stores

## 8. `/doc/add` Main Request Shape

Main model is `AddDocRequest`.

Minimal practical payload:

```json
{
  "algo_id": "general_algo",
  "file_infos": [
    {
      "file_path": "/abs/path/to/file.mp4",
      "doc_id": "doc-001",
      "metadata": {
        "kb_id": "default"
      }
    }
  ]
}
```

Important fields:

- `algo_id`
- `file_infos`

Each `file_infos` item usually includes:

- `file_path`
- `doc_id`
- `metadata`

The file path must be accessible by the processor / worker machine.

## 9. File Upload Without Frontend

Frontend is not required for testing ingestion.

If `/doc/add` works, you can test directly by:

- `curl`
- Python script
- Postman

Frontend is only one client of this API.

## 10. Current Reader Responsibilities

Recommended responsibility split:

- `ImageEmbReader`
  - create `ImageDocNode`
- `VideoFrameReader`
  - extract frames and create multiple `ImageDocNode`
- `AudioReader` / `VideoAudioReader`
  - create normal `DocNode`

If embedding is not computed inside readers, then embedding should be provided by:

```python
Document(embed=embed, ...)
```

not by reader constructor.

## 11. Group Mapping

Default mapping:

- `DocNode` -> `lazyllm_root`
- `ImageDocNode` -> `image`

Implications:

- images and video frames usually belong to `image`
- audio transcript text belongs to `lazyllm_root`

## 12. Retrieval Strategy

Typical split:

### Image / video-frame retrieval

Use vector retrieval on `image` group:

```python
Retriever(
    docs,
    group_name='image',
    similarity='cosine',
    embed_keys=['siglip'],
)
```

### Text / transcript retrieval

If using BM25 on root text:

```python
Retriever(
    docs,
    group_name='lazyllm_root',
    similarity='bm25',
)
```

Notes:

- BM25 does not need embedding
- root group is active by default
- if root only uses BM25, usually no need to activate root with embedding keys

## 13. Local Verification Rule Of Thumb

If local directory-based `Document(dataset_path=..., manager=False)` works, then service-mode `/doc/add` is usually close to working too.

Still verify:

- processor can access the file paths
- service environment has `ffmpeg`
- service environment has model / OCR / ASR dependencies

## 14. Recommended Debug Order

1. First verify local `Document(dataset_path=..., manager=False)`
2. Then verify `build_document()` and `parsing.py`
3. Then test `POST /doc/add`
4. Then connect frontend if needed

This reduces variables and makes reader bugs easier to isolate.
