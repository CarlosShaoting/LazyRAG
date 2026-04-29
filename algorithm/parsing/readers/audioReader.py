import base64
import mimetypes
from pathlib import Path
from typing import List, Optional

from lazyllm.thirdparty import fsspec
from lazyllm.tools.rag.doc_node import DocNode
from lazyllm.tools.rag.readers.readerBase import LazyLLMReaderBase


class AudioReader(LazyLLMReaderBase):
    __lazyllm_registry_disable__ = True

    def __init__(self, model, return_trace: bool = True) -> None:
        super().__init__(return_trace=return_trace)
        if model is None:
            raise ValueError('`model` is required for AudioReader')
        self._model = model

    def _load_data(self, file: Path, fs: Optional['fsspec.AbstractFileSystem'] = None) -> List[DocNode]:
        if fs is not None:
            raise NotImplementedError('AudioReader currently supports local audio paths only')

        if not isinstance(file, Path):
            file = Path(file)

        mime_type, _ = mimetypes.guess_type(file)
        if not mime_type or not mime_type.startswith('audio/'):
            raise ValueError(f'Unsupported audio file type: {file}')

        with open(file, 'rb') as f:
            audio_b64 = base64.b64encode(f.read()).decode('utf-8')

        result = self._model({
            'inputs': '',
            'audio': f'data:{mime_type};base64,{audio_b64}'
        })
        transcript = result['text'] if isinstance(result, dict) else result
        return [DocNode(text=transcript)]


__all__ = ['AudioReader']
