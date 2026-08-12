#!/usr/bin/env python3
"""한글화 롬 빌드 — 프롤로그 화면 20개 + 본편 대사 + 이름판.

글리프 테이블은 **전역**이다. 롬에 쓰이는 모든 한글 글리프를 한 번 모아 ID 를
부여하고, 각 문자열은 그 ID 목록을 헤더로 들고 다닌다. 업로더가 헤더를 읽어
VRAM 슬롯을 채운다. 화면이 바뀔 때 달라지는 것은 타일의 **내용**뿐이다.

타일·코드 배정
--------------
```
타일 128..191  본문 슬롯        코드 0x7F..0xA0 / 0xE0..0xFD (64개) — 대사·프롤로그
   128..158     마법 공유 어휘   목록이 여러 줄 동시에 보이므로 표 전체가 공유
   159..184     아이템 공유 어휘
타일 192..197  이름 6칸         코드 0x0E..0x13 (위치 고정)
타일 198..205  클래스명 8칸     코드 0x02..0x09 (위치 고정)
타일 206..220  팝업 단문 15칸   코드 0x0A..0x0C / 0x14..0x1F
                               + 상태창 라벨(지휘범위·수정)이 앞 6칸을 나눠 쓴다
타일 212..235  용병 클래스 어휘  **대체 코드 페이지**에서 코드 0x7F.. -> 212..
```
저바이트 코드는 다 찼다. 그래서 코드가 더 필요하면 **표를 갈아 끼운다** — 업로더가
돌려주는 a2 가 `$5F60` 의 코드->타일 표이므로 문자열마다 다른 표를 줄 수 있다.
기록의 플래그 bit0 이 그 뜻이다. 가나 코드를 전역으로 훔치는 길은 막혀 있다
(남은 대사 1026개가 가나 62종을 쓴다 — `。` `「` 까지).
`$62BC` 는 코드 -> 타일 표이고 렌더러 `$5F60` 이 이것으로 타일을 고른다.
배정을 가르는 기준은 **한 화면에 무엇이 같이 보이는가** 하나다. 같이 보이는 것은
타일이 겹치면 안 되고(먼저 그린 글자가 나중 글리프로 변한다), 같이 안 보이는 것은
얼마든지 돌려쓸 수 있다(다시 그릴 때 자기 글리프를 다시 올리므로 스스로 낫는다).

**남은 일본어도 "같이 보이는 것"에 든다.** 본문 슬롯 128..191 은 게임의 가나 폰트
자리이므로, 같은 화면에 원문 가나가 있으면 그 글자가 우리 글리프로 변한다.

훅
--
```
0x5FD4   lea $62BC,a2 -> jsr 업로더     $5F60 안. 문자열이 [0x01][k] 를 달고 있으면
                                        그 기록의 글리프를 올린다. **경로 무관** —
                                        UI·프롤로그·조건문·이름·상태창이 다 이것뿐
0x18D12  jsr $5F60    -> jsr 업로더     프롤로그 첫 draw (승리/패배 라벨 업로드용)
0x157C8  move.l a1,$E818 -> jsr 업로더  대사 본문 글리프 (0xFE 헤더)
0x157D8 + 상태창 3곳   이름표 즉치      0x2AE64 -> 우리 표
```
그리기 지점마다 훅을 걸면 경로를 전부 찾아야 한다. 승리조건 창에서 그 대가를
치렀고(STATUS 참고) 지금은 렌더러 안 한 곳으로 모았다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asm import UI_MARKER, build_uploader_labels, build_uploader_msg  # noqa: E402
from asm import build_uploader_ui, build_uploader_block  # noqa: E402
from chain import parse_chain  # noqa: E402
from events import e82c_sites  # noqa: E402
import menu  # noqa: E402
from script import decode  # noqa: E402

SRC = Path("/Users/rotein/Downloads/Langrisser.md")
VRAM = Path("work/Mega Drive/Langrisser-vdp-vram-20260811-151039.bin")
G7_BIN = Path("font/galmuri7/font-007242d37349daf3.bin")
G7_MAP = Path("font/galmuri7/font-007242d37349daf3_glyph_map.json")
LABEL_BIN = Path("font/dunggeunmo/font-6883cc1477b4cbfa.bin")
LABEL_MAP = Path("font/dunggeunmo/font-6883cc1477b4cbfa_glyph_map.json")
KO_TSV = Path("translation/ko.tsv")
NAMES_TSV = Path("translation/names.tsv")
DIALOGUE_TSV = Path("translation/dialogue.tsv")
UI_TSV = Path("translation/ui.tsv")

ROM_SIZE = 0x100000
UPLOADER_AT, UPLOADER2_AT, UI_UPLOADER_AT = 0x80000, 0x80200, 0x80700
LABEL_AT, NAMESTR_AT, NAMEIDS_AT = 0x80400, 0x80800, 0x81000
UISTR_AT, UITBL_AT, ALTTBL_AT = 0x82000, 0x83000, 0x8A000
CLSB_AT = 0x8B000        # 전직 후보용 클래스표 사본
TITLE_AT, TITLE_UP_AT = 0x8C000, 0x80D00   # 선택 창 제목 타일 + 업로더
KFONT_AT, TEXT_AT, CHAIN_AT = 0x90000, 0xA0000, 0xB0000

HOOK_SITE, STRDRAW, TABLE_AT = 0x18D12, 0x5F60, 0x62BC
MSG_HOOK, NAMEPTR_IMM, NAMETBL_ORIG = 0x157C8, 0x157D8, 0x2AE64
UI_HOOK = 0x5FD4          # lea $62BC.l, a2 — 문자열 루프 직전

SLOT_BASE = 128
CODES = list(range(0x7F, 0xA1)) + list(range(0xE0, 0xFE))   # 64개
NAME_BASE, NAME_CELLS = 192, 6
NAME_CODES = list(range(0x0E, 0x0E + NAME_CELLS))
# UI 전용 저바이트 코드 23개 -> 타일 198.. (클래스명 같은 '한 번에 하나' 필드용)
UI_CODES = list(range(0x02, 0x0D)) + list(range(0x14, 0x20))
UI_BASE, UI_STRIDE, UI_REC = 198, 16, 136   # 기록 136B = 글리프 67자까지
#                                            (프롤로그 화면 합집합 64자가 들어가야 한다)
SYS_OFF = 8               # 팝업 단문은 클래스명 뒤 칸을 쓴다 (동시에 보여도 안 겹치게)
# `lea` 로 오는 낱개 문자열의 슬롯 정책. 둘 다 팝업 칸(206..220)을 쓴다.
#   popup   문자열마다 기록 하나 — 서로 동시에 뜨지 않는 것
#   shared  이 정책끼리 기록 하나를 공유 — 상태창 라벨처럼 **같이 보이는** 것
#
# 라벨을 본문 여유 슬롯(185..190)에 넣었다가 실패했다. 본문 슬롯은 곧 **가나 폰트
# 자리**이고, 상태창과 같이 보이는 지휘관 이름판이 원본 카타카나다. `ル`=185
# `レ`=186 `ン`=189 이 우리 `지` `휘` `수` 로 변해 이름판이 `휘ディ수` 가 됐다.
# 팝업 칸은 남은 일본어가 쓰지 않는 자리라(타일 206.. 은 히라가나 폰트 영역이지만
# 이 화면에 히라가나가 없다) 안전하다. 팝업과는 겹치는데 서로 다시 그릴 때
# 자기 글리프를 다시 올리므로 낫는다.
STR_POLICY = {0x30A92: "popup", 0x31564: "shared", 0x3156C: "shared"}
# 이름이 **한 번에 하나만** 보이는 자리들. 여기만 우리 이름표로 돌린다.
#   상태창 3변형 + 레벨업·전직 팝업 3개의 콜백 (0x151AC / 0x15218 / 0x1527A)
# 출전 준비 화면 위쪽 지휘관 이름판처럼 여러 개가 동시에 보이는 자리는 건드리지
# 않는다 — 우리 방식은 타일 192..197 을 돌려쓰므로 모두 마지막 이름으로 변한다.
#   0x12260 은 상태창 4번째 변형이다 (이름 -> 클래스명 -> LV 를 잇달아 그리는
#   같은 모양). 나머지 10곳은 아직 분류하지 않았다 — uiscan.py 가 목록을 낸다.
NAMEPTR_PANEL = (0x1257C, 0x1260E, 0x126A4, 0x12260,
                 0x151C2, 0x1522E, 0x15290)
UI_FIELDS = {                     # 필드 -> (원본 표, 엔트리 수, 칸 수, 배정 방식)
    "magic": (0x2B9AC, 14, 8, "shared"),
    "item":  (0x2B8E4, 10, 8, "shared"),
    "class": (0x2B334, 91, 8, "positional"),
}
# 용병 클래스는 출전 준비 화면에서 **여러 줄이 동시에** 보인다(패널 + 목록 3줄).
# 위치 코드로는 마지막 줄 글리프가 앞줄을 덮어 `솔저`·`호스맨` 이 `라이`·`라이트` 로
# 나왔다. 그래서 이 엔트리들만 표 전체 어휘를 공유하는 기록 하나를 쓴다.
#
# 코드가 없어서 **대체 코드 페이지**를 쓴다. 업로더가 돌려주는 a2 가 `$5F60` 의
# 코드->타일 표이므로 문자열마다 다른 표를 줄 수 있다(`asm.build_uploader_ui`).
# 가나 코드를 전역으로 훔치려 했으나 남은 대사 1026개가 가나 62종을 쓰고 있어
# (`。` `「` 포함) 불가였다. 이 표에서만 본문 코드를 다른 타일로 돌린다.
MERC_CLASSES = list(range(65, 73)) + list(range(75, 80))
CAND_ROWS = range(1, 43)  # 전직 후보표에서 뜻이 있는 행 (지휘관 구간)
CAND_TBL = 0x2BF2E        # 클래스 -> 후보 2개 (워드 x 2, 0xFFFF = 없음)
CAND_SITE = 0x151FE       # 후보를 그리는 lea 즉치 (0x151FC) — 이 자리만 사본으로
#
# 코드 페이지. 기록의 첫 바이트가 페이지 번호이고 0 은 원본 표다.
#   1 용병 클래스     타일 212.. — 출전 준비 화면 (이름 192 / 클래스 198 / 라벨 206)
#   2 전직 후보 클래스 타일 214.. — 전직 팝업. 팝업 문장(206..)과 같이 보이므로
#                     문장 음절 수만큼 비켜 둔다. 후보 2개가 어휘를 공유한다.
PAGES = {"merc": (1, 212), "cand": (2, 214)}
ALT_BASE = 212            # (호환용 — 페이지 1 의 시작 타일)
BG, INK, OUTLINE = 13, 15, 14

TABLES = {"stage": 0x38A38, "prologue": 0x38BF2, "cond": 0x3962E}
KINDS = ["stage", "prologue", "cond"]          # 그려지는 순서
LABEL_DST, LABEL_TILES, LABEL_Y = 522 * 32, 20, 4
LABEL_TOP, LABEL_BOTTOM = "승리", "패배"
FROM_VRAM = {"。": 129, "「": 130, "」": 131, "、": 132, "・": 133}  # 게임 폰트의 가나 블록
# 게임 ASCII 폰트는 타일 0..95 = 코드 0x20..0x7F 라 소문자도 있다 (Yes/No 용)
ASCII_OK = set(" 1234567890.,()-!?:/" "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "abcdefghijklmnopqrstuvwxyz")


PLACED: list[tuple[int, int, str]] = []


def place(rom: bytearray, at: int, data: bytes, label: str) -> int:
    """빈 공간에 데이터를 놓고 구간을 등록한다. 겹치면 즉시 죽는다.

    이름 ID 표가 글리프 테이블을 덮어써서 한 번 당했다. 주소를 손으로 관리하는
    동안은 겹침을 눈으로 확인할 수 없으니 기계가 확인한다.
    """
    end = at + len(data)
    for s, e, other in PLACED:
        if at < e and s < end:
            raise SystemExit(f"{label} [{at:06X}..{end:06X}) 가 "
                             f"{other} [{s:06X}..{e:06X}) 와 겹친다")
    PLACED.append((at, end, label))
    rom[at:end] = data
    return end


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


def load_tsv(path: Path, key: int, val: int, ncol: int) -> dict[str, str]:
    out = {}
    for ln in path.read_text().rstrip("\n").split("\n")[1:]:
        c = ln.split("\t")
        if len(c) >= ncol and c[val]:
            out[c[key]] = c[val].replace("\\n", "\n")
    return out


def esc(s: str) -> str:
    """워크시트에 적히는 형태로 — 원문 기억의 키를 맞추기 위한 것."""
    return s.replace("\n", "\\n").replace("\t", " ")


def load_dialogue() -> tuple[dict[tuple[str, int], str], dict[str, str]]:
    """(앵커, 메시지번호) -> 한국어, 그리고 **원문 -> 한국어 기억**.

    같은 대사가 화자 워드만 바꿔 여러 앵커에 복사돼 있다(스테이지 16 의 검 습득
    대사는 8벌). 워크시트에는 한 벌만 싣고, 나머지는 원문이 같으면 기억에서
    끌어온다. 같은 문장을 여러 번 옮겨 적지 않기 위한 것이다.
    """
    rows = DIALOGUE_TSV.read_text().rstrip("\n").split("\n")
    cols = rows[0].split("\t")
    ia, ii, ij, ik = (cols.index(c) for c in ("anchor", "idx", "jp", "ko"))
    explicit: dict[tuple[str, int], str] = {}
    memory: dict[str, str] = {}
    for ln in rows[1:]:
        c = ln.split("\t")
        if len(c) <= ik or not c[ik]:
            continue
        ko = c[ik].replace("\\n", "\n")
        explicit[(c[ia], int(c[ii]))] = ko
        memory.setdefault(c[ij], ko)
    return explicit, memory


class Glyphs:
    """전역 글리프 테이블. 문자 -> ID, ID 는 7비트 두 바이트로 담긴다."""

    def __init__(self, vram: bytes) -> None:
        self.gid: dict[str, int] = {}
        self.vram = vram
        self.g7 = G7_BIN.read_bytes()
        self.g7map = json.loads(G7_MAP.read_text())

    def add(self, text: str) -> None:
        for ch in text:
            if ch not in ASCII_OK and ch != "\n" and ch not in self.gid:
                self.gid[ch] = len(self.gid)

    def table(self) -> bytes:
        out = bytearray()
        for ch in self.gid:
            if ch in FROM_VRAM:
                t = FROM_VRAM[ch]
                out += self.vram[t * 32:(t + 1) * 32]
            elif ch in self.g7map:
                o = self.g7map[ch] * 8
                out += to_4bpp(self.g7[o:o + 8])
            else:
                raise SystemExit(f"글리프 없음: {ch!r}")
        return bytes(out)

    def header(self, slots: dict[str, int]) -> bytes:
        """[0xFE][N][ID x N] — ID = (b0 << 7) | b1.

        16비트로 담으면 ID 255 가 0x00FF 처럼 0xFF 를 포함하는데, 게임은 메시지를
        건너뛸 때 0xFF 를 바이트 단위로 훑으므로(0x15470, 0x157BA) 헤더 중간에서
        멈춘다. 두 바이트 모두 0x80 미만이면 그 사고가 원천적으로 없다.
        """
        out = bytearray([0xFE, len(slots)])
        for ch in slots:
            g = self.gid[ch]
            if g > 0x3FFF:
                raise SystemExit(f"글리프 ID {g} 가 14비트를 넘는다")
            out += bytes([g >> 7, g & 0x7F])
        return bytes(out)


def assign(texts: list[str]) -> dict[str, int]:
    """한 화면(또는 한 메시지)에 동시에 보이는 문자들에게 슬롯을 나눠준다.

    네임테이블은 타일 *번호* 만 들고 있다. 나중에 픽셀을 바꾸면 먼저 그려진
    글자의 모양까지 바뀌므로, 같이 보이는 문자열은 배정을 공유해야 한다.
    """
    slots: dict[str, int] = {}
    for t in texts:
        for ch in t:
            if ch not in ASCII_OK and ch != "\n" and ch not in slots:
                slots[ch] = len(slots)
    return slots


def encode(text: str, slots: dict[str, int]) -> bytes:
    out = bytearray()
    for ch in text:
        if ch == "\n":
            out += b"\x0d\x0d"          # 시각적 한 줄 = 0x0D 두 개
        elif ch in ASCII_OK:
            out.append(ord(ch))
        else:
            out.append(CODES[slots[ch]])
    return bytes(out)


# ------------------------------------------------------------------ 이름판
def build_names(g: Glyphs, recs: list[tuple[int, list[str], int]]) -> tuple[bytes, bytes, int]:
    """이름 문자열표 + 글리프 ID 표. 둘 다 원본과 같은 16B/엔트리.

    원본 표(0x2AE64, 16B x 78)를 건드리지 않는 이유: 같은 표를 유닛 목록 창처럼
    **여러 이름이 동시에 보이는** UI 도 읽는다. 그런 곳은 한 이름당 6칸을 돌려쓰는
    이 방식으로는 안 되므로(마지막 이름으로 다 변한다) 원문 그대로 둔다.
    우리 표로 돌리는 것은 이름이 한 번에 하나만 보이는 자리뿐이다.

    문자열은 **위치 코드**다 — k 번째 한글 칸은 항상 코드 `0x0E+k`. 업로더가
    그 이름의 글리프를 타일 192+k 에 올리므로 표에는 자리만 적으면 된다.

    앞머리에 `[0x01][기록번호]` 를 단다. 대사 이름판은 `0x157C8` 훅이 `$E82A` 로
    글리프를 올리지만, 유닛 상태창은 그 훅을 지나지 않는다. UI 마커를 달아 두면
    `$5F60` 안의 훅(`0x5FD4`)이 **어느 경로에서든** 그 이름의 글리프를 올린다.
    엔트리 16바이트에 2 + 6칸 + 종료자 = 9바이트라 자리가 남는다.
    """
    ko = load_tsv(NAMES_TSV, 0, 2, 3)
    n = 78
    strs, idtbl = bytearray(), bytearray()
    for k in range(n):
        name = ko.get(str(k), "")
        cells, ids, chars = bytearray(), [], []
        for ch in name:
            if ch in ASCII_OK:
                cells.append(ord(ch))
            else:
                if len(ids) >= NAME_CELLS:
                    raise SystemExit(f"이름 {k} {name!r} 이 {NAME_CELLS}칸을 넘는다")
                cells.append(NAME_CODES[len(ids)])
                g.add(ch)
                ids.append(g.gid[ch])
                chars.append(ch)
        if len(cells) > NAME_CELLS:
            raise SystemExit(f"이름 {k} {name!r} 이 {NAME_CELLS}칸을 넘는다")
        cells += b" " * (NAME_CELLS - len(cells)) + b"\xff"   # 남은 칸은 공백으로 지운다
        entry = bytes([UI_MARKER, len(recs)]) + bytes(cells)
        recs.append((NAME_BASE, chars, 0))
        rec = bytearray([len(ids)])
        for gid in ids:
            rec += bytes([gid >> 7, gid & 0x7F])
        strs += entry.ljust(16, b"\x00")
        idtbl += rec.ljust(16, b"\x00")
    return bytes(strs), bytes(idtbl), n


# ------------------------------------------------------------------ UI 텍스트
def lea_sites(rom: bytes, addr: int) -> list[int]:
    """`lea addr.l, aN` 의 즉치 위치들. UI 문자열표를 우리 것으로 돌리는 데 쓴다."""
    pat, out = addr.to_bytes(4, "big"), []
    for p in range(0, len(rom) - 6, 2):
        if rom[p] & 0xF1 == 0x41 and rom[p + 1] == 0xF9 and rom[p + 2:p + 6] == pat:
            out.append(p + 2)
    return out


def build_ui(rom: bytearray, src: bytes, g: Glyphs,
             recs: list[tuple[int, list[str], int]]) -> tuple[bytes, list[str]]:
    """UI 문자열표를 우리 것으로 바꾼다. 반환값은 (문자열표, 글리프 기록표, 로그).

    엔트리가 `lsl.w #4` 로 색인돼 **16바이트 고정**이라 글리프 목록을 문자열에 담을
    수 없다. 그래서 `[0x01][k]` 두 바이트만 붙이고 글리프는 별도 기록표에 둔다.

    두 가지 배정 방식을 쓴다 — 갈리는 기준은 **한 화면에 몇 개가 보이는가**다.

      positional  한 번에 하나만 보이는 표(클래스명). 엔트리마다 기록을 따로 갖고
                  k 번째 칸은 항상 코드 `UI_CODES[k]`. 칸 수만큼만 타일을 쓴다.
      shared      여러 줄이 동시에 보이는 표(마법·아이템 — 목록을 루프로 그린다).
                  표 전체의 **어휘 합집합**을 한 기록에 담고 모든 엔트리가 그것을
                  공유한다. 줄마다 다시 올려도 결과가 같으므로 순서에 안 깨진다.

    번역이 없는 엔트리는 원본 16바이트를 그대로 복사한다. 우리 표가 원본을 완전히
    대신하므로 빈 칸을 남기면 그 엔트리가 사라진다.
    """
    ui: dict[tuple[str, int], str] = {}
    for ln in UI_TSV.read_text().rstrip("\n").split("\n")[1:]:
        c = ln.split("\t")
        if len(c) >= 4 and c[3]:
            # system·str 은 인덱스 대신 롬 주소를 키로 쓴다
            base = 16 if c[0] in ("system", "str") else 10
            ui[(c[0], int(c[1], base))] = c[3]

    strs, log, body_off, at = bytearray(), [], 0, {}
    for field, (table, n, cells, mode) in UI_FIELDS.items():
        at[field] = UISTR_AT + len(strs)
        done = 0
        if mode == "shared":
            vocab: list[str] = []
            for k in range(n):
                for ch in ui.get((field, k), ""):
                    if ch not in ASCII_OK and ch not in vocab:
                        vocab.append(ch)
            if body_off + len(vocab) > len(CODES):
                raise SystemExit(f"{field}: 어휘 {len(vocab)}자가 본문 코드에 안 들어간다")
            cmap = {ch: CODES[body_off + i] for i, ch in enumerate(vocab)}
            shared_k = len(recs)
            recs.append((SLOT_BASE + body_off, vocab, 0))
            body_off += len(vocab)
        if field == "class":                      # 용병 클래스만 대체 페이지 공유
            merc: list[str] = []
            for k in MERC_CLASSES:
                for ch in ui.get((field, k), ""):
                    if ch not in ASCII_OK and ch not in merc:
                        merc.append(ch)
            pidx, pbase = PAGES["merc"]
            if pbase + len(merc) > 256:
                raise SystemExit(f"용병 어휘 {len(merc)}자가 페이지 타일 "
                                 f"{256 - pbase}칸에 안 들어간다")
            merc_map = {ch: CODES[i] for i, ch in enumerate(merc)}
            merc_k = len(recs)
            recs.append((pbase, merc, pidx))
            log.append(f"  merc              어휘 {len(merc)}자 / 페이지 {pidx} "
                       f"타일 {pbase}..{pbase + len(merc) - 1} / 클래스 "
                       f"{len(MERC_CLASSES)}개")
        for k in range(n):
            ko = ui.get((field, k))
            if not ko:
                strs += src[table + k * UI_STRIDE:table + (k + 1) * UI_STRIDE]
                continue
            if len(ko) > cells:
                raise SystemExit(f"{field}[{k}] {ko!r} 이 {cells}칸을 넘는다")
            if mode == "shared":
                rk, code_of = shared_k, cmap
            elif field == "class" and k in MERC_CLASSES:
                rk, code_of = merc_k, merc_map
            else:
                chars = [ch for ch in ko if ch not in ASCII_OK]
                if len(chars) > len(UI_CODES):
                    raise SystemExit(f"{field}[{k}] {ko!r} 이 이름칸 {len(UI_CODES)}개를 넘는다")
                rk, code_of = len(recs), {ch: UI_CODES[i] for i, ch in enumerate(chars)}
                recs.append((UI_BASE, chars, 0))
            entry = bytearray([UI_MARKER, rk])
            for i, ch in enumerate(ko):
                entry.append(ord(ch) if ch in ASCII_OK else code_of[ch])
            entry += b" " * (cells - len(ko)) + b"\xff"     # 남은 칸은 공백으로 지운다
            if len(entry) > UI_STRIDE:
                raise SystemExit(f"{field}[{k}] 엔트리가 {UI_STRIDE}바이트를 넘는다")
            strs += entry.ljust(UI_STRIDE, b"\x00")
            done += 1
        sites = lea_sites(src, table)
        if not sites:
            raise SystemExit(f"{field}: 표 {table:06X} 를 싣는 lea 를 못 찾았다")
        for p in sites:
            rom[p:p + 4] = at[field].to_bytes(4, "big")
        log.append(f"  {field:6s} {table:06X} -> {at[field]:06X}  {done}/{n} 번역 / "
                   f"lea {len(sites)}곳 / 기록 {len(recs)}개")

    # 창 서술자가 물고 있는 단문 (종류 4). 텍스트는 포인터+4 에 있고 앞 4바이트는
    # (x, y) 다. 팝업은 한 번에 하나만 뜨므로 전부 같은 코드 구간을 나눠 쓴다.
    sysbase = UI_BASE + SYS_OFF
    sysd = {idx: ko for (field, idx), ko in ui.items() if field == "system"}
    done = 0
    for rec_at in sorted(sysd):
        ko = sysd[rec_at].replace("\\n", "\n")
        ptr_at = rec_at + 8
        ptr = int.from_bytes(src[ptr_at:ptr_at + 4], "big")
        # 세이브 확인 창(0x000282)처럼 레코드가 롬 앞쪽에 있는 것도 있다.
        assert 0x200 <= ptr < 0x40000, f"{rec_at:06X}: 창 포인터가 이상하다"
        chars = [ch for ch in ko if ch not in ASCII_OK and ch != "\n"]
        if len(chars) > len(UI_CODES) - SYS_OFF:
            raise SystemExit(f"단문 {rec_at:06X} {ko!r} 이 팝업 칸 "
                             f"{len(UI_CODES) - SYS_OFF}개를 넘는다")
        # 전직 팝업은 후보 클래스(페이지 2, 타일 214..)와 한 화면이다. 문장이 그
        # 타일까지 먹으면 후보 이름이 문장 글리프로 변한다.
        if rec_at == 0x32A8E and sysbase + len(chars) > PAGES["cand"][1]:
            raise SystemExit(f"전직 팝업 문장 {ko!r} 이 {len(chars)}자 — 후보 페이지 "
                             f"타일 {PAGES['cand'][1]} 를 침범한다")
        rk = len(recs)
        recs.append((sysbase, chars, 0))
        code_of = {ch: UI_CODES[SYS_OFF + i] for i, ch in enumerate(chars)}
        out = bytearray(src[ptr:ptr + 4]) + bytes([UI_MARKER, rk])
        for ch in ko:
            if ch == "\n":
                out += b"\x0d\x0d"
            else:
                out.append(ord(ch) if ch in ASCII_OK else code_of[ch])
        out += b"\x0d\x0d\xff"
        at_sys = UISTR_AT + len(strs)
        strs += out
        if len(strs) & 1:
            strs += b"\x00"
        rom[ptr_at:ptr_at + 4] = at_sys.to_bytes(4, "big")
        done += 1
    log.append(f"  system            {done}개 / 팝업 칸 {len(UI_CODES) - SYS_OFF}개 "
               f"(타일 {sysbase}..{UI_BASE + len(UI_CODES) - 1})")

    # 코드가 `lea` 로 직접 싣는 낱개 문자열. 표도 창 레코드도 아니다.
    # 슬롯은 `STR_POLICY` 로 갈린다 — 같이 보이는 것과 겹치지 않아야 한다.
    #   0x30A92  승리조건 창 머리글. 조건문(본문 슬롯)보다 **먼저** 그려지므로
    #            본문 범위를 쓰면 이미 그린 글자가 조건문 글리프로 변한다 -> 팝업 칸
    #   0x31564  상태창 `しきはんい`, 0x3156C `しゅうせい`. 이름(192..197)·클래스명
    #            (198..205)·지휘관 이름판(원본 가나 = 본문 슬롯)과 한 화면이라
    #            팝업 칸에 둘이 기록을 공유한다 (STR_POLICY 주석 참고)
    strd = {addr: ko for (field, addr), ko in ui.items() if field == "str"}
    shared_strs = [a for a in sorted(strd) if STR_POLICY.get(a) == "shared"]
    shared_rk, shared_code = None, {}
    if shared_strs:
        vocab = []
        for a in shared_strs:
            for ch in strd[a].replace("\\n", "\n"):
                if ch not in ASCII_OK and ch != "\n" and ch not in vocab:
                    vocab.append(ch)
        if len(vocab) > len(UI_CODES) - SYS_OFF:
            raise SystemExit(f"낱개 문자열 공유 어휘 {len(vocab)}자가 팝업 칸을 넘는다")
        shared_code = {ch: UI_CODES[SYS_OFF + i] for i, ch in enumerate(vocab)}
        shared_rk = len(recs)
        recs.append((sysbase, vocab, 0))
    for addr in sorted(strd):
        ko = strd[addr].replace("\\n", "\n")
        chars = [ch for ch in ko if ch not in ASCII_OK and ch != "\n"]
        if STR_POLICY.get(addr) == "shared":
            rk, code_of = shared_rk, shared_code
        else:
            if len(chars) > len(UI_CODES) - SYS_OFF:
                raise SystemExit(f"낱개 문자열 {addr:06X} {ko!r} 이 팝업 칸을 넘는다")
            rk = len(recs)
            recs.append((sysbase, chars, 0))
            code_of = {ch: UI_CODES[SYS_OFF + i] for i, ch in enumerate(chars)}
        out = bytearray([UI_MARKER, rk])
        for ch in ko:
            out += b"\x0d\x0d" if ch == "\n" else \
                bytes([ord(ch) if ch in ASCII_OK else code_of[ch]])
        out += b"\xff"
        at_str = UISTR_AT + len(strs)
        strs += out
        if len(strs) & 1:
            strs += b"\x00"
        sites = lea_sites(src, addr)
        if not sites:
            raise SystemExit(f"낱개 문자열 {addr:06X} 를 싣는 lea 를 못 찾았다")
        for p in sites:
            rom[p:p + 4] = at_str.to_bytes(4, "big")
        log.append(f"  str    {addr:06X} -> {at_str:06X}  lea {len(sites)}곳  {ko!r}")

    # 전직 팝업의 후보 클래스 — **두 개를 동시에** 그린다(0x151F8 의 dbra, 2회).
    # 위치 코드로는 뒤 후보가 앞 후보를 덮으므로 클래스표 **사본**을 만들어 후보
    # 어휘를 공유시키고, 후보를 그리는 lea 즉치 한 곳만 그 사본으로 돌린다.
    # 다른 자리(상태창·전직 완료 팝업)는 한 번에 하나만 보이므로 원래 표를 쓴다.
    cand = set()
    for k in CAND_ROWS:
        for i in range(2):
            v = int.from_bytes(src[CAND_TBL + k * 4 + i * 2:CAND_TBL + k * 4 + i * 2 + 2], "big")
            if v != 0xFFFF and 0 < v < 63:
                cand.add(v)
    cvocab: list[str] = []
    for k in sorted(cand):
        for ch in ui.get(("class", k), ""):
            if ch not in ASCII_OK and ch not in cvocab:
                cvocab.append(ch)
    pidx, pbase = PAGES["cand"]
    if pbase + len(cvocab) > 256:
        raise SystemExit(f"후보 어휘 {len(cvocab)}자가 페이지 타일 "
                         f"{256 - pbase}칸에 안 들어간다")
    cmap2 = {ch: CODES[i] for i, ch in enumerate(cvocab)}
    cand_k = len(recs)
    recs.append((pbase, cvocab, pidx))
    clsb, table, cells = bytearray(), UI_FIELDS["class"][0], UI_FIELDS["class"][2]
    done = 0
    for k in range(UI_FIELDS["class"][1]):
        ko = ui.get(("class", k)) if k in cand else None
        if not ko:            # 후보가 아닌 엔트리는 원문 그대로 — 그려질 일이 없고,
            clsb += src[table + k * UI_STRIDE:table + (k + 1) * UI_STRIDE]
            continue          # 만약 그려지면 일본어로 보여 바로 눈에 띈다
        entry = bytearray([UI_MARKER, cand_k])
        for ch in ko:
            entry.append(ord(ch) if ch in ASCII_OK else cmap2[ch])
        entry += b" " * (cells - len(ko)) + b"\xff"
        clsb += entry.ljust(UI_STRIDE, b"\x00")
        done += 1
    at_clsb = place(rom, CLSB_AT, bytes(clsb), "전직 후보 클래스표") - len(clsb)
    assert int.from_bytes(rom[CAND_SITE:CAND_SITE + 4], "big") == at["class"], \
        f"{CAND_SITE:06X} 가 클래스표 즉치가 아니다"
    rom[CAND_SITE:CAND_SITE + 4] = at_clsb.to_bytes(4, "big")
    log.append(f"  cand   {table:06X} -> {at_clsb:06X}  {done}/{len(cand)} 후보 / "
               f"어휘 {len(cvocab)}자 / 페이지 {pidx} 타일 "
               f"{pbase}..{pbase + len(cvocab) - 1}")

    log.append(f"  본문 슬롯 {body_off}/{len(CODES)} 사용 (공유 어휘) / "
               f"이름칸 코드 {len(UI_CODES)}개는 클래스명용")
    return bytes(strs), log


def bake_records(recs: list[tuple[int, list[str], int]], g: Glyphs) -> bytes:
    """글리프 기록표 — `[타일][N][ID x N]`, 엔트리 `UI_REC` 바이트 고정.

    프롤로그 화면 기록까지 다 모인 뒤에 굽는다. UI 업로더가 `k` 를 `mulu #stride`
    로 색인하므로 엔트리 길이는 고정이어야 한다.
    """
    for _, chars, _page in recs:
        for ch in chars:
            g.add(ch)
    tbl = bytearray()
    for base, chars, page in recs:
        rec = bytearray([page, base, len(chars)])
        for ch in chars:
            rec += bytes([g.gid[ch] >> 7, g.gid[ch] & 0x7F])
        if len(rec) > UI_REC:
            raise SystemExit(f"글리프 기록이 {UI_REC}바이트를 넘는다 ({len(chars)}자)")
        tbl += rec.ljust(UI_REC, b"\x00")
    return bytes(tbl)


# ------------------------------------------------------------------ 본편 대사
def build_chains(rom: bytearray, src: bytes, g: Glyphs) -> tuple[bytes, list[str]]:
    """번역된 대화 체인을 새 자리에 다시 쓰고 앵커 즉치를 그쪽으로 돌린다.

    체인 문법은 chain.py 참고. 메시지는 문자열 두 칸을 갖고 그중 하나만 본문인데
    (선택은 런타임 $E824) **원본의 모양을 그대로 보존**하면 판단이 필요없다 —
    비어 있던 칸은 비우고, 본문이던 칸에 번역을 넣는다.
    """
    explicit, memory = load_dialogue()
    sites_of = e82c_sites(src)
    blob, log, stats = bytearray(), [], [0, 0, 0]      # 체인 / 번역메시지 / 원문메시지
    partial: list[tuple[str, int, int]] = []
    for anchor in sorted(sites_of):
        anchor_s = f"{anchor:06X}"
        try:
            msgs = parse_chain(src, anchor)
        except ValueError as e:
            log.append(f"  {anchor_s} 파싱 실패, 건너뜀: {e}")
            continue
        kos = [explicit.get((anchor_s, i)) or memory.get(esc(decode(m["s1"] or m["s2"])))
               for i, m in enumerate(msgs)]
        # 체인은 전부 한글이거나 전부 원문이어야 한다. 글리프 슬롯(타일 128..191)은
        # 게임의 가나 폰트 자리라서, 한 메시지가 한글을 올리면 같은 체인의 남은
        # 일본어 메시지는 그 타일을 가나로 읽어 깨진다.
        if not all(kos):
            stats[2] += len(msgs)
            if any(kos):
                partial.append((anchor_s, sum(1 for k in kos if k), len(msgs)))
            continue

        if len(blob) & 1:
            blob.append(0x00)
        start, over = CHAIN_AT + len(blob), []
        stats[0] += 1
        for i, m in enumerate(msgs):
            text = kos[i]
            stats[1 if text else 2] += 1
            if text is None:
                s1, s2 = m["s1"], m["s2"]          # 원문 그대로
            else:
                slots = assign([text])
                if len(slots) > len(CODES):
                    over.append((i, len(slots)))
                g.add(text)
                enc = g.header(slots) + encode(text, slots)
                s1 = enc if m["s1"] else b""
                s2 = enc if m["s2"] else b""
                if not s1 and not s2:
                    raise SystemExit(f"{anchor_s}[{i}]: 원본에 본문 칸이 없다")
            blob += m["w"].to_bytes(2, "big") + s1 + b"\xff" + s2 + b"\xff"
            if len(blob) & 1:
                blob.append(0x00)    # 짝수 정렬 — 메시지 시작은 짝수여야 한다
        blob += b"\xff\xff"          # 체인 종료 (상위비트가 서면 끝)

        for imm in sites_of[anchor]:
            assert int.from_bytes(rom[imm:imm + 4], "big") == anchor, \
                f"{imm:06X}: 즉치가 {anchor_s} 가 아니다"
            rom[imm:imm + 4] = start.to_bytes(4, "big")
        n_ko = sum(1 for k in kos if k)
        log.append(f"  {anchor_s} -> {start:06X}  메시지 {n_ko}/{len(msgs)} 번역 / "
                   f"{CHAIN_AT + len(blob) - start}B / 즉치 {len(sites_of[anchor])}곳"
                   + (f"  ✗ 코드 초과 {over}" if over else ""))
    log.append(f"  체인 {stats[0]}개 / 메시지 한글 {stats[1]}개, 원문 {stats[2]}개")
    for a, n, tot in partial:
        log.append(f"  {a} 번역 {n}/{tot} — 체인이 덜 찼으므로 원문 그대로 뒀다")
    return bytes(blob), log


def main() -> None:
    src = SRC.read_bytes()
    rom = bytearray(src)
    rom.extend(b"\xff" * (ROM_SIZE - len(rom)))
    vram = VRAM.read_bytes()
    g = Glyphs(vram)
    ko = load_tsv(KO_TSV, 0, 2, 3)

    # 번역이 있는 스테이지만 처리 (나머지는 원문 그대로 남는다)
    stages = [s for s in range(1, 21)
              if all(f"{k}-{s:02d}" in ko for k in KINDS)]
    if not stages:
        raise SystemExit("번역된 스테이지가 없다 (translation/ko.tsv)")
    for s in stages:
        for k in KINDS:
            g.add(ko[f"{k}-{s:02d}"])

    # 글리프 기록표는 이름·UI·프롤로그가 함께 쓴다. UI 업로더가 k 로 색인한다.
    # (타일 번호, 글리프 문자들, 대체 코드 페이지 여부)
    recs: list[tuple[int, list[str], int]] = []
    namestr, nameids, name_n = build_names(g, recs)
    chains, chain_log = build_chains(rom, src, g)
    uistr, ui_log = build_ui(rom, src, g, recs)
    # 메뉴는 폰트가 아니라 미리 그려둔 그래픽이다. 글리프 풀과 타일맵 서술자를
    # 우리가 다시 쓰므로 위의 글리프 테이블·코드표와 아무것도 공유하지 않는다.
    menu_log = menu.build(rom, src)
    # 선택 창 제목 — 압축 풀(리소스 0x81)이라 로드 직후 VRAM 을 덮는다.
    titles, title_log = menu.build_titles(rom, src)
    place(rom, TITLE_AT, titles, "선택 창 제목 타일")
    tcode = build_uploader_block(
        src=TITLE_AT, dst=(menu.TITLE_BASE_TILE + menu.TITLE_OFF) * 32,
        tiles=len(titles) // 32, call_first=menu.GRAPHLOAD)
    place(rom, TITLE_UP_AT, tcode, "제목 업로더")
    want_load = b"\x4e\xb9" + menu.GRAPHLOAD.to_bytes(4, "big")
    for site in menu.TITLE_LOADS:
        assert rom[site:site + 6] == want_load, f"{site:06X} 가 jsr $53B4 아님"
        rom[site:site + 6] = b"\x4e\xb9" + TITLE_UP_AT.to_bytes(4, "big")
    title_log.append(f"  훅 {len(menu.TITLE_LOADS)}곳 (리소스 0x81 로드) -> "
                     f"{TITLE_UP_AT:06X}")
    menu_log += ["  -- 선택 창 제목 (풀 0x81)"] + title_log

    place(rom, NAMESTR_AT, namestr, "이름 문자열표")
    place(rom, NAMEIDS_AT, nameids, "이름 글리프ID표")
    place(rom, UISTR_AT, uistr, "UI 문자열표")
    place(rom, CHAIN_AT, chains, "대사 체인")
    place(rom, LABEL_AT, make_labels(), "승리/패배 라벨")

    # 프롤로그 훅
    want = b"\x4e\xb9" + STRDRAW.to_bytes(4, "big")
    assert rom[HOOK_SITE:HOOK_SITE + 6] == want, f"{HOOK_SITE:06X} 가 jsr ${STRDRAW:X} 아님"
    code = build_uploader_labels(kfont=KFONT_AT, slot_base=SLOT_BASE, target=STRDRAW,
                                 label_src=LABEL_AT, label_dst=LABEL_DST,
                                 label_tiles=LABEL_TILES)
    place(rom, UPLOADER_AT, code, "프롤로그 업로더")
    rom[HOOK_SITE:HOOK_SITE + 6] = b"\x4e\xb9" + UPLOADER_AT.to_bytes(4, "big")

    # 대사 훅 — move.l a1,$E818 (6B) 자리를 jsr (6B) 로 바꾼다
    want2 = b"\x23\xc9\xff\xff\xe8\x18"
    assert rom[MSG_HOOK:MSG_HOOK + 6] == want2, f"{MSG_HOOK:06X} 가 move.l a1,$E818 아님"
    code2 = build_uploader_msg(kfont=KFONT_AT, body_base=SLOT_BASE, name_base=NAME_BASE,
                               name_ids=NAMEIDS_AT, name_n=name_n)
    place(rom, UPLOADER2_AT, code2, "대사 업로더")
    rom[MSG_HOOK:MSG_HOOK + 6] = b"\x4e\xb9" + UPLOADER2_AT.to_bytes(4, "big")

    # 이름 문자열표 포인터
    # 이름 문자열표 포인터 — 대사 이름판 + 유닛 상태창 3변형.
    # 목록 창은 제외한다. 여러 이름이 동시에 보이는데 우리 표는 타일 192..197 을
    # 돌려쓰므로 모든 줄이 마지막 이름으로 변한다.
    for imm in (NAMEPTR_IMM,) + NAMEPTR_PANEL:
        assert int.from_bytes(rom[imm:imm + 4], "big") == NAMETBL_ORIG, \
            f"{imm:06X} 가 이름표 즉치 아님"
        rom[imm:imm + 4] = NAMESTR_AT.to_bytes(4, "big")

    # 코드 -> 타일 매핑은 전 화면 공통이므로 한 번만
    for i, c in enumerate(CODES):
        rom[TABLE_AT + c] = SLOT_BASE + i
    for i, c in enumerate(NAME_CODES):
        rom[TABLE_AT + c] = NAME_BASE + i
    for i, c in enumerate(UI_CODES):
        rom[TABLE_AT + c] = UI_BASE + i

    # 프롤로그 화면 — 세 문자열이 **같은 기록 하나**를 공유한다
    #
    # 처음에는 첫 문자열만 `[0xFE][N][ID x N]` 헤더를 달고 프롤로그 렌더러의 첫
    # draw(0x18D12)에 걸린 훅이 올렸다. 그 훅을 지나지 않는 경로가 있어서 깨졌다 —
    # 전투 중 승리조건 창(0x10C36)이 같은 표를 읽어 `jsr $5F60` 으로 그리는데,
    # 헤더가 그대로 글자로 찍히고 슬롯에는 앞 대사의 글리프가 남아 있었다.
    #
    # 그래서 UI 문자열과 같은 방식으로 바꿨다. 훅이 `$5F60` 안(0x5FD4)에 있으므로
    # **어느 경로로 그려도** 문자열이 자기 글리프를 들고 온다. 세 문자열이 한 화면에
    # 동시에 보이니 기록은 화면 단위 합집합 하나를 공유한다(순서에 안 깨진다).
    at = TEXT_AT
    print(f"{'st':>3}  {'글리프':>5}  {'바이트':>6}   위치")
    over = []
    for s in stages:
        texts = {k: ko[f"{k}-{s:02d}"] for k in KINDS}
        slots = assign([texts[k] for k in KINDS])
        if len(slots) > len(CODES):
            over.append((s, len(slots)))
        rk = len(recs)
        recs.append((SLOT_BASE, list(slots), 0))
        start, total = at, 0
        for k in KINDS:
            blob = bytes([UI_MARKER, rk]) + encode(texts[k], slots) + b"\xff"
            at = place(rom, at, blob, f"화면 {k}-{s:02d}") + 2
            t = TABLES[k]
            rom[t + (s - 1) * 4:t + (s - 1) * 4 + 4] = (at - len(blob) - 2).to_bytes(4, "big")
            total += len(blob)
        mark = "✗" if len(slots) > len(CODES) else " "
        print(f"{s:3d}  {len(slots):3d}/{len(CODES)}{mark} {total:6d}   {start:06X}")

    # 기록표는 프롤로그 화면까지 다 모인 뒤에 굽는다. 글리프 테이블은 이미 위에서
    # 구웠지만 프롤로그 글리프는 main 진입부에서 g.add 로 넣어 뒀으므로 문제없다.
    uitbl = bake_records(recs, g)
    place(rom, UITBL_AT, uitbl, "UI 글리프기록표")
    place(rom, KFONT_AT, g.table(), "글리프 테이블")   # 글리프는 모두 모인 뒤에 굽는다

    # UI 훅 — lea $62BC.l, a2 (6B) 자리를 jsr (6B) 로. 문자열이 자기 글리프를 들고
    # 오므로 그리기 지점마다 훅을 걸 필요가 없다.
    want3 = b"\x45\xf9" + TABLE_AT.to_bytes(4, "big")
    assert rom[UI_HOOK:UI_HOOK + 6] == want3, f"{UI_HOOK:06X} 가 lea ${TABLE_AT:X},a2 아님"
    # 대체 코드 페이지들 — 원본 표를 복사하고 본문 코드만 다른 타일로 돌린다.
    # 그 페이지를 지정한 기록을 쓰는 문자열만 이렇게 그려지므로 남은 일본어는 무사하다.
    pages = bytearray()
    for name, (idx, base) in sorted(PAGES.items(), key=lambda kv: kv[1][0]):
        assert len(pages) == (idx - 1) * 256, f"페이지 {name} 번호가 어긋난다"
        tbl = bytearray(rom[TABLE_AT:TABLE_AT + 256])
        for i, c in enumerate(CODES):
            if base + i < 256:
                tbl[c] = base + i
        pages += tbl
    place(rom, ALTTBL_AT, bytes(pages), "대체 코드 페이지")

    code3 = build_uploader_ui(kfont=KFONT_AT, uitbl=UITBL_AT, nrec=len(recs),
                              stride=UI_REC, table_at=TABLE_AT, alt_table=ALTTBL_AT)
    place(rom, UI_UPLOADER_AT, code3, "UI 업로더")
    rom[UI_HOOK:UI_HOOK + 6] = b"\x4e\xb9" + UI_UPLOADER_AT.to_bytes(4, "big")

    rom[0x1A4:0x1A8] = (ROM_SIZE - 1).to_bytes(4, "big")
    # 체크섬 — 개발 중에는 우회(0x18E = 0)를 쓴다. 0x4630 의 검사 루틴이 0 이면
    # 비교를 건너뛰기 때문이고, 매 빌드 재계산을 한 번 빠뜨리면 원인 불명의 빨간
    # 화면을 보게 된다. **배포판은 --release 로 정상값을 넣는다** (docs/RELEASE.md).
    release = "--release" in sys.argv
    if release:
        total = sum(int.from_bytes(rom[p:p + 2], "big")
                    for p in range(0x200, ROM_SIZE, 2)) & 0xFFFF
        rom[0x18E:0x190] = total.to_bytes(2, "big")
    else:
        rom[0x18E] = rom[0x18F] = 0

    out = Path("work/korom_all.md")
    out.write_bytes(rom)
    print(f"체크섬  {'정상 기록 (배포용)' if release else '우회 0x18E = 0000 (개발용)'}")
    menu.preview(src, rom, Path("work/menu_preview.png"))
    print("\nUI 문자열표")
    print("\n".join(ui_log))
    print("\n메뉴 그래픽 (풀 재배치 + 서술자 재작성)")
    print("\n".join(menu_log))
    print("\n대사 체인")
    print("\n".join(chain_log))
    print(f"\n전역 글리프 {len(g.gid)}개 / 이름 {name_n}개")
    pro = [r for r in PLACED if r[2].startswith("화면 ")]
    for s, e, label in sorted(r for r in PLACED if r not in pro):
        print(f"  {s:06X}..{e:06X}  {e - s:6d}B  {label}")
    print(f"  {min(pro)[0]:06X}..{max(pro)[1]:06X}  "
          f"{sum(e - s for s, e, _ in pro):6d}B  프롤로그 화면 텍스트 {len(pro)}개")
    if over:
        print(f"\n✗ 코드 초과: {over}  — 어휘를 줄이거나 CODES 를 늘려야 한다")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
