#!/usr/bin/env python3
"""번역문에 필요한 한글 글리프를 8x8 타일로 쪼개고 중복을 제거한다.

한글 1음절 = 16x16 = 8x8 타일 4개(좌상·우상·좌하·우하).
음절 수 x 4 가 그대로 타일 수가 되진 않는다. 초성·중성·종성 조합이라
조각이 서로 겹치기 때문이다. 실제 타일 수가 남은 설계를 결정한다.

  대사 폰트 경로는 타일 0..255 만 주소지정 가능 ($62BC 테이블이 move.b)
  현재 테이블이 안 쓰는 타일 번호는 96개
  -> 96개 안에 들면 가나 폰트를 살려둘 수 있다(다른 화면이 안 깨진다)
"""
import json
from pathlib import Path

FONT_DIR = Path("font/galmuri11")
BIN = FONT_DIR / "font-58c1637749eb0742.bin"
MAP = FONT_DIR / "font-58c1637749eb0742_glyph_map.json"
KO_TSV = Path("translation/ko.tsv")
GLYPH_BYTES = 32


def quadrants(data: bytes, index: int) -> list[bytes]:
    """16x16 1bpp 글리프 -> 8x8 1bpp 타일 4개 (좌상, 우상, 좌하, 우하)."""
    off = index * GLYPH_BYTES
    rows = [(data[off + y * 2], data[off + y * 2 + 1]) for y in range(16)]
    return [
        bytes(r[0] for r in rows[:8]),    # 좌상
        bytes(r[1] for r in rows[:8]),    # 우상
        bytes(r[0] for r in rows[8:]),    # 좌하
        bytes(r[1] for r in rows[8:]),    # 우하
    ]


def load_text() -> str:
    row = KO_TSV.read_text().rstrip("\n").split("\n")[1].split("\t")
    return row[2].replace("\\n", "\n")


def main() -> None:
    data = BIN.read_bytes()
    gmap = json.loads(MAP.read_text())
    text = load_text()

    syll = sorted({c for c in text if "가" <= c <= "힣"})
    missing = [c for c in syll if c not in gmap]
    if missing:
        print(f"폰트에 없는 음절: {''.join(missing)}")

    # 타일 중복 제거 — 빈 타일은 게임의 기존 공백 타일을 재사용하므로 따로 센다
    tiles: dict[bytes, int] = {}
    per_syll: dict[str, list[bytes]] = {}
    blank = bytes(8)
    for c in syll:
        q = quadrants(data, gmap[c])
        per_syll[c] = q
        for t in q:
            if t != blank:
                tiles.setdefault(t, len(tiles))

    total = len(syll) * 4
    blanks = sum(1 for c in syll for t in per_syll[c] if t == blank)
    print(f"고유 음절        {len(syll)}자")
    print(f"조각 총합        {total}개 (음절당 4)")
    print(f"  빈 조각        {blanks}개 -> 기존 공백 타일 재사용")
    print(f"고유 타일        {len(tiles)}개")
    print(f"중복 제거율      {(1 - len(tiles) / total) * 100:.0f}%")
    print()
    print(f"타일 0..255 중 현재 미사용   96개")
    print(f"가나 타일 회수 시 추가        61개")
    if len(tiles) <= 96:
        print(f"=> {len(tiles)}개는 미사용 타일 96개 안에 들어간다.")
        print("   가나 폰트를 건드리지 않아도 되므로 다른 화면이 깨지지 않는다.")
    elif len(tiles) <= 96 + 61:
        print(f"=> {len(tiles)}개는 가나 타일까지 회수해야 들어간다.")
        print("   다른 화면의 일본어가 깨진다(테스트에는 무해).")
    else:
        print(f"=> {len(tiles)}개는 ASCII 타일까지 회수해야 한다.")

    Path("work/hangul_tiles.json").write_text(json.dumps({
        "syllables": syll,
        "tile_count": len(tiles),
        "tiles": [t.hex() for t in tiles],
        "layout": {c: [tiles.get(t, -1) for t in per_syll[c]] for c in syll},
    }, ensure_ascii=False, indent=1))
    print("\n-> work/hangul_tiles.json  (-1 = 빈 타일)")


if __name__ == "__main__":
    main()
