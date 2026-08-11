#!/usr/bin/env python3
"""동적 글리프 업로드 방식 빌드. 롬을 1MB 로 확장하고 새 68000 루틴을 넣는다.

구조
----
  0x80000   업로더 루틴 (tools/asm.py)
  0x80200   한글 글리프 테이블 — MD 4bpp 8x8, 32바이트/글리프
  0x90000   이설한 메시지
  0x15576   훅 (렌더러 첫 명령 6바이트를 jmp 로 교체)
  $62BC     우리가 쓰는 코드만 타일로 매핑한다.

메시지 형식
-----------
  [0xFE][N: byte][글리프 ID: word x N][텍스트 바이트...][0xFF]

  0xFE 는 업로더가 헤더를 알아보는 마커다.
  텍스트 코드는 일본어가 쓰지 않는 구간에서만 고른다 —
  ASCII 0x20..0x7D, 가나 0xA1..0xDF 를 건드리면 남은 일본어가 깨진다.
  여유 구간: 0x7F..0xA0 (34개) + 0xE0..0xFD (30개) = 64개.

메시지 시작 시 업로더가 글리프 N개를 VRAM 타일 128.. 로 올린다.
따라서 한 메시지가 쓸 수 있는 고유 음절은 94자이며, 대본 전체의 음절 수와
무관해진다. 이것이 37자 제약을 없애는 지점이다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asm import build_hook, build_uploader  # noqa: E402

SRC = Path("/Users/rotein/Downloads/Langrisser.md")
VRAM = Path("work/Mega Drive/Langrisser-vdp-vram-20260811-151039.bin")
G7_BIN = Path("font/galmuri7/font-007242d37349daf3.bin")
G7_MAP = Path("font/galmuri7/font-007242d37349daf3_glyph_map.json")
KO_TSV = Path("translation/ko.tsv")

ROM_SIZE = 0x100000
UPLOADER_AT, KFONT_AT, MSG_AT = 0x80000, 0x80200, 0x90000
# 텍스트 렌더 경로가 둘이다. 프롤로그는 0x15650 쪽을 쓴다.
#   0x15568 의 beq 가 항상 성립해 실행이 0x15650 으로 가므로 0x15576 만 걸면 안 걸린다.
# 두 경로 모두 첫 명령이 movea.l $E818,a1 (6바이트) 이라 같은 루틴을 재사용한다.
HOOKS = [(0x15576, 0x1557C), (0x15650, 0x15656)]
TABLE_AT = 0x62BC
PTR_TABLE, PTR_INDEX = 0x38BF2, 0            # 스테이지 프롤로그 0번
SLOT_BASE = 128
CODES = list(range(0x7F, 0xA1)) + list(range(0xE0, 0xFE))
SLOT_MAX = len(CODES)
BG, INK = 13, 15                             # 기존 폰트와 같은 색 (배경 13 / 글자 15)

# 게임 폰트에만 있는 문자는 원본 VRAM 타일에서 그대로 가져온다
FROM_VRAM = {"。": 129, "「": 130, "」": 131}


def to_4bpp(g8: bytes) -> bytes:
    """8x8 1bpp -> MD 4bpp 타일 32바이트."""
    out = bytearray()
    for y in range(8):
        row = g8[y]
        for k in range(4):
            hi = INK if row >> (7 - k * 2) & 1 else BG
            lo = INK if row >> (6 - k * 2) & 1 else BG
            out.append((hi << 4) | lo)
    return bytes(out)


def pick_kr(row_id: str) -> str:
    """ko.tsv 에서 id 로 번역문을 고른다.

    같은 화면의 번역이 방식별로 둘 있다 — 정적 8x8 은 안전 타일 40개 제약 때문에
    축약판을, 동적 업로드는 제약이 없으니 완전판을 쓴다.
    """
    for ln in KO_TSV.read_text().rstrip("\n").split("\n")[1:]:
        c = ln.split("\t")
        if c[0] == row_id:
            return c[2]
    raise SystemExit(f"ko.tsv 에 id={row_id} 없음")


def main() -> None:
    rom = bytearray(SRC.read_bytes())
    rom.extend(b"\xff" * (ROM_SIZE - len(rom)))          # 1MB 로 확장
    vram = VRAM.read_bytes()
    font = G7_BIN.read_bytes()
    gmap = json.loads(G7_MAP.read_text())

    kr = pick_kr("prologue-01")
    lines = kr.split("\\n")

    # 이 메시지가 쓰는 글리프를 모은다 (등장 순서 = 슬롯 순서)
    slots: dict[str, int] = {}
    for ch in kr.replace("\\n", ""):
        if ch != " " and ch not in slots:
            slots[ch] = len(slots)
    if len(slots) > SLOT_MAX:
        raise SystemExit(f"고유 글리프 {len(slots)} > 코드 {SLOT_MAX}")

    # 글리프 테이블
    table = bytearray()
    for ch in slots:
        if ch in FROM_VRAM:
            t = FROM_VRAM[ch]
            table += vram[t * 32:(t + 1) * 32]           # 원본 타일 그대로
        elif ch in gmap:
            table += to_4bpp(font[gmap[ch] * 8:gmap[ch] * 8 + 8])
        else:
            raise SystemExit(f"글리프 없음: {ch!r}")
    rom[KFONT_AT:KFONT_AT + len(table)] = table

    # 업로더 + 훅
    for i, (site, resume) in enumerate(HOOKS):
        assert rom[site:site + 6] == b"\x22\x79\xff\xff\xe8\x18", \
            f"{site:06X} 의 첫 명령이 movea.l $E818,a1 가 아니다"
        at = UPLOADER_AT + i * 0x100
        code = build_uploader(kfont=KFONT_AT, slot_base=SLOT_BASE,
                              p_work=0xFFFFE818, resume=resume)
        rom[at:at + len(code)] = code
        hook = build_hook(at)
        assert len(hook) == 6
        rom[site:site + 6] = hook
        print(f"훅            {site:06X} -> {at:06X}  (resume {resume:06X})")

    # $62BC — 우리 코드만 타일로. 일본어 구간(0xA1..0xDF)은 손대지 않는다.
    for i in range(len(slots)):
        rom[TABLE_AT + CODES[i]] = SLOT_BASE + i

    # 메시지 조립
    msg = bytearray([0xFE, len(slots)])          # 마커 + 글리프 수
    for ch in slots:
        msg += (slots[ch]).to_bytes(2, "big")            # 글리프 ID = 슬롯 순서
    for i, line in enumerate(lines):
        if i:
            msg += b"\x0d\x0d"
        for ch in line:
            msg.append(0x20 if ch == " " else CODES[slots[ch]])
    msg.append(0xFF)
    rom[MSG_AT:MSG_AT + len(msg)] = msg

    # 포인터를 이설한 자리로
    rom[PTR_TABLE + PTR_INDEX * 4:PTR_TABLE + PTR_INDEX * 4 + 4] = MSG_AT.to_bytes(4, "big")

    rom[0x1A4:0x1A8] = (ROM_SIZE - 1).to_bytes(4, "big")  # 헤더 롬 끝 주소
    rom[0x18E] = rom[0x18F] = 0                           # 체크섬 검사 우회

    out = Path("work/korom_dynamic.md")
    out.write_bytes(rom)
    print(f"롬 확장       {len(rom):,} bytes (1MB)")
    print(f"글리프 테이블  {KFONT_AT:06X}  {len(slots)}개 x 32B = {len(table)}B")
    print(f"메시지        {MSG_AT:06X}  {len(msg)}B (헤더 {2+2*len(slots)}B + 본문)")
    print(f"포인터        {PTR_TABLE:06X}[{PTR_INDEX}] -> {MSG_AT:06X}")
    print(f"\n고유 글리프 {len(slots)}개 / 사용 가능 코드 {SLOT_MAX}개")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
