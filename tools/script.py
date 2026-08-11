#!/usr/bin/env python3
"""랑그릿사(MD) 대본 코덱 + 추출기.

확정된 텍스트 인코딩
--------------------
  0x0D            줄바꿈
  0x20..0x7D      ASCII 그대로 (0x20 = 공백)
  0x7E            히라가나 모드 토글 (기본은 카타카나)
  0xA1..0xDD      JIS X 0201 가나 — 기본은 카타카나, 토글 중이면 히라가나
  0x2D            카타카나 모드에서 장음 ー 로 쓰인다 (ASCII '-')
  0xDE            탁점  ゛ (직전 글자에 결합)
  0xDF            반탁점 ゜ (직전 글자에 결합)
  0xFF 0x00       메시지 종료

폰트는 8x16 = 세로로 붙은 두 타일이고 탁점은 윗줄 타일에 얹힌다.
그래서 대본에서도 탁점이 별도 바이트로 뒤에 온다.
"""
import json
import sys
from pathlib import Path

JIS = ("。「」、・ヲァィゥェォャュョッー"
       "アイウエオカキクケコサシスセソ"
       "タチツテトナニヌネノハヒフヘホマ"
       "ミムメモヤユヨラリルレロワン゛゜")
KATA = {i + 0xA1: c for i, c in enumerate(JIS)}
PUNCT = "。「」、・ー"
TO_HIRA = str.maketrans(
    "ヲァィゥェォャュョッアイウエオカキクケコサシスセソタチツテトナニヌネノ"
    "ハヒフヘホマミムメモヤユヨラリルレロワン",
    "をぁぃぅぇぉゃゅょっあいうえおかきくけこさしすせそたちつてとなにぬねの"
    "はひふへほまみむめもやゆよらりるれろわん")
DAKU = dict(zip("カキクケコサシスセソタチツテトハヒフヘホウかきくけこさしすせそたちつてとはひふへほう",
                "ガギグゲゴザジズゼゾダヂヅデドバビブベボヴがぎぐげござじずぜぞだぢづでどばびぶべぼゔ"))
HANDAKU = dict(zip("ハヒフヘホはひふへほ", "パピプペポぱぴぷぺぽ"))

TERM = b"\xff"      # 0xFF = 메시지 종료 (뒤에 0x00 이 따라오는 경우가 많다)


def decode(data: bytes) -> str:
    """바이트열 -> 사람이 읽는 일본어. 탁점은 앞 글자에 합성한다."""
    out: list[str] = []
    hira = False          # 기본은 카타카나
    for b in data:
        if b == 0x7E:
            hira = not hira
        elif b == 0x0D:
            out.append("\n")
        elif b == 0xDE and out:
            out[-1] = DAKU.get(out[-1], out[-1])
        elif b == 0xDF and out:
            out[-1] = HANDAKU.get(out[-1], out[-1])
        elif 0x20 <= b <= 0x7D:
            out.append(chr(b))
        elif b in KATA:
            c = KATA[b]
            out.append(c if c in PUNCT else (c.translate(TO_HIRA) if hira else c))
        else:
            out.append(f"<{b:02X}>")
    return "".join(out)


def find_tables(rom: bytes, lo: int, hi: int, min_entries: int = 8) -> list[tuple[int, int]]:
    """대본 영역을 가리키는 연속 32비트 포인터 배열을 찾는다."""
    ptr = [i for i in range(0, len(rom) - 4, 2)
           if lo <= int.from_bytes(rom[i:i + 4], "big") < hi]
    tables, i = [], 0
    while i < len(ptr):
        j = i
        while j + 1 < len(ptr) and ptr[j + 1] - ptr[j] == 4:
            j += 1
        if j - i + 1 >= min_entries:
            tables.append((ptr[i], j - i + 1))
        i = j + 1
    return tables


KANA_BYTES = set(range(0xA1, 0xE0)) | {0x20, 0x0D, 0x7E}


def is_dialogue(raw: bytes) -> bool:
    """대본 메시지인지 판정 — 실제 가나가 충분히 있어야 한다."""
    if len(raw) < 6:
        return False
    if sum(1 for b in raw if b in KANA_BYTES) < len(raw) * 0.85:
        return False
    # 공백·줄바꿈만 있는 레이아웃 조각을 걸러낸다
    return sum(1 for b in raw if 0xA1 <= b <= 0xDD) >= 4


def skip_term(rom: bytes, ff: int) -> int:
    """0xFF 종료자 위치 -> 다음 메시지 시작. 종료자는 0xFF 또는 0xFF 0x00 이다."""
    p = ff + 1
    return p + 1 if rom[p:p + 1] == b"\x00" else p


PTR_TABLES = [(0x38A38, 20), (0x38BF2, 20), (0x3962E, 20),
              (0x2087C, 14), (0x3A322, 11)]


def seeds(rom: bytes) -> set[int]:
    """게임이 실제로 사용하는 메시지 시작 주소 — 이것만이 정렬의 근거다.

    포인터 테이블 엔트리 + 코드 즉치(refs.json). 블록 경계 추측은 쓰지 않는다.
    """
    out = set()
    for tbl, n in PTR_TABLES:
        for k in range(n):
            out.add(int.from_bytes(rom[tbl + k * 4:tbl + k * 4 + 4], "big"))
    refs = Path("work/refs.json")
    if refs.exists():
        out |= {int(r["target"], 16) for r in json.loads(refs.read_text())}
    return {a for a in out if a < len(rom)}


def extract(rom: bytes, blocks: list[tuple[int, int]]) -> list[dict]:
    """검증된 앵커에서 시작해 0xFF 구분자를 따라 앞으로 걸어나간다.

    앵커가 없는 블록은 블록 시작 직전 0xFF 뒤에서 시작한다(정렬 보장 없음).
    """
    msgs, seen = [], set()

    def walk(pos: int, hi: int, strict: bool) -> None:
        """strict=True  앵커에서 출발 — 비대사를 만나면 뱅크 끝으로 보고 멈춘다.
        strict=False  블록 훑기 — 비대사는 건너뛰며 계속한다(정렬 보장 없음)."""
        while pos < hi:
            end = rom.find(TERM, pos, hi)
            if end < 0:
                break
            raw = rom[pos:end]
            if is_dialogue(raw):
                if pos not in seen:
                    seen.add(pos)
                    msgs.append({"addr": f"{pos:06X}", "len": len(raw),
                                 "text": decode(raw), "anchor": pos in ANCHORS})
            elif strict:
                break
            pos = skip_term(rom, end)

    ANCHORS = seeds(rom)
    for a in sorted(ANCHORS):
        walk(a, min(len(rom), a + 8192), strict=True)
    for off, n in blocks:
        hi = min(len(rom), off + n + 64)
        prev = rom.rfind(b"\xff", max(0, off - 512), off)
        walk(skip_term(rom, prev) if prev >= 0 else off, hi, strict=False)
    return sorted(msgs, key=lambda m: m["addr"])


def main() -> None:
    rom = Path(sys.argv[1] if len(sys.argv) > 1
               else "/Users/rotein/Downloads/Langrisser.md").read_bytes()
    blocks = [(int(a, 16), int(b)) for a, b in
              (ln.split() for ln in
               Path("work/script_blocks.txt").read_text().split("\n") if ln)]
    msgs = extract(rom, blocks)

    Path("work/script.json").write_text(json.dumps(msgs, ensure_ascii=False, indent=1))
    # 번역용 워크시트 (jp 칸 옆에 kr 을 채워 넣는다)
    with Path("work/script.tsv").open("w") as f:
        f.write("addr\tlen\tjp\tkr\n")
        for m in msgs:
            f.write(f"{m['addr']}\t{m['len']}\t{m['text'].replace(chr(10), '\\n')}\t\n")

    total = sum(m["len"] for m in msgs)
    chars = sum(len(m["text"].replace("\n", "")) for m in msgs)
    print(f"블록 {len(blocks)}개에서 메시지 {len(msgs)}개 추출")
    print(f"원본 {total:,} bytes / 일본어 {chars:,}자")
    print("-> work/script.json, work/script.tsv")


if __name__ == "__main__":
    main()
