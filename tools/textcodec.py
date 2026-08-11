#!/usr/bin/env python3
"""랑그릿사(MD) 텍스트 인코딩 코덱.

검증된 규칙:  타일 인덱스 = (바이트 + 0x20) & 0xFF
  타일 0..95    8x8 ASCII, 문자코드 = 타일 + 0x20
  타일 129..191 카타카나, JIS X 0201 = 타일 + 0x20
  타일 193..255 히라가나, JIS X 0201 = 타일 - 0x20
  타일 101 공백 / 106 탁점 / 107 반탁점 (탁점은 윗줄 타일에 얹힘)
"""
JIS = ("。「」、・ヲァィゥェォャュョッー"
       "アイウエオカキクケコサシスセソ"
       "タチツテトナニヌネノハヒフヘホマ"
       "ミムメモヤユヨラリルレロワン゛゜")
KATA = {i + 0xA1: c for i, c in enumerate(JIS)}
TO_HIRA = str.maketrans(
    "ヲァィゥェォャュョッアイウエオカキクケコサシスセソタチツテトナニヌネノ"
    "ハヒフヘホマミムメモヤユヨラリルレロワン",
    "をぁぃぅぇぉゃゅょっあいうえおかきくけこさしすせそたちつてとなにぬねの"
    "はひふへほまみむめもやゆよらりるれろわん")


def tile_to_char(tile: int) -> str | None:
    if tile == 101:
        return " "
    if tile == 106:
        return "゛"      # ゛
    if tile == 107:
        return "゜"      # ゜
    if 0 <= tile <= 95:
        return chr(tile + 0x20)
    if (c := KATA.get(tile + 0x20)) and 129 <= tile <= 191:
        return c
    if (c := KATA.get(tile - 0x20)) and 193 <= tile <= 255:
        return c.translate(TO_HIRA)
    return None


def byte_to_char(b: int) -> str | None:
    return tile_to_char((b + 0x20) & 0xFF)


def decode(data: bytes) -> str:
    """알 수 없는 바이트는 <XX> 로 남긴다."""
    out = []
    for b in data:
        c = byte_to_char(b)
        out.append(c if c is not None else f"<{b:02X}>")
    return "".join(out)


def encode(text: str) -> bytes:
    rev = {}
    for b in range(256):
        c = byte_to_char(b)
        if c is not None and c not in rev:
            rev[c] = b
    return bytes(rev[c] for c in text)


def run_length(data: bytes, start: int) -> int:
    """start 부터 디코드 가능한 바이트가 몇 개 이어지는지"""
    n = 0
    while start + n < len(data) and byte_to_char(data[start + n]) is not None:
        n += 1
    return n
