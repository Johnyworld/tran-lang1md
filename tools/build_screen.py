#!/usr/bin/env python3
"""프롤로그 화면 전체를 한글로. 화면 단위 슬롯 공유.

왜 화면 단위인가
----------------
네임테이블은 타일 *번호* 만 들고 있다. 나중에 그 타일의 픽셀을 바꾸면 먼저
그려진 글자의 모양까지 바뀐다. 그래서 한 화면에 동시에 보이는 문자열들은
**하나의 일관된 타일 배정을 공유해야** 한다.

이 화면은 세 문자열을 그린다 (0x18CE8 렌더러).
  0x18D12  스테이지명   $38A38 테이블   X=12 Y=3    <- 먼저 그려진다. 여기에 훅
  0x18D2A  프롤로그     $38BF2 테이블   X=3  Y=5
  0x18D42  승패조건     $3962E 테이블   X=9  Y=15

첫 draw 에 훅을 걸어 세 문자열 글리프의 **합집합**을 한 번에 올린다.
따라서 헤더(마커+ID 목록)는 스테이지명 문자열만 갖고, 나머지 둘은 본문뿐이다.

코드 공간
---------
여유 코드는 0x7F..0xA0 (34) + 0xE0..0xFD (30) = 64개.
0x0E..0x1F 도 써 봤으나 그 코드를 받은 글자가 화면에서 사라졌다. 렌더러 본체의
cmpi 전수 조사로는 특수 취급이 안 보였지만 원인 미확인이라 쓰지 않는다.
가나 구간(0xA1..0xDF)과 ASCII(0x20..0x7D)는 건드리지 않아 다른 화면의
일본어가 보존된다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asm import build_uploader_a1  # noqa: E402

SRC = Path("/Users/rotein/Downloads/Langrisser.md")
VRAM = Path("work/Mega Drive/Langrisser-vdp-vram-20260811-151039.bin")
G7_BIN = Path("font/galmuri7/font-007242d37349daf3.bin")
G7_MAP = Path("font/galmuri7/font-007242d37349daf3_glyph_map.json")
KO_TSV = Path("translation/ko.tsv")

ROM_SIZE = 0x100000
UPLOADER_AT, KFONT_AT, TEXT_AT = 0x80000, 0x81000, 0x90000
HOOK_SITE, STRDRAW, TABLE_AT = 0x18D12, 0x5F60, 0x62BC
SLOT_BASE = 128
CODES = list(range(0x7F, 0xA1)) + list(range(0xE0, 0xFE))   # 64개
BG, INK = 13, 15

# (ko.tsv id, 포인터 테이블, 인덱스)  — 그려지는 순서대로
PARTS = [("stage-01", 0x38A38, 0), ("prologue-01", 0x38BF2, 0), ("cond-01", 0x3962E, 0)]
FROM_VRAM = {"。": 129, "「": 130, "」": 131}
ASCII_OK = set(" 1234567890.()")          # 게임 ASCII 폰트로 그린다


def to_4bpp(g8: bytes) -> bytes:
    out = bytearray()
    for y in range(8):
        row = g8[y]
        for k in range(4):
            hi = INK if row >> (7 - k * 2) & 1 else BG
            lo = INK if row >> (6 - k * 2) & 1 else BG
            out.append((hi << 4) | lo)
    return bytes(out)


def pick(row_id: str) -> str:
    for ln in KO_TSV.read_text().rstrip("\n").split("\n")[1:]:
        c = ln.split("\t")
        if c[0] == row_id:
            return c[2].replace("\\n", "\n")
    raise SystemExit(f"ko.tsv 에 id={row_id} 없음")


def main() -> None:
    rom = bytearray(SRC.read_bytes())
    rom.extend(b"\xff" * (ROM_SIZE - len(rom)))
    vram, font = VRAM.read_bytes(), G7_BIN.read_bytes()
    gmap = json.loads(G7_MAP.read_text())

    texts = {pid: pick(pid) for pid, _, _ in PARTS}

    # 세 문자열 글리프의 합집합 — 등장 순서가 슬롯 순서
    slots: dict[str, int] = {}
    for pid, _, _ in PARTS:
        for ch in texts[pid]:
            if ch not in ASCII_OK and ch != "\n" and ch not in slots:
                slots[ch] = len(slots)
    if len(slots) > min(len(CODES), 256 - SLOT_BASE):
        raise SystemExit(f"글리프 {len(slots)} > 코드 {len(CODES)}")

    # 글리프 테이블 (ID = 슬롯 번호)
    table = bytearray()
    for ch in slots:
        if ch in FROM_VRAM:
            t = FROM_VRAM[ch]
            table += vram[t * 32:(t + 1) * 32]
        elif ch in gmap:
            table += to_4bpp(font[gmap[ch] * 8:gmap[ch] * 8 + 8])
        else:
            raise SystemExit(f"글리프 없음: {ch!r}")
    rom[KFONT_AT:KFONT_AT + len(table)] = table

    def encode(s: str) -> bytes:
        out = bytearray()
        for ch in s:
            if ch == "\n":
                out += b"\x0d\x0d"      # 한 줄 = 0x0D 두 개 (렌더러 Y+=1, 글리프 2행)
            elif ch in ASCII_OK:
                out.append(ord(ch))
            else:
                out.append(CODES[slots[ch]])
        out.append(0xFF)
        return bytes(out)

    # 첫 문자열만 헤더를 갖는다 (합집합 전체를 올린다)
    header = bytearray([0xFE, len(slots)])
    for i in range(len(slots)):
        header += i.to_bytes(2, "big")

    at = TEXT_AT
    for i, (pid, tbl, idx) in enumerate(PARTS):
        blob = (bytes(header) if i == 0 else b"") + encode(texts[pid])
        rom[at:at + len(blob)] = blob
        rom[tbl + idx * 4:tbl + idx * 4 + 4] = at.to_bytes(4, "big")
        print(f"  {pid:12} {at:06X}  {len(blob):3d}B  -> 포인터 {tbl:06X}[{idx}]")
        at += len(blob) + 2

    # 업로더 + 훅 (첫 draw 에만)
    want = b"\x4e\xb9" + STRDRAW.to_bytes(4, "big")
    assert rom[HOOK_SITE:HOOK_SITE + 6] == want, f"{HOOK_SITE:06X} 가 jsr ${STRDRAW:X} 아님"
    code = build_uploader_a1(kfont=KFONT_AT, slot_base=SLOT_BASE, target=STRDRAW)
    assert UPLOADER_AT + len(code) <= KFONT_AT
    rom[UPLOADER_AT:UPLOADER_AT + len(code)] = code
    rom[HOOK_SITE:HOOK_SITE + 6] = b"\x4e\xb9" + UPLOADER_AT.to_bytes(4, "big")

    for i in range(len(slots)):
        rom[TABLE_AT + CODES[i]] = SLOT_BASE + i

    rom[0x1A4:0x1A8] = (ROM_SIZE - 1).to_bytes(4, "big")
    rom[0x18E] = rom[0x18F] = 0

    out = Path("work/korom_screen.md")
    out.write_bytes(rom)
    print(f"\n글리프 합집합  {len(slots)}개 / 코드 {len(CODES)}개 / 슬롯 {256-SLOT_BASE}개")
    print(f"업로더        {UPLOADER_AT:06X}  {len(code)}B")
    print(f"훅            {HOOK_SITE:06X}  jsr {STRDRAW:06X} -> jsr {UPLOADER_AT:06X}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
