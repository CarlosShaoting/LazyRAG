from pathlib import Path

import pytest

import lazymind.parsing.engine.readers.pdfReader as pdf_reader


def test_lazymind_pdf_reader_normalizes_before_ocr_parsing(monkeypatch, tmp_path):
    source = tmp_path / 'long.pdf'
    source.write_bytes(b'pdf')
    calls = []

    monkeypatch.setattr(pdf_reader, 'normalize_long_pdf_inplace', lambda path: calls.append(('normalize', path)))
    monkeypatch.setattr(pdf_reader.LazyMindPDFReader, '_resolve_route', lambda self, extra_info: ('mineru', 'url'))
    monkeypatch.setattr(
        pdf_reader.DynamicPDFReader,
        '_load_data',
        lambda self, file, extra_info=None, **kwargs: calls.append(('parse', file)) or ['parsed'],
    )

    reader = pdf_reader.LazyMindPDFReader()
    assert reader._load_data(source) == ['parsed']
    assert calls == [('normalize', Path(source)), ('parse', source)]


def test_lazymind_pdf_reader_normalizes_after_default_parsing(monkeypatch, tmp_path):
    source = tmp_path / 'long.pdf'
    source.write_bytes(b'original')
    calls = []

    def normalize(path):
        calls.append(('normalize', path))
        path.write_bytes(b'normalized')

    def parse(self, file, extra_info=None, **kwargs):
        calls.append(('parse', file))
        assert Path(file).read_bytes() == b'original'
        return ['parsed']

    monkeypatch.setattr(pdf_reader, 'normalize_long_pdf_inplace', normalize)
    monkeypatch.setattr(pdf_reader.LazyMindPDFReader, '_resolve_route', lambda self, extra_info: ('none', ''))
    monkeypatch.setattr(pdf_reader.DynamicPDFReader, '_load_data', parse)

    reader = pdf_reader.LazyMindPDFReader()
    assert reader._load_data(source) == ['parsed']
    assert calls == [('parse', source), ('normalize', Path(source))]
    assert source.read_bytes() == b'normalized'


def test_lazymind_pdf_reader_normalizes_after_default_parsing_failure(monkeypatch, tmp_path):
    source = tmp_path / 'long.pdf'
    source.write_bytes(b'original')

    def normalize(path):
        path.write_bytes(b'normalized')

    monkeypatch.setattr(pdf_reader, 'normalize_long_pdf_inplace', normalize)
    monkeypatch.setattr(pdf_reader.LazyMindPDFReader, '_resolve_route', lambda self, extra_info: ('', ''))
    monkeypatch.setattr(
        pdf_reader.DynamicPDFReader,
        '_load_data',
        lambda self, file, extra_info=None, **kwargs: (_ for _ in ()).throw(RuntimeError('parse failed')),
    )

    reader = pdf_reader.LazyMindPDFReader()
    with pytest.raises(RuntimeError, match='parse failed'):
        reader._load_data(source)
    assert source.read_bytes() == b'normalized'
