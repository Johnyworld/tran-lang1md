#!/usr/bin/env python3
"""타일맵으로 그려지는 라벨 전수 조사 — `$5CDC` 호출 61곳을 전부 본다.

창 레코드(`[폭][높이][0xC000][5][포인터]`)만 훑으면 놓친다. `位置選択` 처럼
**코드가 `lea <서술자>, a1` + `move.w #베이스, d4` 로 직접 부르는** 것이 있다.
그래서 호출 지점에서 거꾸로 a1·d4 를 찾는다.

```
$5CDC  a1 = 서술자([순서][폭][높이][데이터]), d4 = 타일 베이스 워드
```

베이스가 타일 256 미만이면 창 테두리(폰트 타일 0..118)이므로 라벨이 아니다.
그 이상이면 미리 그려둔 텍스트 그래픽이고 번역 대상이다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import menu  # noqa: E402

SRC = Path("/Users/rotein/Downloads/Langrisser.md")
TILEMAP = 0x5CDC
BACK = 0x40                      # 호출 앞 이 범위에서 a1·d4 를 찾는다


def callers(src: bytes, target: int) -> list[int]:
    out = []
    for p in range(0, len(src) - 6, 2):
        w = int.from_bytes(src[p:p + 2], "big")
        if w in (0x4EB9, 0x4EF9) and int.from_bytes(src[p + 2:p + 6], "big") == target:
            out.append(p)
        elif w in (0x6100, 0x6000):
            d = int.from_bytes(src[p + 2:p + 4], "big")
            d = d - 0x10000 if d > 0x7FFF else d
            if p + 2 + d == target:
                out.append(p)
        elif (w >> 8) in (0x61, 0x60) and (w & 0xFF) not in (0, 0xFF):
            d = w & 0xFF
            d = d - 0x100 if d > 0x7F else d
            if p + 2 + d == target:
                out.append(p)
    return out


def back_scan(src: bytes, at: int) -> tuple[int | None, int | None]:
    """호출 앞에서 마지막 `lea imm.l, a1` 과 `move.w #imm, d4` 를 찾는다."""
    a1 = d4 = None
    for p in range(at - BACK, at, 2):
        if p < 0:
            continue
        w = int.from_bytes(src[p:p + 2], "big")
        if w == 0x43F9:                                  # lea imm.l, a1
            a1 = int.from_bytes(src[p + 2:p + 6], "big")
        elif w == 0x383C:                                # move.w #imm, d4
            d4 = int.from_bytes(src[p + 2:p + 4], "big")
    return a1, d4


def main() -> None:
    src = SRC.read_bytes()
    sites = callers(src, TILEMAP)
    print(f"$5CDC 호출 {len(sites)}곳\n")
    seen: dict[tuple[int, int], list[int]] = {}
    for at in sites:
        a1, d4 = back_scan(src, at)
        if a1 is None or d4 is None:
            continue
        seen.setdefault((a1, d4), []).append(at)

    print(f"{'서술자':>8} {'베이스':>6} {'크기':>7}  호출 지점")
    labels = []
    for (a1, d4), ats in sorted(seen.items()):
        tile = d4 & 0x7FF
        try:
            _, w, h, grid, dlen = menu.decode(src, a1 - 8, tile)
        except (SystemExit, AssertionError, IndexError) as e:
            # 뒤로 훑어 찾은 a1 이 그 호출의 것이 아닐 수 있다 (오탐)
            print(f"{a1:08X} {tile:6d}  파싱 실패 — 오탐으로 본다: {e}")
            continue
        mark = "" if tile < 256 else "  <- 라벨 (번역 대상)"
        print(f"{a1:08X} {tile:6d} {w:3d}x{h:<3d}  "
              + " ".join(f"{x:06X}" for x in ats) + mark)
        if tile >= 256:
            labels.append((a1, tile, w, h, ats))
    print(f"\n라벨 후보 {len(labels)}개")
    for a1, tile, w, h, ats in labels:
        print(f"  서술자 {a1:06X}  베이스 타일 {tile}  {w}x{h}  호출 "
              + " ".join(f"{x:06X}" for x in ats))


if __name__ == "__main__":
    main()
