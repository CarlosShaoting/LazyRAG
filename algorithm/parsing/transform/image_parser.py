import os
from typing import Iterable, List, Optional
from urllib.parse import urlparse

from lazyllm import LOG, ModuleBase
from lazyllm.tools.rag import DocNode
from chat.pipelines.builders.get_models import get_automodel


IMAGE_PREFIX = os.getenv('RAG_IMAGE_PATH_PREFIX', '/mnt/lustre/share_data/mineru/images/')
IMAGE_NODE_TYPES = {'image', 'img', 'picture', 'figure'}
IMAGE_EMBED_KEY = 'embed_img_text'


def is_url(s: str) -> bool:
    try:
        res = urlparse(s)
        return bool(res.scheme and (res.netloc or res.scheme == 'file'))
    except Exception as exc:
        LOG.error(f'is_url error: {exc}')
        return False


class ImageParser(ModuleBase):
    def __init__(
        self,
        image_prefix: str = IMAGE_PREFIX,
        image_types: Optional[Iterable[str]] = None,
        keep_original_text: bool = True,
        description_key: str = 'image_description',
        markdown_key: str = 'image_markdown',
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._image_prefix = image_prefix
        self._image_types = {str(t).lower() for t in (image_types or IMAGE_NODE_TYPES)}
        self._keep_original_text = keep_original_text
        self._description_key = description_key
        self._markdown_key = markdown_key
        self._emb_model = self._load_embed_model()

    @classmethod
    def class_name(cls) -> str:
        return 'ImageParser'

    def _load_embed_model(self):
        return get_automodel(IMAGE_EMBED_KEY)

    def _normalize_image_path(self, image_path: str) -> str:
        if not image_path:
            return image_path
        if is_url(image_path) or image_path.startswith('lazyllm'):
            return image_path
        return os.path.join(self._image_prefix, image_path)

    def _extract_image_path_from_lines(self, lines: list[dict]) -> Optional[str]:
        for line in lines or []:
            image_path = line.get('image_path')
            if image_path:
                return image_path
        return None

    def _extract_image_path(self, node: DocNode) -> Optional[str]:
        metadata = node.metadata
        direct_candidates = [
            metadata.get('image_path'),
            metadata.get('img_path'),
            metadata.get('image'),
            metadata.get('img'),
        ]
        for candidate in direct_candidates:
            if candidate:
                return candidate

        return self._extract_image_path_from_lines(metadata.get('lines', []))

    def _is_image_node(self, node: DocNode) -> bool:
        node_type = str(node.metadata.get('type', '')).lower()
        if node_type in self._image_types:
            return True
        return bool(self._extract_image_path(node))

    def _describe_image(self, image_path: str, node: DocNode) -> str:
        try:
            if hasattr(self._emb_model, 'describe'):
                desc = self._emb_model.describe(image_path=image_path, node=node)
            else:
                desc = self._emb_model(image_path=image_path, node=node)
        except TypeError:
            try:
                if hasattr(self._emb_model, 'describe'):
                    desc = self._emb_model.describe(image_path)
                else:
                    desc = self._emb_model(image_path)
            except Exception as exc:
                LOG.warning(f'[ImageParser] describe image failed: {exc}')
                return ''
        except Exception as exc:
            LOG.warning(f'[ImageParser] describe image failed: {exc}')
            return ''

        if desc is None:
            return ''
        if isinstance(desc, str):
            return desc.strip()
        return str(desc).strip()

    def _build_content(self, node: DocNode, image_markdown: str, image_description: str) -> str:
        parts: List[str] = [image_markdown]

        if self._keep_original_text and (node.text or '').strip():
            parts.append(node.text.strip())

        if image_description:
            parts.append(image_description)

        return '\n'.join(part for part in parts if part).strip()

    def forward(self, document: List[DocNode], **kwargs) -> List[DocNode]:
        return self._parse_nodes(document)

    def _parse_nodes(self, nodes: List[DocNode]) -> List[DocNode]:
        for node in nodes:
            if not self._is_image_node(node):
                continue

            raw_image_path = self._extract_image_path(node)
            if not raw_image_path:
                continue

            normalized_path = self._normalize_image_path(raw_image_path)
            alt_text = (
                node.metadata.get('caption')
                or node.metadata.get('table_caption')
                or node.metadata.get('title')
                or ''
            )
            image_markdown = f'![{alt_text}]({normalized_path})'
            image_description = self._describe_image(normalized_path, node)

            node._metadata['image_path'] = normalized_path
            node._metadata[self._markdown_key] = image_markdown
            if image_description:
                node._metadata[self._description_key] = image_description

            node._content = self._build_content(node, image_markdown, image_description)

        return nodes
