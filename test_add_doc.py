import os
import time

from parsing.build_document import build_document, ALGO_ID
from lazyllm.tools.rag.parsing_service.base import FileInfo, AddDocRequest
from lazyllm.tools.rag.utils import gen_docid

PDF_PATH = "/home/mnt/cuishaoting/test_mineru.pdf"

def main():
    docs = build_document()
    docs.start()

    time.sleep(3)

    doc_id = gen_docid(PDF_PATH)
    req = AddDocRequest(
        algo_id=ALGO_ID,
        file_infos=[
            FileInfo(
                file_path=PDF_PATH,
                doc_id=doc_id,
                metadata={"kb_id": "debug_local"}
            )
        ]
    )

    # 直接走 manager，也就是 DocumentProcessor
    resp = docs.manager.add_doc(req)
    print(resp)

if __name__ == "__main__":
    main()


# 运行指令

# export PYTHONPATH=/home/mnt/cuishaoting/LazyRAG:/home/mnt/cuishaoting/LazyRAG/algorithm
# export LAZYRAG_OCR_SERVER_TYPE=mineru
# export LAZYRAG_OCR_SERVER_URL=http://10.119.23.139:20234
# python /home/mnt/cuishaoting/LazyRAG/test_add_doc.py