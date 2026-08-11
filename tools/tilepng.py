#!/usr/bin/env python3
"""롬 구간을 1bpp / 4bpp 타일로 해석해 PNG 로 저장한다 (Tile Molester 대용).

usage: python3 tools/tilepng.py <rom> <hex_offset> <bpp> <glyph_w> <glyph_h> <count> <out.png>
  bpp 1  : 글리프 = w/8 * h 바이트, 행 단위 MSB-first
  bpp 4md: MD 4bpp 8x8 타일 32바이트 (glyph_w/h 는 8 의 배수)
"""
import struct
import sys
import zlib
from pathlib import Path

SCALE = 3
COLS = 16
PAD = 1


def png(path: Path, w: int, h: int, pix: list[list[int]]) -> None:
    """pix[y][x] = 0..255 grayscale"""
    raw = b"".join(b"\x00" + bytes(row) for row in pix)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def glyph_1bpp(data: bytes, off: int, gw: int, gh: int) -> list[list[int]]:
    bpr = gw // 8
    out = []
    for y in range(gh):
        row = []
        for xb in range(bpr):
            b = data[off + y * bpr + xb] if off + y * bpr + xb < len(data) else 0
            row += [255 if b >> (7 - i) & 1 else 0 for i in range(8)]
        out.append(row)
    return out


def glyph_4bpp_md(data: bytes, off: int, gw: int, gh: int) -> list[list[int]]:
    """MD planar-free 4bpp: 8x8 tile = 32 bytes, tiles stacked column-major within glyph."""
    tw, th = gw // 8, gh // 8
    out = [[0] * gw for _ in range(gh)]
    for tx in range(tw):
        for ty in range(th):
            base = off + (tx * th + ty) * 32
            for y in range(8):
                for k in range(4):
                    b = data[base + y * 4 + k] if base + y * 4 + k < len(data) else 0
                    for j, nib in enumerate((b >> 4, b & 15)):
                        out[ty * 8 + y][tx * 8 + k * 2 + j] = nib * 17
    return out


def main() -> None:
    rom, off, bpp, gw, gh, cnt, out = sys.argv[1:8]
    data = Path(rom).read_bytes()
    off, gw, gh, cnt = int(off, 16), int(gw), int(gh), int(cnt)
    gsz = gw * gh // 8 if bpp == "1" else (gw // 8) * (gh // 8) * 32
    render = glyph_1bpp if bpp == "1" else glyph_4bpp_md

    rows = (cnt + COLS - 1) // COLS
    cw, ch = gw + PAD, gh + PAD
    W, H = COLS * cw * SCALE, rows * ch * SCALE
    canvas = [[64] * W for _ in range(H)]

    for i in range(cnt):
        g = render(data, off + i * gsz, gw, gh)
        ox, oy = (i % COLS) * cw, (i // COLS) * ch
        for y in range(gh):
            for x in range(gw):
                v = g[y][x]
                for sy in range(SCALE):
                    for sx in range(SCALE):
                        canvas[(oy + y) * SCALE + sy][(ox + x) * SCALE + sx] = v

    png(Path(out), W, H, canvas)
    print(f"{out}: {W}x{H}, {cnt} glyphs of {gw}x{gh} from {off:06X} (+{gsz}B each)")


if __name__ == "__main__":
    main()
