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
from asm import build_uploader_labels  # noqa: E402

SRC = Path("/Users/rotein/Downloads/Langrisser.md")
VRAM = Path("work/Mega Drive/Langrisser-vdp-vram-20260811-151039.bin")
G7_BIN = Path("font/galmuri7/font-007242d37349daf3.bin")
G7_MAP = Path("font/galmuri7/font-007242d37349daf3_glyph_map.json")
# 라벨 전용 폰트. Galmuri11 은 16px 에서 `ㅂ+ㅐ` 가 무너져 `배`가 `버`로 읽힌다.
# 배/버 픽셀 차이로 후보를 줄였다 — Galmuri11 9(구분 불가) / 프리텐다드 일반 38 /
# 둥근모꼴 50 / 프리텐다드 Bold 69. 둥근모꼴은 획이 1px 로 가늘면서 자모가 셀을
# 꽉 채워, 원본 한자의 큰 인상에 가깝고 Bold 처럼 뭉치지도 않는다.
# 픽셀 전용 폰트가 아니어도 자모 간격이 넓으면 16px 에서 더 잘 읽힌다.
LABEL_BIN = Path("font/dunggeunmo/font-6883cc1477b4cbfa.bin")
LABEL_MAP = Path("font/dunggeunmo/font-6883cc1477b4cbfa_glyph_map.json")

# 勝利/敗北 라벨 — VRAM 타일 522..541 (4칸 x 5행 = 32x40px), 행 우선
# 원본은 타일당 16바이트 2플레인(색상15 마스크 + 색상14+15 합집합)이지만
# 그 형식을 알 필요가 없다. 우리 비압축 4bpp 타일로 같은 자리를 덮어쓴다.
LABEL_DST, LABEL_TILES = 522 * 32, 20
LABEL_TOP, LABEL_BOTTOM = "승리", "패배"
OUTLINE = 14
# Galmuri11 글리프는 16px 셀 안에서 잉크가 y=3..12 에 있다. y=0/16 에 그대로 두면
# 라벨이 조건문(화면 행 15·17)보다 4px 위로 치우친다. 그만큼 내려 맞춘다.
LABEL_Y = 4
KO_TSV = Path("translation/ko.tsv")

ROM_SIZE = 0x100000
UPLOADER_AT, KFONT_AT, LABEL_AT, TEXT_AT = 0x80000, 0x81000, 0x82000, 0x90000
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


def make_labels() -> bytes:
    """승리/패배 를 32x40px 4bpp 타일 20개로. 원본처럼 색상 14 외곽선을 넣는다."""
    font = LABEL_BIN.read_bytes()
    gmap = json.loads(LABEL_MAP.read_text())
    W, H = 32, 40
    ink = [[False] * W for _ in range(H)]
    for row, word in ((LABEL_Y, LABEL_TOP), (16 + LABEL_Y, LABEL_BOTTOM)):
        for i, ch in enumerate(word):
            o = gmap[ch] * 32
            for y in range(16):
                hi, lo = font[o + y * 2], font[o + y * 2 + 1]
                bits = (hi << 8) | lo
                for x in range(16):
                    if bits >> (15 - x) & 1:
                        ink[row + y][i * 16 + x] = True
    # 외곽선·그림자를 넣지 않는다.
    #   사방 외곽선 -> 획이 깨져 보임
    #   Bold        -> 뭉침
    #   우하단 그림자 -> `ㅐ` 의 두 세로획 사이 틈을 메워 `ㅓ` 로 읽힘
    # 16x16 한글의 획 간격이 좁아 어떤 장식도 획을 붙여버린다. 순수 잉크가 답이다.
    edge = [[False] * W for _ in range(H)]
    out = bytearray()
    for tr in range(H // 8):
        for tc in range(W // 8):
            for y in range(8):
                for k in range(4):
                    px = []
                    for j in range(2):
                        gx, gy = tc * 8 + k * 2 + j, tr * 8 + y
                        px.append(INK if ink[gy][gx] else (OUTLINE if edge[gy][gx] else BG))
                    out.append((px[0] << 4) | px[1])
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
    labels = make_labels()
    rom[LABEL_AT:LABEL_AT + len(labels)] = labels
    code = build_uploader_labels(kfont=KFONT_AT, slot_base=SLOT_BASE, target=STRDRAW,
                                 label_src=LABEL_AT, label_dst=LABEL_DST,
                                 label_tiles=LABEL_TILES)
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
    print(f"라벨 타일     {LABEL_AT:06X}  {len(labels)}B ({LABEL_TILES}타일) -> VRAM {LABEL_DST:04X}")
    print(f"업로더        {UPLOADER_AT:06X}  {len(code)}B")
    print(f"훅            {HOOK_SITE:06X}  jsr {STRDRAW:06X} -> jsr {UPLOADER_AT:06X}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
