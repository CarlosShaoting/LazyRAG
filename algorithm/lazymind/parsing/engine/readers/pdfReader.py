from pathlib import Path

from lazyllm import LOG
from lazyllm.tools.rag.readers.ocrReader import DynamicPDFReader


def normalize_long_pdf_inplace(path: Path) -> bool:
    # Keep imports compatible with LazyLLM releases that predate long-PDF normalization.
    from lazyllm.tools.pdf_utils import normalize_long_pdf_inplace as normalize
    return normalize(path)


class LazyMindPDFReader(DynamicPDFReader):
    __lazyllm_registry_disable__ = True

    @staticmethod
    def _normalize_long_pdf(path: Path) -> None:
        try:
            normalize_long_pdf_inplace(path)
        except Exception as exc:
            LOG.warning(f'[LazyMindPDFReader] Long PDF normalization skipped: {path}: {exc}')

    def _load_data(self, file, extra_info=None, **kwargs):
        path = Path(file)
        if path.suffix.lower() != '.pdf':
            return super()._load_data(file, extra_info=extra_info, **kwargs)

        ocr_type, _ = self._resolve_route(extra_info)
        if ocr_type in ('', 'none'):
            try:
                # CropBox-based pages still share the original content stream, while pypdf ignores CropBox during
                # text extraction. Read the original single page first to avoid parsing the same long stream per slice.
                return super()._load_data(file, extra_info=extra_info, **kwargs)
            finally:
                # The stored path is replaced after parsing so the frontend always displays the sliced PDF.
                self._normalize_long_pdf(path)

        self._normalize_long_pdf(path)
        return super()._load_data(file, extra_info=extra_info, **kwargs)


__all__ = ['LazyMindPDFReader']
