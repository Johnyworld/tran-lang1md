#!/usr/bin/env python3
"""VRAM 덤프의 네임테이블을 읽어 화면 텍스트를 복원한다.

발견된 규칙:
  본문 폰트는 8x16 = 세로로 붙은 두 타일. 위 타일은 탁점/반탁점(보통 공백),
  아래 타일이 가나 본체.
    아래 타일  카타카나 = JIS X 0201 코드 - 0x20   (0xA1..0xDF -> 129..191)
               히라가나 = JIS X 0201 코드 + 0x20   (0xA1..0xDF -> 193..255)
    위 타일    101 = 공백, 106 = 탁점, 107 = 반탁점
  8x8 ASCII 폰트는 별도로 타일 0..95 = 코드 0x20..0x7F.
"""
import sys
from pathlib import Path

JIS = (
    "。「」、・ヲァィゥェォャュョッー"
    "アイウエオカキクケコサシスセソ"
    "タチツテトナニヌネノハヒフヘホマ"
    "ミムメモヤユヨラリルレロワン゛゜"
)
KATA = {i + 0xA1: c for i, c in enumerate(JIS)}
KANA_TO_HIRA = str.maketrans(
    "ヲァィゥェォャュョッアイウエオカキクケコサシスセソタチツテトナニヌネノ"
    "ハヒフヘホマミムメモヤユヨラリルレロワン",
    "をぁぃぅぇぉゃゅょっあいうえおかきくけこさしすせそたちつてとなにぬねの"
    "はひふへほまみむめもやゆよらりるれろわん",
)
DAKUTEN = dict(zip("カキクケコサシスセソタチツテトハヒフヘホウかきくけこさしすせそたちつてとはひふへほう",
                   "ガギグゲゴザジズゼゾダヂヅデドバビブベボヴがぎぐげござじずぜぞだぢづでどばびぶべぼゔ"))
HANDAKU = dict(zip("ハヒフヘホはひふへほ", "パピプペポぱぴぷぺぽ"))

BASE, PITCH, COLS = 0xC000, 0x80, 64


def glyph(tile: int) -> str:
    """아래 타일 인덱스 -> 문자"""
    if tile == 101:
        return " "
    if 0 <= tile <= 95:
        return chr(tile + 0x20)
    for shift, hira in ((0x20, False), (-0x20, True)):
        code = tile + shift
        if code in KATA:
            c = KATA[code]
            return c.translate(KANA_TO_HIRA) if hira else c
    return f"[{tile}]"


def combine(base: str, mark: int) -> str:
    if mark == 106:
        return DAKUTEN.get(base, base)
    if mark == 107:
        return HANDAKU.get(base, base)
    return base


def main() -> None:
    d = Path(sys.argv[1]).read_bytes()

    def word(row: int, col: int) -> int:
        o = BASE + row * PITCH + col * 2
        return (d[o] << 8) | d[o + 1]

    print("=== 화면 복원 (아래 타일 + 위 타일의 탁점 결합) ===")
    for row in range(1, 28):
        line = ""
        for col in range(COLS):
            low = word(row, col) & 0x7FF
            top = word(row - 1, col) & 0x7FF
            line += combine(glyph(low), top)
        if line.strip():
            print(f"row{row:2d} |{line.rstrip()}")


if __name__ == "__main__":
    main()
