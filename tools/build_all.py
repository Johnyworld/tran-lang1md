#!/usr/bin/env python3
"""20스테이지 프롤로그 화면 전체를 한글로 빌드한다.

build_screen.py 를 20스테이지로 일반화한 것. 핵심 설계 변경은 **글리프 테이블을
전역으로** 둔 것이다.

  - 전역 글리프 테이블: 20스테이지에 쓰이는 모든 글리프를 모아 ID 를 부여
  - 스테이지별 헤더: 그 화면이 쓰는 글리프의 **전역 ID** 목록 (최대 64개)
    ID 는 7비트 두 바이트로 담아 0xFF 가 섞이지 않게 한다
  - `$62BC`: 코드 -> 타일(SLOT_BASE+i) 매핑은 모든 스테이지가 같으므로 한 번만 설정

덕분에 업로더도 하나, 테이블도 하나면 된다. 화면이 바뀔 때 달라지는 것은
VRAM 타일의 **내용**뿐이다.

한 화면은 세 문자열을 그린다 (렌더러 0x18CE8). 첫 draw(0x18D12)에 훅을 걸어
그 화면 세 문자열 글리프의 합집합을 한 번에 올린다. 네임테이블은 타일 번호만
들고 있어 나중에 픽셀을 바꾸면 먼저 그려진 글자 모양까지 바뀌므로, 한 화면에
동시에 보이는 문자열은 하나의 타일 배정을 공유해야 한다.
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
LABEL_BIN = Path("font/dunggeunmo/font-6883cc1477b4cbfa.bin")
LABEL_MAP = Path("font/dunggeunmo/font-6883cc1477b4cbfa_glyph_map.json")
KO_TSV = Path("translation/ko.tsv")

ROM_SIZE = 0x100000
UPLOADER_AT, LABEL_AT, KFONT_AT, TEXT_AT = 0x80000, 0x80400, 0x81000, 0xA0000
HOOK_SITE, STRDRAW, TABLE_AT = 0x18D12, 0x5F60, 0x62BC
SLOT_BASE = 128
CODES = list(range(0x7F, 0xA1)) + list(range(0xE0, 0xFE))   # 64개
BG, INK, OUTLINE = 13, 15, 14

TABLES = {"stage": 0x38A38, "prologue": 0x38BF2, "cond": 0x3962E}
KINDS = ["stage", "prologue", "cond"]          # 그려지는 순서
LABEL_DST, LABEL_TILES, LABEL_Y = 522 * 32, 20, 4
LABEL_TOP, LABEL_BOTTOM = "승리", "패배"
FROM_VRAM = {"。": 129, "「": 130, "」": 131, "、": 132, "・": 133}  # 게임 폰트의 가나 블록
ASCII_OK = set(" 1234567890.,()-!?")   # 게임 ASCII 폰트로 그린다


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
    """승리/패배 를 32x40px 4bpp 타일 20개로. 16x16 한글은 획 간격이 좁아
    외곽선·그림자를 넣으면 획이 붙으므로 장식하지 않는다."""
    font, gmap = LABEL_BIN.read_bytes(), json.loads(LABEL_MAP.read_text())
    W, H = 32, 40
    ink = [[False] * W for _ in range(H)]
    for row, word in ((LABEL_Y, LABEL_TOP), (16 + LABEL_Y, LABEL_BOTTOM)):
        for i, ch in enumerate(word):
            o = gmap[ch] * 32
            for y in range(16):
                bits = (font[o + y * 2] << 8) | font[o + y * 2 + 1]
                for x in range(16):
                    if bits >> (15 - x) & 1:
                        ink[row + y][i * 16 + x] = True
    out = bytearray()
    for tr in range(H // 8):
        for tc in range(W // 8):
            for y in range(8):
                for k in range(4):
                    px = [INK if ink[tr * 8 + y][tc * 8 + k * 2 + j] else BG
                          for j in range(2)]
                    out.append((px[0] << 4) | px[1])
    return bytes(out)


def load_ko() -> dict[str, str]:
    out = {}
    for ln in KO_TSV.read_text().rstrip("\n").split("\n")[1:]:
        c = ln.split("\t")
        if len(c) >= 3 and c[2]:
            out[c[0]] = c[2].replace("\\n", "\n")
    return out


def main() -> None:
    rom = bytearray(SRC.read_bytes())
    rom.extend(b"\xff" * (ROM_SIZE - len(rom)))
    vram = VRAM.read_bytes()
    g7, g7map = G7_BIN.read_bytes(), json.loads(G7_MAP.read_text())
    ko = load_ko()

    # 번역이 있는 스테이지만 처리 (나머지는 원문 그대로 남는다)
    stages = [s for s in range(1, 21)
              if all(f"{k}-{s:02d}" in ko for k in KINDS)]
    if not stages:
        raise SystemExit("번역된 스테이지가 없다 (translation/ko.tsv)")

    # 전역 글리프 테이블 — 전 스테이지의 합집합
    gid: dict[str, int] = {}
    for s in stages:
        for k in KINDS:
            for ch in ko[f"{k}-{s:02d}"]:
                if ch not in ASCII_OK and ch != "\n" and ch not in gid:
                    gid[ch] = len(gid)
    table = bytearray()
    for ch in gid:
        if ch in FROM_VRAM:
            t = FROM_VRAM[ch]
            table += vram[t * 32:(t + 1) * 32]
        elif ch in g7map:
            table += to_4bpp(g7[g7map[ch] * 8:g7map[ch] * 8 + 8])
        else:
            raise SystemExit(f"글리프 없음: {ch!r}")
    rom[KFONT_AT:KFONT_AT + len(table)] = table

    labels = make_labels()
    rom[LABEL_AT:LABEL_AT + len(labels)] = labels

    want = b"\x4e\xb9" + STRDRAW.to_bytes(4, "big")
    assert rom[HOOK_SITE:HOOK_SITE + 6] == want, f"{HOOK_SITE:06X} 가 jsr ${STRDRAW:X} 아님"
    code = build_uploader_labels(kfont=KFONT_AT, slot_base=SLOT_BASE, target=STRDRAW,
                                 label_src=LABEL_AT, label_dst=LABEL_DST,
                                 label_tiles=LABEL_TILES)
    assert UPLOADER_AT + len(code) <= LABEL_AT, "업로더가 라벨 데이터와 겹친다"
    rom[UPLOADER_AT:UPLOADER_AT + len(code)] = code
    rom[HOOK_SITE:HOOK_SITE + 6] = b"\x4e\xb9" + UPLOADER_AT.to_bytes(4, "big")

    # 코드 -> 타일 매핑은 전 스테이지 공통이므로 한 번만
    for i in range(len(CODES)):
        rom[TABLE_AT + CODES[i]] = SLOT_BASE + i

    at = TEXT_AT
    print(f"{'st':>3}  {'글리프':>5}  {'바이트':>6}   위치")
    over = []
    for s in stages:
        texts = {k: ko[f"{k}-{s:02d}"] for k in KINDS}
        slots: dict[str, int] = {}
        for k in KINDS:
            for ch in texts[k]:
                if ch not in ASCII_OK and ch != "\n" and ch not in slots:
                    slots[ch] = len(slots)
        if len(slots) > len(CODES):
            over.append((s, len(slots)))

        def enc(t: str) -> bytes:
            out = bytearray()
            for ch in t:
                if ch == "\n":
                    out += b"\x0d\x0d"          # 시각적 한 줄 = 0x0D 두 개
                elif ch in ASCII_OK:
                    out.append(ord(ch))
                else:
                    out.append(CODES[slots[ch]])
            out.append(0xFF)
            return bytes(out)

        # 글리프 ID 는 7비트 두 바이트 (ID = (b0<<7)|b1). 두 바이트 모두 0x80
        # 미만이므로 0xFF 가 절대 나오지 않는다 — 게임이 메시지를 건너뛸 때
        # 0xFF 를 바이트 단위로 훑기 때문(0x15470)에 반드시 지켜야 한다.
        header = bytearray([0xFE, len(slots)])
        for ch in slots:
            g = gid[ch]
            if g > 0x3FFF:
                raise SystemExit(f"글리프 ID {g} 가 14비트를 넘는다")
            header += bytes([g >> 7, g & 0x7F])

        start, total = at, 0
        for i, k in enumerate(KINDS):
            blob = (bytes(header) if i == 0 else b"") + enc(texts[k])
            rom[at:at + len(blob)] = blob
            t = TABLES[k]
            rom[t + (s - 1) * 4:t + (s - 1) * 4 + 4] = at.to_bytes(4, "big")
            at += len(blob) + 2
            total += len(blob)
        mark = "✗" if len(slots) > len(CODES) else " "
        print(f"{s:3d}  {len(slots):3d}/{len(CODES)}{mark} {total:6d}   {start:06X}")

    rom[0x1A4:0x1A8] = (ROM_SIZE - 1).to_bytes(4, "big")
    rom[0x18E] = rom[0x18F] = 0

    out = Path("work/korom_all.md")
    out.write_bytes(rom)
    print(f"\n스테이지 {len(stages)}개 / 전역 글리프 {len(gid)}개 ({len(table)}B)")
    print(f"업로더 {UPLOADER_AT:06X} {len(code)}B / 라벨 {LABEL_AT:06X} / "
          f"글리프 {KFONT_AT:06X} / 텍스트 {TEXT_AT:06X}~{at:06X}")
    if over:
        print(f"\n✗ 코드 초과: {over}  — 어휘를 줄이거나 CODES 를 늘려야 한다")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
