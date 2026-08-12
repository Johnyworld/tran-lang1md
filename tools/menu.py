#!/usr/bin/env python3
"""메뉴 그래픽 한글화 — 글리프 풀을 다시 굽고 타일맵 서술자를 다시 쓴다.

메뉴는 문자열이 아니다
----------------------
유닛 명령 메뉴 같은 것은 폰트로 그려지지 않는다. **미리 그려둔 텍스트 그래픽**을
타일 단위로 잘라 네임테이블에 늘어놓는다. 그래서 `$62BC` 코드표도, 글리프
업로더도 여기서는 쓸 수 없다.

```
리소스 0x7D   롬 0x5D7BA, 4bpp 비압축 252타일  -> VRAM 0xA000 (타일 1280)
              0x6F38 이 로드한다 (전투 화면)
서술자        창 레코드 +8 이 가리키는 블록. +4 = 타일 베이스, +8 부터 $5CDC 서술자
```

풀은 **8px 열 단위로 중복 제거된 텍스트 띠**다. 한자는 16px(2열), 가나는 8px(1열)
이고, 서술자가 필요한 열만 골라 붙인다. `データ` 의 `ー` 는 `ロード` 의 것을
재사용한다. 그래서 "글자 하나를 한글로 바꾼다" 는 발상이 통하지 않는다 —
`動` 을 `동` 으로 바꾸면 `手動`·`半自動` 까지 같이 바뀌고, 장음부호는 애초에
1:1 대응이 없다.

대신 **풀과 서술자를 둘 다 우리가 다시 쓴다.** 서술자가 임의의 타일 번호를
임의의 칸에 놓을 수 있으므로 한글 음절(16x16 = 타일 4개)을 풀 어디에 두든 된다.
인접 조건이 없다 — 조각난 빈 자리를 그대로 쓸 수 있다.

$5CDC 서술자 문법 (0x5CDC 실측)
-------------------------------
```
바이트 < 0xFA   타일 = 베이스 + 바이트, d5(뒤집기) OR, $9126 XOR
0xFA..0xFD      뒤집기 없음 / 가로 / 세로 / 양쪽
0xFE nn         다음 바이트를 nn 번 반복
0xFF            끝
블록 +8 의 첫 워드가 2 면 열 우선(세로로 먼저), 1 이면 행 우선
```

건드리지 않는 것
----------------
`030A1A` 는 어느 풀과 함께 그려지는지 확정하지 못했다. 이 풀로 렌더하면 가운데
줄이 `件ブ` 로 깨지는데, 다른 풀(0xB1/0xB2/0xB3 — 압축, 0xA000 에 로드되는
다른 리소스들)과 짝일 가능성이 있다. 그래서 서술자를 그대로 두고 그 줄이 쓰는
풀 오프셋을 **원본 픽셀로 고정**한다. 어느 쪽이 맞든 지금과 같게 동작한다.

같은 이유로 **어떤 서술자도 참조하지 않는 오프셋 21개도 고정**한다. `ロード`
`セーブ` 열이 거기 있는데 서술자가 아닌 경로로 그려지는 것으로 보인다.
"안 쓰는 것 같다" 는 판단으로 타일을 덮어써서 이미 한 번 당했다(STATUS 의
스테이지 번호 `1` 사고).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

POOL_HDR = 0x5D7B6            # 0001 FC 00 = 비압축 252타일
POOL_AT, POOL_TILES = 0x5D7BA, 252
POOL_BASE_TILE = 1280         # VRAM 타일 번호
BLANK = 45                    # 균일 색13 타일 — 원본이 여백에 쓰는 것
MAX_CELL = 0xF9               # 서술자 바이트는 0xFA 부터 제어코드
BG, INK = 13, 15              # 원본 풀이 쓰는 두 색 (색0 = 투명, 320px 뿐)
GLYPH_Y = 1                   # 원본 한자 잉크는 y=2..13, 둥근모꼴은 1..13

LABEL_BIN = Path("font/dunggeunmo/font-6883cc1477b4cbfa.bin")
LABEL_MAP = Path("font/dunggeunmo/font-6883cc1477b4cbfa_glyph_map.json")
MENU_TSV = Path("translation/menu.tsv")

UNTOUCHED = {0x030A1A}        # 문맥 미확인 — 서술자를 건드리지 않는다

# ---------------------------------------------------------------- 선택 창 제목
# 두 번째 풀. 리소스 0x81 -> VRAM 0x3800 (타일 448) 이고 **압축**이다. 풀 필요가
# 없다 — 게임이 올린 직후 그 자리를 우리 비압축 타일로 덮는다(승리/패배 라벨과
# 같은 방법). 그래서 리소스 로드 `jsr $53B4` 세 곳에 훅을 건다.
TITLE_BASE_TILE = 448
TITLE_OFF = 98                # 네 제목이 쓰는 오프셋 98..159 의 앞부터 쓴다
TITLE_RES = 0x81              # 이 리소스가 올라올 때마다 우리 타일로 덮는다
TITLE_VRAM = 0x3800           # 리소스 0x81 이 올라가는 VRAM 주소 (타일 448)
# 예전에는 `move.w #$81,d1` 이 보이는 로드 지점 세 곳(0x1181C·0x18C9C·0x19038)에
# 훅을 걸었다. 리소스 번호를 레지스터로 넘기는 자리를 놓치므로(출전 준비 화면에서
# 지휘관선택이 원문으로 나왔다) 로더 꼬리 한 곳으로 옮겼다 — asm.build_uploader_res.
GRAPHLOAD_TAIL = 0x53D2       # movem.l (a7)+, d1-d2/a1 + rts (6바이트)
TITLE_RECS = (0x030FEE, 0x03104C, 0x0310A6, 0x038800)

# ---------------------------------------------------------------- 전투씬 라벨
# `基本能力` `指揮修正` `レベル修正` `地形効果`. 넷이 **서술자 하나를 공유**하고
# 베이스만 30씩 옮긴다 (`0x0F8FE`: d4 = 0x8588 + 라벨 x 30, 서술자 `0xFB10` 10x3).
# 그래서 서술자는 손댈 것이 없고 **타일 픽셀만** 갈아 넣으면 된다.
#
# 프레임까지 한 덩이(10x3 = 80x24px)라 원본 픽셀이 필요했다. VRAM 덤프에서 떠 온다.
#   프레임  y0..3 / y19..22, x0..3 / x76..79
#   판 내부 배경 색 2, 글자 영역 x4..75 y5..18 (원본 한자는 색 e/f/7/3 음영)
BATTLE_BASE, BATTLE_N, BATTLE_STRIDE = 1416, 4, 30
BATTLE_W, BATTLE_H = 10, 3
BATTLE_RES, BATTLE_VRAM = 0x7E, 0xB100       # 리소스 0x7E -> VRAM 0xB100 (0x0E078)
BATTLE_PLATE = 2                             # 판 내부 배경 색
BATTLE_BOX = (4, 76, 4, 19)                  # x0, x1, y0, y1 (글자를 지우고 그릴 범위)
BATTLE_DUMP = Path("work/Mega Drive/korom_debug-vdp-vram-20260812-130157.bin")

# ---------------------------------------------------------------- 출전 준비 라벨
# `指揮官選択`(타일 256) / `位置選択`(타일 272). 서술자 `0x30F70`(8x2) 하나를 두 호출이
# 베이스만 바꿔 쓴다. 타일 256..287 이 어느 리소스 소유인지 정적으로 못 갈랐다
# (리소스 3 과 0x82 가 둘 다 VRAM 0x2000 에 올라오고 둘 다 압축이다). 그래서 로드
# 시점이 아니라 **그리기 직전**(`jsr $5CDC` 자리)에 올린다 — 소유권을 몰라도 된다.
DEPLOY_SITES = ((0x11136, 256, 0), (0x1118E, 272, 1))    # (호출 자리, 베이스 타일, ko 행)
DEPLOY_W, DEPLOY_H = 8, 2
DEPLOY_DUMP = Path("work/Mega Drive/korom_debug-vdp-vram-20260812-130320.bin")
DEPLOY_BG = 13                               # 창 내부 색
TILEMAP = 0x5CDC

# -------------------------------------------------------------- 대상 선택 라벨 4개
# 정보창 우하단의 `移動先選択` / `攻擊先選択` / `移動できません` / `攻擊できません`.
# 창 레코드도 서술자도 아니라 **코드가 네임테이블에 직접 쓴다** (`0x0D0AA`: 주소
# 0xDC38 부터 타일 362 를 1씩 증가시키며 10칸 x 2줄). 그래서 tilescan(=$5CDC 호출
# 훑기)에 안 걸렸고 실기 스크린샷으로 잡았다.
#
# 처음엔 그리기 직후(`jsr $4A74` 자리)를 훅해 20타일을 올렸다. 그런데 이동 모드
# 스크린샷에서 일본어가 그대로였다 — **네 라벨이 같은 타일 362..381 을 돌려쓰고
# 게임이 모드마다 픽셀을 갈아 올린다.** 두 덤프의 네임테이블이 똑같이 362..381 인데
# 픽셀만 다른 것이 근거다.
#
# 그 픽셀 출처를 덤프 -> 롬 바이트 검색으로 찾았다. **리소스 0x83** (표 0x3A610,
# `0x60EEE` = `0001 50 00` 비압축 80타일) 안에 20타일씩 4개가 나란히 있다. 그래서
# 훅을 걷고 **롬 데이터를 제자리에서 갈아치운다** — 올리는 경로가 무엇이든 덮인다.
TARGET_RES_DATA = 0x60EF2        # 리소스 0x83 헤더(0x60EEE) + 4
TARGET_W, TARGET_H, TARGET_N = 10, 2, 4
TARGET_STRIDE = TARGET_W * TARGET_H * 32     # 20타일 = 0x280
ATTACK_BG = 13                   # 배경 13 / 글자 15 (원본 데이터 실측)
GRAPHLOAD = 0x53B4


def u16(b: bytes, p: int) -> int:
    return int.from_bytes(b[p:p + 2], "big")


def blocks(src: bytes) -> list[int]:
    """풀 0x7D 를 쓰는 서술자 블록의 주소들. 창 레코드 +8 이 가리키는 자리다."""
    out = []
    for p in range(0, len(src) - 16, 2):
        if (u16(src, p) == 0x8500 or u16(src, p) == 0x8520) and u16(src, p + 2) == 0 \
                and u16(src, p + 4) in (1, 2) and 0 < u16(src, p + 6) <= 40 \
                and 0 < u16(src, p + 8) <= 32:
            out.append(p - 4)
    return out


def decode(src: bytes, ptr: int,
           base_tile: int = POOL_BASE_TILE) -> tuple[int, int, int, list[list[int]], int]:
    """블록 -> (베이스타일, w, h, 그리드[행][열] = 풀 오프셋, 서술자 길이)."""
    base = u16(src, ptr + 4) & 0x7FF
    order, w, h = u16(src, ptr + 8), u16(src, ptr + 10), u16(src, ptr + 12)
    p, rep, cells, flip = ptr + 14, 0, [], 0
    while len(cells) < w * h:
        b = src[p]
        if b == 0xFF:
            raise SystemExit(f"{ptr:06X}: 칸이 모자란 채 0xFF ({len(cells)}/{w*h})")
        if b < 0xFA:
            cells.append(b)
            if rep:
                rep -= 1
            else:
                p += 1
        elif b <= 0xFD:
            # 0xFA = 뒤집기 해제. $5CDC 가 루프 전에 d5 를 지우므로 그게 기본값이고,
            # 원본 서술자들은 0xFA 만 쓴다(실제 뒤집기는 없다). 우리 인코더는
            # 기본값에 의존해 아무것도 내보내지 않는다.
            flip = b - 0xFA
            if flip:
                raise SystemExit(f"{ptr:06X}: 뒤집기 {flip} 은 처리하지 않는다")
            p += 1
        else:
            rep = src[p + 1] - 1
            p += 2
    assert src[p] == 0xFF, f"{ptr:06X}: 서술자 끝이 0xFF 가 아니다"
    off = base - base_tile
    grid = [[0] * w for _ in range(h)]
    for i, c in enumerate(cells):
        r, col = (i % h, i // h) if order == 2 else (i // w, i % w)
        grid[r][col] = c + off
    return base, w, h, grid, p + 1 - (ptr + 8)


def encode(grid: list[list[int]], w: int, h: int, off: int) -> bytes:
    """열 우선(order 2) 서술자. 3칸 이상 같은 값이면 0xFE 로 줄인다."""
    seq = [grid[r][c] - off for c in range(w) for r in range(h)]
    for v in seq:
        if not 0 <= v <= MAX_CELL:
            raise SystemExit(f"칸 값 {v} 이 0..{MAX_CELL} 를 벗어난다")
    out, i = bytearray(), 0
    while i < len(seq):
        j = i
        while j < len(seq) and seq[j] == seq[i]:
            j += 1
        n = j - i
        if n >= 3:
            out += bytes([0xFE, n, seq[i]])
        else:
            out += bytes([seq[i]]) * n
        i = j
    return bytes(out) + b"\xff"


def rows_of(grid: list[list[int]], h: int) -> list[tuple[list[int], list[int]]]:
    """타일 행 두 개 = 16px 글자 한 줄. (위 오프셋들, 아래 오프셋들)."""
    assert h % 2 == 0, "높이가 홀수인 서술자"
    return [(grid[r], grid[r + 1]) for r in range(0, h, 2)]


def load_ko() -> dict[tuple[str, int], str]:
    ko = {}
    for ln in MENU_TSV.read_text().rstrip("\n").split("\n")[1:]:
        c = ln.split("\t")
        if len(c) >= 4 and c[3]:
            ko[(c[0], int(c[1]))] = c[3]
    return ko


def render_syllable(font: bytes, gmap: dict, ch: str) -> list[bytes]:
    """한글 음절 하나를 16x16 -> 4bpp 타일 4개 (TL, TR, BL, BR) 로."""
    if ch not in gmap:
        raise SystemExit(f"둥근모꼴에 글리프 없음: {ch!r}")
    ink = [[False] * 16 for _ in range(16)]
    o = gmap[ch] * 32
    for y in range(16):
        bits = (font[o + y * 2] << 8) | font[o + y * 2 + 1]
        for x in range(16):
            if bits >> (15 - x) & 1 and 0 <= y + GLYPH_Y < 16:
                ink[y + GLYPH_Y][x] = True
    out = []
    for tr, tc in ((0, 0), (0, 1), (1, 0), (1, 1)):
        px = bytearray()
        for y in range(8):
            for k in range(4):
                hi = INK if ink[tr * 8 + y][tc * 8 + k * 2] else BG
                lo = INK if ink[tr * 8 + y][tc * 8 + k * 2 + 1] else BG
                px.append((hi << 4) | lo)
        out.append(bytes(px))
    return out


def build_titles(rom: bytearray, src: bytes) -> tuple[bytes, list[str]]:
    """선택 창 제목 4개. 타일 블록을 만들고 서술자를 원본 길이 안에서 다시 쓴다.

    이 풀(리소스 0x81)은 압축이지만 풀 필요가 없다. 게임이 VRAM 에 올린 직후
    우리 비압축 타일로 덮으면 되고(`asm.build_uploader_block`), 서술자는 우리가
    올린 자리를 가리키게 고친다. 원본 제목이 쓰던 오프셋 98.. 안에서만 쓰므로
    같은 풀의 다른 그래픽(승리/패배 라벨 = 오프셋 74..93 등)은 건드리지 않는다.
    """
    ko, log = load_ko(), []
    font, gmap = LABEL_BIN.read_bytes(), json.loads(LABEL_MAP.read_text())
    tiles: list[bytes] = []
    syl: dict[str, int] = {}

    def slot(ch: str) -> int:
        if ch not in syl:
            syl[ch] = len(tiles)
            tiles.extend(render_syllable(font, gmap, ch))
        return syl[ch]

    plans = []
    for rec in TITLE_RECS:
        text = ko.get((f"{rec:06X}", 0))
        ptr = int.from_bytes(src[rec + 8:rec + 12], "big")
        base, w, h, grid, dlen = decode(src, ptr, TITLE_BASE_TILE)
        if not text:
            log.append(f"  {rec:06X}  번역 없음 — 원문 유지")
            continue
        if len(text) * 2 > w:
            raise SystemExit(f"{rec:06X} {text!r} 이 {w}칸을 넘는다 ({len(text)*2}칸)")
        plans.append((rec, ptr, base, w, h, grid, dlen, text))
        for ch in text:
            slot(ch)
    blank = len(tiles)
    tiles.append(bytes([(BG << 4) | BG]) * 32)

    for rec, ptr, base, w, h, grid, dlen, text in plans:
        top, bot = [], []
        for ch in text:
            i = TITLE_OFF + syl[ch]
            top += [i, i + 1]
            bot += [i + 2, i + 3]
        pad = w - len(top)
        grid[0] = top + [TITLE_OFF + blank] * pad
        grid[1] = bot + [TITLE_OFF + blank] * pad
        desc = (b"\x00\x02" + w.to_bytes(2, "big") + h.to_bytes(2, "big")
                + encode(grid, w, h, base - TITLE_BASE_TILE))
        if len(desc) > dlen:
            raise SystemExit(f"{rec:06X}: 서술자 {len(desc)}B 가 원본 {dlen}B 를 넘는다")
        rom[ptr + 8:ptr + 8 + len(desc)] = desc
        log.append(f"  {rec:06X}  {w}x{h}  {len(desc):3d}/{dlen}B  {text}")
    if TITLE_OFF + len(tiles) > MAX_CELL:
        raise SystemExit(f"제목 타일 {len(tiles)}개가 오프셋 {MAX_CELL} 를 넘는다")
    log.append(f"  음절 {len(syl)}개 / 타일 {len(tiles)}개 -> 풀 오프셋 "
               f"{TITLE_OFF}..{TITLE_OFF + len(tiles) - 1} (VRAM 타일 "
               f"{TITLE_BASE_TILE + TITLE_OFF}..)")
    return b"".join(tiles), log


class Pool:
    """풀 252타일을 다시 굽는다. 고정 오프셋은 원본 픽셀 그대로 남긴다."""

    def __init__(self, src: bytes, pinned: set[int]) -> None:
        self.tiles = [bytearray(src[POOL_AT + i * 32:POOL_AT + (i + 1) * 32])
                      for i in range(POOL_TILES)]
        self.free = [i for i in range(min(POOL_TILES, MAX_CELL + 1)) if i not in pinned]
        self.font = LABEL_BIN.read_bytes()
        self.gmap = json.loads(LABEL_MAP.read_text())
        self.syl: dict[str, tuple[int, int, int, int]] = {}   # 음절 -> (TL,TR,BL,BR)

    def syllable(self, ch: str) -> tuple[int, int, int, int]:
        if ch in self.syl:
            return self.syl[ch]
        if len(self.free) < 4:
            raise SystemExit(f"풀에 빈 타일이 없다 ({len(self.syl)}음절까지 넣었다)")
        slot = tuple(self.free.pop(0) for _ in range(4))
        for t, px in zip(slot, render_syllable(self.font, self.gmap, ch)):
            self.tiles[t] = bytearray(px)
        self.syl[ch] = slot
        return slot

    def bytes(self) -> bytes:
        return b"".join(self.tiles)


def build_battle_labels() -> tuple[bytes, list[str]]:
    """전투씬 라벨 4개. 원본 타일에서 글자만 지우고 한글을 그려 넣는다.

    서술자(`0xFB10`)는 넷이 공유하므로 건드리지 않는다. 타일 120개(4 x 30)를
    통째로 만들어 리소스 `0x7E` 가 올라올 때 VRAM `0xB100` 에 덮는다.
    """
    ko, log = load_ko(), []
    font, gmap = LABEL_BIN.read_bytes(), json.loads(LABEL_MAP.read_text())
    vram = BATTLE_DUMP.read_bytes()
    x0, x1, y0, y1 = BATTLE_BOX
    out = bytearray()
    for k in range(BATTLE_N):
        base = BATTLE_BASE + k * BATTLE_STRIDE
        px = [[0] * (BATTLE_W * 8) for _ in range(BATTLE_H * 8)]
        for r in range(BATTLE_H):                     # 원본 픽셀을 뜬다
            for c in range(BATTLE_W):
                b = (base + r * BATTLE_W + c) * 32
                for y in range(8):
                    for i in range(4):
                        byte = vram[b + y * 4 + i]
                        px[r * 8 + y][c * 8 + i * 2] = byte >> 4
                        px[r * 8 + y][c * 8 + i * 2 + 1] = byte & 15
        text = ko.get(("battle", k))
        if text:
            for y in range(y0, y1):                   # 글자 영역을 판 색으로 지운다
                for x in range(x0, x1):
                    px[y][x] = BATTLE_PLATE
            if len(text) * 16 > x1 - x0:
                raise SystemExit(f"전투씬 라벨 {k} {text!r} 이 {x1 - x0}px 를 넘는다")
            ox = x0 + (x1 - x0 - len(text) * 16) // 2
            for i, ch in enumerate(text):
                if ch not in gmap:
                    raise SystemExit(f"둥근모꼴에 글리프 없음: {ch!r}")
                o = gmap[ch] * 32
                for y in range(16):
                    bits = (font[o + y * 2] << 8) | font[o + y * 2 + 1]
                    for x in range(16):
                        if bits >> (15 - x) & 1:
                            px[y0 + y][ox + i * 16 + x] = INK
            log.append(f"  라벨 {k} 타일 {base}..{base + BATTLE_STRIDE - 1}  {text}")
        else:
            log.append(f"  라벨 {k} 번역 없음 — 원본 유지")
        for r in range(BATTLE_H):                     # 다시 타일로
            for c in range(BATTLE_W):
                for y in range(8):
                    for i in range(4):
                        hi = px[r * 8 + y][c * 8 + i * 2]
                        lo = px[r * 8 + y][c * 8 + i * 2 + 1]
                        out.append((hi << 4) | lo)
    log.append(f"  타일 {len(out) // 32}개 -> 리소스 {BATTLE_RES:02X} 로드 시 "
               f"VRAM {BATTLE_VRAM:04X}")
    return bytes(out), log


def build_deploy_labels() -> tuple[bytes, list[str]]:
    """출전 준비 라벨 2개. 원본 타일에서 글자만 지우고 한글을 그린다.

    반환 순서는 `DEPLOY_SITES` 순서이고, 각 라벨은 16타일이다.
    """
    ko, log = load_ko(), []
    font, gmap = LABEL_BIN.read_bytes(), json.loads(LABEL_MAP.read_text())
    vram = DEPLOY_DUMP.read_bytes()
    out = bytearray()
    for site, base, row in DEPLOY_SITES:
        px = [[DEPLOY_BG] * (DEPLOY_W * 8) for _ in range(DEPLOY_H * 8)]
        text = ko.get(("deploy", row))
        if not text:
            for r in range(DEPLOY_H):        # 번역 없으면 원본 그대로
                for c in range(DEPLOY_W):
                    b = (base + r * DEPLOY_W + c) * 32
                    for y in range(8):
                        for i in range(4):
                            byte = vram[b + y * 4 + i]
                            px[r * 8 + y][c * 8 + i * 2] = byte >> 4
                            px[r * 8 + y][c * 8 + i * 2 + 1] = byte & 15
            log.append(f"  {site:06X} 타일 {base}..{base + 15}  번역 없음 — 원본 유지")
        else:
            if len(text) * 16 > DEPLOY_W * 8:
                raise SystemExit(f"출전 준비 라벨 {text!r} 이 {DEPLOY_W * 8}px 를 넘는다")
            ox = (DEPLOY_W * 8 - len(text) * 16) // 2
            for i, ch in enumerate(text):
                if ch not in gmap:
                    raise SystemExit(f"둥근모꼴에 글리프 없음: {ch!r}")
                o = gmap[ch] * 32
                for y in range(16):
                    bits = (font[o + y * 2] << 8) | font[o + y * 2 + 1]
                    for x in range(16):
                        if bits >> (15 - x) & 1:
                            px[y][ox + i * 16 + x] = INK
            log.append(f"  {site:06X} 타일 {base}..{base + 15}  {text}")
        for r in range(DEPLOY_H):
            for c in range(DEPLOY_W):
                for y in range(8):
                    for i in range(4):
                        hi = px[r * 8 + y][c * 8 + i * 2]
                        lo = px[r * 8 + y][c * 8 + i * 2 + 1]
                        out.append((hi << 4) | lo)
    return bytes(out), log


def build_target_labels(src: bytes) -> tuple[list[tuple[int, bytes]], list[str]]:
    """대상 선택 라벨 4개. 리소스 0x83 안 20타일 블록을 제자리에 갈아 끼운다.

    반환은 `[(롬 주소, 640바이트), ...]` — 훅이 없으므로 빌더가 그대로 쓴다.
    """
    ko, log = load_ko(), []
    font, gmap = LABEL_BIN.read_bytes(), json.loads(LABEL_MAP.read_text())
    W, H = TARGET_W * 8, TARGET_H * 8
    out = []
    for blk in range(TARGET_N):
        at = TARGET_RES_DATA + blk * TARGET_STRIDE
        text = ko.get(("target", blk))
        if not text:
            log.append(f"  {at:06X} 블록 {blk}  번역 없음 — 원본 유지")
            continue
        if len(text) * 16 > W:
            raise SystemExit(f"대상 선택 라벨 {text!r} 이 {W}px 를 넘는다")
        px = [[ATTACK_BG] * W for _ in range(H)]
        ox = (W - len(text) * 16) // 2
        for i, ch in enumerate(text):
            if ch == " ":
                continue
            if ch not in gmap:
                raise SystemExit(f"둥근모꼴에 글리프 없음: {ch!r}")
            o = gmap[ch] * 32
            for y in range(16):
                bits = (font[o + y * 2] << 8) | font[o + y * 2 + 1]
                for x in range(16):
                    if bits >> (15 - x) & 1:
                        px[y][ox + i * 16 + x] = INK
        blob = bytearray()
        for r in range(TARGET_H):
            for c in range(TARGET_W):
                for y in range(8):
                    for i in range(4):
                        hi = px[r * 8 + y][c * 8 + i * 2]
                        lo = px[r * 8 + y][c * 8 + i * 2 + 1]
                        blob.append((hi << 4) | lo)
        assert len(blob) == TARGET_STRIDE
        out.append((at, bytes(blob)))
        log.append(f"  {at:06X} 블록 {blk}  {ko.get(('target', blk))}")
    return out, log


def plan(src: bytes) -> tuple[dict[int, dict], set[int]]:
    """서술자별 줄 구성과 고정 오프셋 집합. 번역 없이도 돌아가는 조사 단계."""
    menus, referenced = {}, set()
    for ptr in blocks(src):
        base, w, h, grid, dlen = decode(src, ptr)
        if base < 1280:                       # 프롤로그 풀(타일 448)은 다른 리소스
            continue
        referenced |= {o for row in grid for o in row}
        menus[ptr] = dict(base=base, w=w, h=h, grid=grid, dlen=dlen,
                          rows=rows_of(grid, h))
    pinned = {o for o in range(POOL_TILES) if o not in referenced}   # 미참조 = 보험
    return menus, pinned


def build(rom: bytearray, src: bytes) -> list[str]:
    """풀을 다시 굽고 서술자를 다시 쓴다. 반환값은 로그."""
    ko = load_ko()
    menus, pinned = plan(src)
    rec_of = {}                               # 블록 -> 레코드 주소 (로그용 이름)
    for p in range(0, len(src) - 12, 2):
        if u16(src, p + 4) == 0xC000 and u16(src, p + 6) == 5:
            ptr = int.from_bytes(src[p + 8:p + 12], "big")
            if ptr in menus:
                rec_of[ptr] = p
    if len(rec_of) != len(menus):
        raise SystemExit(f"서술자 {len(menus)}개 중 레코드를 찾은 것이 {len(rec_of)}개")

    # 1) 고정 오프셋 — 손대지 않는 메뉴 전체 + 번역 없는 줄
    todo = {}
    for ptr, m in menus.items():
        rec = f"{rec_of[ptr]:06X}"
        if rec_of[ptr] in UNTOUCHED:
            pinned |= {o for row in m["grid"] for o in row}
            continue
        texts = [ko.get((rec, i)) for i in range(len(m["rows"]))]
        for i, t in enumerate(texts):
            if not t:                         # 번역 없는 줄은 원본 픽셀 유지
                pinned |= set(m["rows"][i][0]) | set(m["rows"][i][1])
        todo[ptr] = texts
    pinned.add(BLANK)

    # 2) 한글 음절을 빈 타일에 굽는다
    pool = Pool(src, pinned)
    log = []
    for ptr, texts in sorted(todo.items()):
        m = menus[ptr]
        off = m["base"] - POOL_BASE_TILE
        grid = [row[:] for row in m["grid"]]
        done = []
        for i, text in enumerate(texts):
            if not text:
                continue
            cells_top, cells_bot = [], []
            for ch in text:
                if ch == " ":
                    cells_top.append(BLANK)
                    cells_bot.append(BLANK)
                    continue
                tl, tr, bl, br = pool.syllable(ch)
                cells_top += [tl, tr]
                cells_bot += [bl, br]
            if len(cells_top) > m["w"]:
                raise SystemExit(f"{rec_of[ptr]:06X}[{i}] {text!r} 이 "
                                 f"{m['w']}칸을 넘는다 ({len(cells_top)}칸)")
            pad = m["w"] - len(cells_top)
            grid[i * 2] = cells_top + [BLANK] * pad
            grid[i * 2 + 1] = cells_bot + [BLANK] * pad
            done.append(text)
        # 베이스를 0x8500 으로 통일한다. 0x8520 이면 오프셋 32 미만을 가리킬 수 없다.
        if m["base"] != POOL_BASE_TILE:
            rom[ptr + 4:ptr + 6] = (0x8000 | (POOL_BASE_TILE & 0x7FF)).to_bytes(2, "big")
            off = 0
        desc = (b"\x00\x02" + m["w"].to_bytes(2, "big") + m["h"].to_bytes(2, "big")
                + encode(grid, m["w"], m["h"], off))
        if len(desc) > m["dlen"]:
            raise SystemExit(f"{rec_of[ptr]:06X}: 서술자가 {len(desc)}B 로 "
                             f"원본 {m['dlen']}B 를 넘는다")
        rom[ptr + 8:ptr + 8 + len(desc)] = desc
        log.append(f"  {rec_of[ptr]:06X}  {m['w']}x{m['h']}  {len(desc):3d}/{m['dlen']}B  "
                   + " / ".join(done))

    rom[POOL_AT:POOL_AT + POOL_TILES * 32] = pool.bytes()
    log.append(f"  풀 {POOL_AT:06X}  음절 {len(pool.syl)}개 / 빈 타일 "
               f"{len(pool.free)}개 남음 / 고정 {len(pinned)}개")
    return log


def preview(src: bytes, rom: bytes, out: Path, scale: int = 4) -> None:
    """빌드 결과를 눈으로 확인할 PNG. 실기 확인 전에 걸러내기 위한 것."""
    from tilepng import png
    menus, _ = plan(src)
    items = []
    for ptr in sorted(menus):
        base, w, h, grid, _ = decode(rom, ptr)
        items.append((ptr, w, h, grid, base - POOL_BASE_TILE))
    W = max(w for _, w, _, _, _ in items) * 8 * scale
    H = sum(h * 8 + 4 for _, _, h, _, _ in items) * scale
    canvas = [[40] * W for _ in range(H)]
    y0 = 0
    for ptr, w, h, grid, off in items:
        for r in range(h):
            for c in range(w):
                b = POOL_AT + grid[r][c] * 32
                for y in range(8):
                    for k in range(4):
                        byte = rom[b + y * 4 + k]
                        for j, nib in enumerate((byte >> 4, byte & 15)):
                            v = nib * 17
                            for sy in range(scale):
                                for sx in range(scale):
                                    canvas[(y0 + r * 8 + y) * scale + sy][
                                        (c * 8 + k * 2 + j) * scale + sx] = v
        y0 += h * 8 + 4
    png(out, W, H, canvas)


def main() -> None:
    src = Path("/Users/rotein/Downloads/Langrisser.md").read_bytes()
    menus, pinned = plan(src)
    print(f"풀 0x7D  {POOL_AT:06X}  {POOL_TILES}타일 / 미참조 {len(pinned)}개")
    for ptr in sorted(menus):
        m = menus[ptr]
        print(f"\n{ptr:06X}  base={m['base']}  {m['w']}x{m['h']}  서술자 {m['dlen']}B")
        for i, (top, bot) in enumerate(m["rows"]):
            print(f"   {i}  위 {top}\n      아래 {bot}")


if __name__ == "__main__":
    main()
