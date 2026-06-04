import os
from pathlib import Path
from typing import List, Optional, Tuple
from fastapi import HTTPException

from lazymind.chat.config import MOUNT_BASE_DIR

_IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tiff', '.tif', '.heic', '.heif')


def split_image_files(paths: List[str]) -> Tuple[List[str], List[str]]:
    image_files = [p for p in paths if p.lower().endswith(_IMAGE_EXTENSIONS)]
    other_files = [p for p in paths if p not in image_files]
    return other_files, image_files


def validate_and_resolve_files(files: Optional[List[str]]) -> List[str]:
    if not files:
        return []

    root = Path(MOUNT_BASE_DIR).resolve()
    resolved: List[str] = []
    for f in files:
        if '\x00' in f:
            raise HTTPException(status_code=400, detail='Invalid path')
        p = Path(f)
        cand = (p if p.is_absolute() else root / p).resolve()
        if not cand.is_relative_to(root):
            raise HTTPException(status_code=400, detail='Path outside mount directory')
        if not cand.is_file() or not os.access(cand, os.R_OK):
            raise HTTPException(status_code=400, detail=f'File not accessible: {f}')
        resolved.append(str(cand))

    return resolved
