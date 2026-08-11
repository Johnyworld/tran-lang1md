#!/usr/bin/env python3
"""MD VRAM 덤프를 4bpp 8x8 타일 시트 PNG 로 그린다.

usage: python3 tools/vramsheet.py <vram.bin> <out.png> [first_tile] [tile_count] [cols] [scale]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tilepng import png  # noqa: E402

GRID = 80  # 타일 경계선 밝기


def main() -> None:
    src, out = sys.argv[1], sys.argv[2]
    first = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    count = int(sys.argv[4]) if len(sys.argv) > 4 else 2048
    cols = int(sys.argv[5]) if len(sys.argv) > 5 else 64
    scale = int(sys.argv[6]) if len(sys.argv) > 6 else 2

    data = Path(src).read_bytes()
    count = min(count, len(data) // 32 - first)
    rows = (count + cols - 1) // cols
    cw = ch = 9  # 8px + 1px 격자
    W, H = cols * cw * scale, rows * ch * scale
    canvas = [[GRID] * W for _ in range(H)]

    for i in range(count):
        base = (first + i) * 32
        ox, oy = (i % cols) * cw, (i // cols) * ch
        for y in range(8):
            for k in range(4):
                b = data[base + y * 4 + k]
                for j, nib in enumerate((b >> 4, b & 15)):
                    v = nib * 17
                    px, py = ox + k * 2 + j, oy + y
                    for sy in range(scale):
                        for sx in range(scale):
                            canvas[py * scale + sy][px * scale + sx] = v

    png(Path(out), W, H, canvas)
    print(f"{out}: {W}x{H}, tiles {first}..{first+count-1} ({cols} cols)")


if __name__ == "__main__":
    main()
