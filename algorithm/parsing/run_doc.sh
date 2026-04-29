export PYTHONPATH=/home/mnt/cuishaoting/LazyRAG/algorithm/lazyllm:/home/mnt/cuishaoting/LazyRAG/algorithm
export LAZYRAG_DOCUMENT_PROCESSOR_URL=http://127.0.0.1:8000
export LAZYRAG_MILVUS_URI=http://127.0.0.1:19530
export LAZYRAG_OPENSEARCH_URI=https://127.0.0.1:9200
export LAZYRAG_OPENSEARCH_USER=admin
export LAZYRAG_OPENSEARCH_PASSWORD=LazyRAG_OpenSearch123!
export LAZYRAG_USE_INNER_MODEL=true
export LAZYRAG_MODEL_CONFIG_PATH=/home/mnt/cuishaoting/LazyRAG/algorithm/chat/runtime_models.inner.yaml
export TMPDIR=/tmp/cst_test_rag

python /home/mnt/cuishaoting/LazyRAG/algorithm/parsing/test_doc.py