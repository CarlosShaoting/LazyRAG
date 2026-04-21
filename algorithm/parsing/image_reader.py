import hashlib
import os
import tempfile
from pathlib import Path
from typing import List, Optional

from lazyllm.common import retry
from lazyllm.thirdparty import PIL
from lazyllm.tools.rag.doc_node import ImageDocNode
from lazyllm.tools.rag.readers.readerBase import LazyLLMReaderBase, get_default_fs

RETRY_TIMES = 3
NORMALIZED_IMAGE_DIR = Path(tempfile.gettempdir()) / 'lazyrag_normalized_images'


class LazyRAGImageReader(LazyLLMReaderBase):
    """Reader for standalone image files."""

    def __init__(self,
                 embed_key: Optional[str] = None,
                 embed_model=None,
                 return_trace: bool = True) -> None:
        super().__init__(return_trace=return_trace)
        self._embed_key = embed_key
        self._embed_model = embed_model

    def _normalize_image_file(self, image_path: str) -> str:
        src = Path(image_path).resolve()
        NORMALIZED_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(str(src).encode('utf-8')).hexdigest()[:16]
        dst = NORMALIZED_IMAGE_DIR / f'{src.stem}_{digest}.jpg'

        if dst.exists():
            return str(dst)

        with PIL.Image.open(src) as img:
            # Use only the first frame so animated formats become a stable single image.
            if getattr(img, 'n_frames', 1) > 1:
                img.seek(0)

            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                rgba = img.convert('RGBA')
                background = PIL.Image.new('RGB', rgba.size, (255, 255, 255))
                background.paste(rgba, mask=rgba.getchannel('A'))
                rgb = background
            else:
                rgb = img.convert('RGB')

            rgb.save(dst, format='JPEG', quality=95)
        return str(dst)

    @retry(stop_after_attempt=RETRY_TIMES)
    def _load_data(self, file: Path, fs: Optional['fsspec.AbstractFileSystem'] = None) -> List[ImageDocNode]:
        if not isinstance(file, Path):
            file = Path(file)

        suffix = file.suffix.lower()
        fs = fs or get_default_fs()
        abs_path = os.path.abspath(str(file))
        normalized_path = self._normalize_image_file(abs_path)
        file_name = file.name

        metadata = {
            'source_path': abs_path,
            'normalized_source_path': normalized_path,
            'file_name': file_name,
            'file_ext': suffix,
            'file_type': 'image',
            'is_pure_image': True,
        }
        embedding = {}

        # Optional fast path: precompute image embedding in reader and keep a
        # metadata marker for downstream code that receives plain DocNode data.
        if self._embed_key and self._embed_model:
            tmp_node = ImageDocNode(image_path=normalized_path, metadata=metadata)
            tmp_node.do_embedding({self._embed_key: self._embed_model})
            if tmp_node.embedding and self._embed_key in tmp_node.embedding:
                embedding[self._embed_key] = tmp_node.embedding[self._embed_key]
                metadata['img_emb'] = {self._embed_key: tmp_node.embedding[self._embed_key]}

        node = ImageDocNode(
            image_path=normalized_path,
            metadata=metadata,
            embedding=embedding,
        )
        return [node]


ImageReader = LazyRAGImageReader
