import os
from pathlib import Path
from typing import List, Optional

from lazyllm.common import retry
from lazyllm.tools.rag.doc_node import ImageDocNode
from lazyllm.tools.rag.readers.readerBase import LazyLLMReaderBase, get_default_fs

RETRY_TIMES = 3


class LazyRAGImageReader(LazyLLMReaderBase):
    """Reader for standalone image files."""

    def __init__(self,
                 embed_key: Optional[str] = None,
                 embed_model=None,
                 return_trace: bool = True) -> None:
        super().__init__(return_trace=return_trace)
        self._embed_key = embed_key
        self._embed_model = embed_model

    @retry(stop_after_attempt=RETRY_TIMES)
    def _load_data(self, file: Path, fs: Optional['fsspec.AbstractFileSystem'] = None) -> List[ImageDocNode]:
        if not isinstance(file, Path):
            file = Path(file)

        suffix = file.suffix.lower()
        fs = fs or get_default_fs()
        abs_path = os.path.abspath(str(file))
        file_name = file.name

        metadata = {
            'source_path': abs_path,
            'file_name': file_name,
            'file_ext': suffix,
            'file_type': 'image',
            'is_pure_image': True,
        }
        embedding = {}

        # Optional fast path: precompute image embedding in reader and keep a
        # metadata marker for downstream code that receives plain DocNode data.
        if self._embed_key and self._embed_model:
            tmp_node = ImageDocNode(image_path=abs_path, metadata=metadata)
            tmp_node.do_embedding({self._embed_key: self._embed_model})
            if tmp_node.embedding and self._embed_key in tmp_node.embedding:
                embedding[self._embed_key] = tmp_node.embedding[self._embed_key]
                metadata['img_emb'] = {self._embed_key: tmp_node.embedding[self._embed_key]}

        node = ImageDocNode(
            image_path=abs_path,
            metadata=metadata,
            embedding=embedding,
        )
        return [node]


ImageReader = LazyRAGImageReader
