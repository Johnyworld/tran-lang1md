#!/usr/bin/env python3
"""한글 프롤로그 테스트 롬을 만든다. 새 68000 코드 없이 세 가지만 고친다.

  1. 폰트 타일 데이터 — 안전한 타일 자리에 Galmuri7 8x8 1bpp 글리프를 덮어쓴다
  2. $62BC 변환 테이블 — 한글 바이트 코드 -> 타일 번호 매핑을 심는다
  3. 대사 바이트 — 0x38C42 에 인코딩한 한글을 쓴다

"안전한 타일" = $62BC 로 도달 가능하지만(직접 또는 |0x40) 이 화면 네임테이블에는
등장하지 않는 타일. 덮어써도 테스트 화면에는 영향이 없다. 다른 화면의 일본어는
일부 글자가 한글로 바뀌어 보이지만 테스트에는 무해하다.

바이트 코드는 텍스트에 쓰이지 않는 구간에서 고른다.
  제어코드   0x0D 줄바꿈 / 0x7E 히라가나 토글 / 0xDE·0xDF 탁점 / 0xFF 종료
  사용 중    0x20..0x7D ASCII, 0xA1..0xDD 가나
  여유       0x7F..0xA0, 0xE0..0xFD
"""
import json
from pathlib import Path

SRC = Path("/Users/rotein/Downloads/Langrisser.md")
G7_BIN = Path("font/galmuri7/font-007242d37349daf3.bin")
G7_MAP = Path("font/galmuri7/font-007242d37349daf3_glyph_map.json")
SAFE = Path("work/safe_tiles.json")
KO_TSV = Path("translation/ko.tsv")

TABLE_AT = 0x62BC
MSG_AT = 0x38C42
MSG_LIMIT = 186          # 원본 메시지 길이 — 넘지 않는다
CHECKSUM_AT = 0x18E

# 게임 폰트에 이미 있는 문자는 기존 코드를 그대로 쓴다
PASSTHROUGH = {" ": 0x20, "。": 0xA1, "「": 0xA2, "」": 0xA3}
FREE_CODES = list(range(0x7F, 0xA1)) + list(range(0xE0, 0xFE))


def main() -> None:
    rom = bytearray(SRC.read_bytes())
    font = G7_BIN.read_bytes()
    gmap = json.loads(G7_MAP.read_text())
    safe = {int(k): v for k, v in json.loads(SAFE.read_text()).items()}

    kr = KO_TSV.read_text().rstrip("\n").split("\n")[1].split("\t")[2]
    lines = kr.split("\\n")
    syll = sorted({c for c in kr if "가" <= c <= "힣"})

    tiles = sorted(safe)
    if len(syll) > min(len(tiles), len(FREE_CODES)):
        raise SystemExit(f"자리 부족: 음절 {len(syll)} / 타일 {len(tiles)} / 코드 {len(FREE_CODES)}")

    # 음절 -> (바이트 코드, 타일 번호)
    assign = {c: (FREE_CODES[i], tiles[i]) for i, c in enumerate(syll)}

    print(f"음절 {len(syll)}자 배정 (코드 0x{FREE_CODES[0]:02X}.. / 타일 {tiles[0]}..)")

    # 1. 폰트 타일 덮어쓰기
    for c, (_, tile) in assign.items():
        gi = gmap[c]
        rom[safe[tile]:safe[tile] + 8] = font[gi * 8:gi * 8 + 8]
    print(f"  폰트 타일 {len(assign)}개 덮어씀")

    # 2. 변환 테이블
    for c, (code, tile) in assign.items():
        rom[TABLE_AT + code] = tile
    print(f"  $62BC 엔트리 {len(assign)}개 갱신")

    # 3. 대사 인코딩
    out = bytearray()
    for i, line in enumerate(lines):
        if i:
            out += b"\x0d\x0d"          # 한 줄 = 0x0D 두 개 (렌더러 Y+=1, 글리프 2행)
        for ch in line:
            if ch in PASSTHROUGH:
                out.append(PASSTHROUGH[ch])
            elif ch in assign:
                out.append(assign[ch][0])
            else:
                raise SystemExit(f"인코딩할 수 없는 문자: {ch!r}")
    out.append(0xFF)
    if len(out) > MSG_LIMIT:
        raise SystemExit(f"메시지 {len(out)}B > 원본 {MSG_LIMIT}B")
    rom[MSG_AT:MSG_AT + len(out)] = out
    print(f"  대사 {len(out)}B / 원본 자리 {MSG_LIMIT}B")

    # 4. 체크섬 검사 우회 (0x18E == 0 이면 tst.w/beq 로 비교를 건너뛴다)
    rom[CHECKSUM_AT] = rom[CHECKSUM_AT + 1] = 0
    print("  체크섬 우회 (0x18E = 0000)")

    out_path = Path("work/korom_prologue.md")
    out_path.write_bytes(rom)
    print(f"\n-> {out_path}  ({len(rom):,} bytes)")

    Path("work/assign.json").write_text(json.dumps(
        {c: {"code": f"{v[0]:02X}", "tile": v[1], "rom": f"{safe[v[1]]:06X}"}
         for c, v in assign.items()}, ensure_ascii=False, indent=1))
    print("-> work/assign.json")


if __name__ == "__main__":
    main()
