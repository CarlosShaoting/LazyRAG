#!/usr/bin/env python3
"""Refresh the immutable Skill resource bundle embedded in ``tools.py``.

Usage: ``python embed_skill_contract.py /path/to/product-solution-delivery``.
Only already packaged resources plus the shared rich-presentation contract are
embedded, so unrelated files in a developer's local Skill directory cannot leak
into the Workflow release.
"""

from __future__ import annotations

import argparse
import ast
import base64
import json
import textwrap
import zlib
from pathlib import Path


START = "RESOURCE_BUNDLE_B85 = ("
END = "\n)\n# END EMBEDDED CONTRACT BUNDLE"
RICH_PRESENTATION = "references/rich-text-presentation.md"


def decode_existing(source: str) -> dict[str, str]:
    start = source.index(START)
    end = source.index(END, start) + 2
    assignment = ast.parse(source[start:end]).body[0]
    encoded = ast.literal_eval(assignment.value)
    return json.loads(zlib.decompress(base64.b85decode(encoded.encode("ascii"))).decode("utf-8"))


def encode_bundle(resources: dict[str, str]) -> str:
    payload = json.dumps(resources, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    encoded = base64.b85encode(zlib.compress(payload.encode("utf-8"), level=9)).decode("ascii")
    lines = [repr(chunk) for chunk in textwrap.wrap(encoded, width=100)]
    return START + "\n" + "\n".join(f"    {line}" for line in lines) + "\n)"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("skill_root", type=Path)
    parser.add_argument("--tools", type=Path, default=Path(__file__).with_name("tools.py"))
    args = parser.parse_args()
    source = args.tools.read_text(encoding="utf-8")
    resources = decode_existing(source)
    resources.setdefault(RICH_PRESENTATION, "")
    for relative in resources:
        path = args.skill_root / relative
        if not path.is_file():
            continue
        resources[relative] = path.read_text(encoding="utf-8")
    if not resources[RICH_PRESENTATION].strip():
        raise SystemExit(f"Missing required Skill resource: {RICH_PRESENTATION}")
    start = source.index(START)
    end = source.index(END, start) + 2
    args.tools.write_text(source[:start] + encode_bundle(resources) + source[end:], encoding="utf-8")


if __name__ == "__main__":
    main()
