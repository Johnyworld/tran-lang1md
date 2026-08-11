#!/usr/bin/env python3
"""Galmuri11 16x16 1bpp 폰트 bin 을 ASCII 아트로 확인한다.

usage: python3 tools/fontdump.py 랑그릿사
"""
import json
import sys
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent.parent / "font" / "galmuri11"
BIN = FONT_DIR / "font-58c1637749eb0742.bin"
MAP = FONT_DIR / "font-58c1637749eb0742_glyph_map.json"

GLYPH_BYTES = 32  # 16x16 1bpp = 16 rows * 2 bytes


def glyph(data: bytes, index: int) -> list[str]:
    off = index * GLYPH_BYTES
    rows = []
    for y in range(16):
        hi, lo = data[off + y * 2], data[off + y * 2 + 1]
        bits = (hi << 8) | lo
        rows.append("".join("#" if bits >> (15 - x) & 1 else "." for x in range(16)))
    return rows


def main() -> None:
    text = sys.argv[1] if len(sys.argv) > 1 else "랑그릿사"
    data = BIN.read_bytes()
    gmap = json.loads(MAP.read_text())
    print(f"{BIN.name}: {len(data)} bytes / {len(data)//GLYPH_BYTES} glyphs")

    missing = [c for c in text if c not in gmap]
    if missing:
        print(f"미수록 글자: {''.join(missing)}")

    rendered = [glyph(data, gmap[c]) for c in text if c in gmap]
    for y in range(16):
        print("  ".join(g[y] for g in rendered))


if __name__ == "__main__":
    main()
