#!/usr/bin/env python3
"""16x16 한글 가독성 비교용 테스트 롬. 역시 새 68000 코드는 쓰지 않는다.

핵심 요령
---------
줄바꿈 `0x0D` 은 `Y += 1`, 즉 타일 한 행만 내려간다.
그래서 한 줄을 두 번 쓰면 세로로 붙은 16x16 이 만들어진다.

    [상반부 타일들] 0x0D [하반부 타일들] 0x0D

탁점 경로(0xDE/0xDF)는 서로 다른 상반부 글리프를 2종밖에 못 만들므로 쓰지 않는다.
이 방식은 그런 제약이 없다.

제약: 음절당 타일 4개라 안전 타일 40개로는 음절 10자 남짓이 한계다.
전체 대본용이 아니라 8x8 과 나란히 놓고 가독성을 판단하기 위한 표본이다.
"""
import json
from pathlib import Path

SRC = Path("/Users/rotein/Downloads/Langrisser.md")
G11_BIN = Path("font/galmuri11/font-58c1637749eb0742.bin")
G11_MAP = Path("font/galmuri11/font-58c1637749eb0742_glyph_map.json")
SAFE = Path("work/safe_tiles.json")

TABLE_AT, MSG_AT, MSG_LIMIT, CHECKSUM_AT = 0x62BC, 0x38C42, 186, 0x18E
SPACE = 0x20
FREE_CODES = list(range(0x7F, 0xA1)) + list(range(0xE0, 0xFE))

TEXT = "주인에게 무한한 힘을 주는 검"


def quads(font: bytes, i: int) -> list[bytes]:
    """16x16 1bpp -> 8x8 타일 4개 (좌상, 우상, 좌하, 우하)."""
    o = i * 32
    r = [(font[o + y * 2], font[o + y * 2 + 1]) for y in range(16)]
    return [bytes(x[0] for x in r[:8]), bytes(x[1] for x in r[:8]),
            bytes(x[0] for x in r[8:]), bytes(x[1] for x in r[8:])]


def main() -> None:
    rom = bytearray(SRC.read_bytes())
    font = G11_BIN.read_bytes()
    gmap = json.loads(G11_MAP.read_text())
    safe = {int(k): v for k, v in json.loads(SAFE.read_text()).items()}
    slots = sorted(safe)

    # 음절 -> 사분면 4개, 중복 타일은 공유
    tile_of: dict[bytes, int] = {}
    layout: dict[str, list[int | None]] = {}
    for ch in sorted({c for c in TEXT if "가" <= c <= "힣"}):
        qs = quads(font, gmap[ch])
        layout[ch] = [None if not any(q) else tile_of.setdefault(q, len(tile_of))
                      for q in qs]

    if len(tile_of) > min(len(slots), len(FREE_CODES)):
        raise SystemExit(f"자리 부족: 타일 {len(tile_of)} 필요 / "
                         f"슬롯 {len(slots)} / 코드 {len(FREE_CODES)}")

    # 각 고유 타일에 롬 자리와 바이트 코드를 배정
    tiles = [slots[i] for i in range(len(tile_of))]
    codes = [FREE_CODES[i] for i in range(len(tile_of))]
    print(f"음절 {len(layout)}자 / 고유 타일 {len(tile_of)}개")

    for q, i in tile_of.items():
        rom[safe[tiles[i]]:safe[tiles[i]] + 8] = q
        rom[TABLE_AT + codes[i]] = tiles[i]
    print(f"  폰트 타일 {len(tile_of)}개 덮어씀 / $62BC {len(tile_of)}엔트리 갱신")

    def emit(ch: str, half: int) -> bytes:
        """half=0 상반부(좌상,우상) / half=1 하반부(좌하,우하)"""
        if ch == " ":
            return bytes([SPACE, SPACE])          # 한글이 2칸이므로 공백도 2칸
        a, b = layout[ch][half * 2], layout[ch][half * 2 + 1]
        return bytes([SPACE if a is None else codes[a],
                      SPACE if b is None else codes[b]])

    out = bytearray()
    for half in (0, 1):
        for ch in TEXT:
            out += emit(ch, half)
        out += b"\x0d"                            # 상반부 -> 하반부, 한 행만 내려간다
    out.append(0xFF)

    if len(out) > MSG_LIMIT:
        raise SystemExit(f"메시지 {len(out)}B > 원본 {MSG_LIMIT}B")
    rom[MSG_AT:MSG_AT + len(out)] = out
    rom[CHECKSUM_AT] = rom[CHECKSUM_AT + 1] = 0
    print(f"  대사 {len(out)}B / 원본 자리 {MSG_LIMIT}B, 체크섬 우회")

    Path("work/korom_16x16.md").write_bytes(rom)
    print(f"\n-> work/korom_16x16.md")
    print(f'   표시 내용: "{TEXT}"  ({len(TEXT) * 2}칸)')


if __name__ == "__main__":
    main()
