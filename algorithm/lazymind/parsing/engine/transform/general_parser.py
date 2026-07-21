import os
import re
import copy
from typing import List
from urllib.parse import urlparse

from lazyllm import pipeline, LOG, globals as lazyllm_globals
from lazyllm.tools.rag import NodeTransform
from lazyllm.tools.rag.doc_node import DocNode

from lazymind.config import config as _cfg
from lazymind.parsing.engine.utils import spawn_child_doc_node


IMAGE_PREFIX = _cfg['rag_image_path_prefix']
IMAGE_PATTERN = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
_TOKEN_LIMIT_PATTERN = re.compile(r'^([1-9][0-9]*)([KM])?$')
_EMBED_CHUNK_LENGTH_BY_MAX_INPUT_TOKENS = {
    512: 384,
    1024: 896,
    2048: 1920,
}


def _parse_token_limit(value) -> int | None:
    if isinstance(value, int) and value > 0:
        return value
    if not isinstance(value, str):
        return None
    match = _TOKEN_LIMIT_PATTERN.fullmatch(value.strip().upper())
    if not match:
        return None
    amount = int(match.group(1))
    suffix = match.group(2)
    return amount * {'K': 1_000, 'M': 1_000_000}.get(suffix, 1)


def _runtime_embed_max_input_tokens() -> int | None:
    try:
        configs = lazyllm_globals['config'].get('dynamic_model_configs')
    except AssertionError:
        return None
    if not isinstance(configs, dict):
        return None
    embed_main = configs.get('embed_main')
    if not isinstance(embed_main, dict):
        return None
    embed_config = embed_main.get('embed')
    if not isinstance(embed_config, dict):
        return None
    return _parse_token_limit(embed_config.get('max_input_tokens'))


def is_url(s):
    try:
        res = urlparse(s)
        return bool(res.scheme and (res.netloc or res.scheme == 'file'))
    except Exception as e:
        LOG.error(f'is_url error: {e}')
        return False


class GeneralParser(NodeTransform):

    def __init__(self, max_length: int = 2048, split_by: str = '\n', **kwargs):
        super().__init__(**kwargs)
        assert max_length > 0, 'max_length must be greater than 0'
        assert isinstance(split_by, str) and len(split_by) > 0, 'split_by must be a non-empty string'
        self._max_length = max_length
        self._split_by = split_by
        self._len_split = len(split_by)

    def sig_fields(self) -> dict:
        return {'max_length': self._max_length, 'split_by': self._split_by}

    def _image_path_transform(self, text: str) -> str:
        def _replace(match: re.Match) -> str:
            alt_text, url = match.groups()
            if not is_url(url) and not url.startswith('lazyllm'):
                url = os.path.join(IMAGE_PREFIX, url)
            return f'![{alt_text}]({url})'
        return IMAGE_PATTERN.sub(_replace, text)

    def _split(self, text: str, max_length: int | None = None) -> List[str]:
        if not text:
            return []
        max_length = max_length or self._max_length
        if len(text) <= max_length:
            return [text]
        result_chunks = []
        parts = text.split(self._split_by)

        current_chunk = []
        current_len = 0
        for part in parts:
            part_len = len(part)
            if part_len > max_length:
                if current_chunk:
                    result_chunks.append(self._split_by.join(current_chunk))
                    current_chunk = []
                    current_len = 0
                for i in range(0, part_len, max_length):
                    result_chunks.append(part[i:i + max_length])
                continue
            add_sep = self._len_split if current_chunk else 0
            if current_len + part_len + add_sep > max_length:
                if current_chunk:
                    result_chunks.append(self._split_by.join(current_chunk))
                current_chunk = [part]
                current_len = part_len
            else:
                if current_chunk:
                    current_len += self._len_split
                current_chunk.append(part)
                current_len += part_len
        if current_chunk:
            result_chunks.append(self._split_by.join(current_chunk))
        return result_chunks

    def forward(self, document: DocNode, **kwargs) -> List[DocNode]:
        metadata = document.metadata
        global_metadata = document.global_metadata
        max_input_tokens = _runtime_embed_max_input_tokens()
        max_length = self._max_length
        if max_input_tokens is not None:
            max_length = min(
                max_length,
                _EMBED_CHUNK_LENGTH_BY_MAX_INPUT_TOKENS.get(max_input_tokens, max_length),
            )

        ppl = pipeline(self._image_path_transform, lambda text: self._split(text, max_length=max_length))
        content = ppl(document.text or '')

        return [
            spawn_child_doc_node(
                document,
                text=chunk,
                metadata=copy.deepcopy(metadata),
                global_metadata=copy.deepcopy(global_metadata),
            ) for chunk in content]
