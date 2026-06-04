from lazyllm.tools.rag.readers.ocrReader.ocr_reader_base import (
    _is_mineru_official_online_url,
    _is_paddle_official_online_url,
)


def test_mineru_online_url_detection():
    assert _is_mineru_official_online_url('') is True
    assert _is_mineru_official_online_url('https://mineru.net/api/v4/file-urls/batch') is True
    assert _is_mineru_official_online_url('http://mineru:8000/api/v1/pdf_parse') is False
    assert _is_mineru_official_online_url('http://172.24.176.1:20234/api/v1/pdf_parse') is False


def test_paddle_online_url_detection():
    assert _is_paddle_official_online_url('') is True
    assert _is_paddle_official_online_url(
        'https://k4q3k6o0l1hbx6jc.aistudio-app.com/layout-parsing'
    ) is True
    assert _is_paddle_official_online_url('http://paddleocr:8080') is False
