import re

import pytest
from lazyllm.tools.rag import DocNode
from lazyllm.tools.rag.doc_node import MetadataMode

from lazymind.parsing.engine.transform import general_parser as general_parser_module
from lazymind.parsing.engine.transform.general_parser import GeneralParser, is_url


def test_is_url_accepts_network_and_file_urls():
    assert is_url('https://example.test/a.png') is True
    assert is_url('file:///tmp/a.png') is True
    assert is_url('images/a.png') is False


def test_is_url_returns_false_when_urlparse_raises(monkeypatch):
    def bad_urlparse(value):
        raise ValueError('bad url')

    monkeypatch.setattr(general_parser_module, 'urlparse', bad_urlparse)

    assert is_url('https://example.test/a.png') is False


def test_image_path_transform_prefixes_only_relative_paths(monkeypatch):
    monkeypatch.setattr(general_parser_module, 'IMAGE_PREFIX', '/assets/images/')
    parser = GeneralParser()

    text = parser._image_path_transform(
        '![local](tables/a.png) ![remote](https://example.test/b.png) ![lazy](lazyllm://image/c.png)'
    )

    assert '![local](/assets/images/tables/a.png)' in text
    assert '![remote](https://example.test/b.png)' in text
    assert '![lazy](lazyllm://image/c.png)' in text
    image_urls = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', text)
    assert image_urls == ['/assets/images/tables/a.png', 'https://example.test/b.png', 'lazyllm://image/c.png']


def test_split_prefers_separator_and_force_splits_long_parts():
    parser = GeneralParser(max_length=6, split_by='\n')

    assert parser._split('aa\nbbb\nc') == ['aa\nbbb', 'c']
    assert parser._split('abcdefgh') == ['abcdef', 'gh']
    assert parser._split('') == []


def test_forward_reduces_chunk_size_for_selected_embedding_limit(monkeypatch):
    parser = GeneralParser(max_length=2048, split_by='\n')
    monkeypatch.setattr(general_parser_module, '_runtime_embed_max_input_tokens', lambda: 512)

    chunks = parser.forward(DocNode(text='a' * 769))

    assert [len(chunk.text) for chunk in chunks] == [384, 384, 1]


def test_forward_uses_fixed_chunk_size_for_2048_token_embedding(monkeypatch):
    parser = GeneralParser(max_length=2048, split_by='\n')
    monkeypatch.setattr(general_parser_module, '_runtime_embed_max_input_tokens', lambda: 2048)

    chunks = parser.forward(DocNode(text='a' * 1921))

    assert [len(chunk.text) for chunk in chunks] == [1920, 1]


def test_forward_uses_default_chunk_size_without_embedding_limit(monkeypatch):
    parser = GeneralParser(max_length=2048, split_by='\n')
    monkeypatch.setattr(general_parser_module, '_runtime_embed_max_input_tokens', lambda: None)

    chunks = parser.forward(DocNode(text='a' * 2048))

    assert [len(chunk.text) for chunk in chunks] == [2048]


def test_general_parser_rejects_invalid_constructor_args():
    with pytest.raises(AssertionError, match='max_length'):
        GeneralParser(max_length=0)
    with pytest.raises(AssertionError, match='split_by'):
        GeneralParser(split_by='')


def test_forward_transforms_images_splits_and_copies_metadata(monkeypatch):
    monkeypatch.setattr(general_parser_module, 'IMAGE_PREFIX', '/assets/images/')
    parser = GeneralParser(max_length=40, split_by='\n')
    metadata = {'page': 1, 'nested': {'value': 'keep'}}
    global_metadata = {'file_name': 'manual.md'}
    node = DocNode(
        text='intro ![img](a.png)\nsecond paragraph',
        metadata=metadata,
        global_metadata=global_metadata,
    )

    chunks = parser.forward(node)

    assert isinstance(chunks, list)
    assert all(isinstance(chunk, DocNode) for chunk in chunks)
    assert [chunk.text for chunk in chunks] == ['intro ![img](/assets/images/a.png)', 'second paragraph']
    assert chunks[0].metadata == metadata
    assert chunks[0].metadata is not metadata
    assert chunks[0].metadata['nested'] is not metadata['nested']
    assert chunks[0].global_metadata == global_metadata
    assert chunks[0].global_metadata is not global_metadata


def test_forward_inherits_parent_metadata_exclusions(monkeypatch):
    monkeypatch.setattr(general_parser_module, 'IMAGE_PREFIX', '/assets/images/')
    parser = GeneralParser(max_length=12, split_by='\n')
    node = DocNode(
        text='first chunk\nsecond chunk',
        metadata={'file_name': 'doc.pdf', 'page': 1, 'bbox': [0, 0, 1, 1], 'lines': [{'content': 'x'}]},
    )
    node.excluded_embed_metadata_keys = ['page', 'bbox', 'lines']
    node.excluded_llm_metadata_keys = ['page', 'bbox', 'lines']

    chunks = parser.forward(node)

    assert len(chunks) == 2
    for chunk in chunks:
        assert set(chunk.excluded_embed_metadata_keys) == {'page', 'bbox', 'lines'}
        assert set(chunk.excluded_llm_metadata_keys) == {'page', 'bbox', 'lines'}
        assert chunk.get_text(MetadataMode.EMBED) == 'file_name: doc.pdf\n\n' + chunk.text
