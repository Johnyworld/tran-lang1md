#!/usr/bin/env python3
"""남은 일본어 UI 문자열 전수 조사 — 무엇이 아직 원문인지 기계가 세게 한다.

찾는 방법
---------
UI 텍스트는 예외 없이 다음 셋 중 하나로 그려진다(STATUS 참고).

```
lea <문자열>, a1   + jsr $5F60 / $5F7A     낱개 문자열·표 엔트리
창 레코드 종류 4                            [폭][높이][0xC000][4][포인터]
표 + lsl.w #4 색인                          클래스·마법·아이템·이름 (16B 고정)
```

그래서 **모든 `lea imm.l` 즉치를 훑어 그 자리가 일본어 문자열인지 판정**하면 목록이
나온다. 판정은 코덱으로 디코드해 가나 바이트가 있고 `0xFF` 로 끝나는지 본다.

`translation/*.tsv` 에 이미 있는 것은 제외한다. 남은 것이 곧 할 일이다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from script import decode  # noqa: E402

SRC = Path("/Users/rotein/Downloads/Langrisser.md")
KANA = range(0xA1, 0xE0)
MAXLEN = 64                      # 이보다 길면 UI 문자열이 아니다 (대본은 따로 센다)
SCRIPT = (0x32000, 0x3A400)      # 주 대본 — UI 조사에서 제외


def strings_at(src: bytes, at: int) -> str | None:
    """그 자리가 UI 문자열이면 디코드해서 돌려준다. 아니면 None."""
    end = src.find(b"\xff", at)
    if end < 0 or end - at > MAXLEN or end == at:
        return None
    body = src[at:end]
    if not any(b in KANA for b in body):
        return None              # 가나가 없으면 영어 라벨 — 번역 대상 아님
    if any(b < 0x0D or 0x14 <= b < 0x20 for b in body):
        return None              # 제어 바이트가 섞이면 문자열이 아니다
    return decode(body)


def lea_targets(src: bytes) -> dict[int, list[int]]:
    """`lea imm.l, aN` 즉치 -> 그 즉치가 놓인 위치들."""
    out: dict[int, list[int]] = {}
    for p in range(0, len(src) - 6, 2):
        if src[p] & 0xF1 == 0x41 and src[p + 1] == 0xF9:
            v = int.from_bytes(src[p + 2:p + 6], "big")
            if 0x200 <= v < 0x80000:
                out.setdefault(v, []).append(p + 2)
    return out


def known() -> set[int]:
    """이미 번역한 주소들 — 표 엔트리는 표 시작 주소로 표시한다."""
    done = {0x2AE64, 0x2B334, 0x2B8E4, 0x2B9AC,        # 이름·클래스·아이템·마법 표
            0x38A38, 0x38BF2, 0x3962E}                  # 프롤로그 화면 표
    for ln in Path("translation/ui.tsv").read_text().rstrip("\n").split("\n")[1:]:
        c = ln.split("\t")
        if c[0] in ("system", "str"):
            done.add(int(c[1], 16))
            if c[0] == "system":                        # 창 레코드 +8 이 문자열
                done.add(int(c[1], 16) + 8)
    return done


def main() -> None:
    src = SRC.read_bytes()
    leas = lea_targets(src)
    done = known()

    # 1) lea 로 오는 낱개 문자열
    print("== lea 로 그려지는 남은 일본어")
    n = 0
    for at in sorted(leas):
        if SCRIPT[0] <= at < SCRIPT[1] or at in done:
            continue
        txt = strings_at(src, at)
        if txt:
            n += 1
            print(f"  {at:06X}  lea {len(leas[at])}곳  {txt!r}")
    print(f"  -> {n}개")

    # 2) 창 레코드 종류 4 (텍스트 창)
    print("\n== 창 레코드 종류 4 중 남은 일본어")
    n = 0
    for p in range(0, len(src) - 12, 2):
        if int.from_bytes(src[p + 4:p + 6], "big") != 0xC000:
            continue
        if int.from_bytes(src[p + 6:p + 8], "big") != 4:
            continue
        w = int.from_bytes(src[p:p + 2], "big")
        h = int.from_bytes(src[p + 2:p + 4], "big")
        ptr = int.from_bytes(src[p + 8:p + 12], "big")
        if not (0x200 <= ptr < 0x40000 and 0 < w <= 64 and 0 < h <= 32):
            continue
        if p in done:
            continue
        end = src.find(b"\xff", ptr + 4)
        if end < 0 or end - ptr > 400:
            continue
        txt = decode(src[ptr + 4:end])
        if any(b in KANA for b in src[ptr + 4:end]):
            n += 1
            print(f"  {p:06X}  {w}x{h}  {txt!r}")
    print(f"  -> {n}개")

    # 3) 16B 고정 표 — 원본을 아직 읽는 자리가 곧 남은 일본어다.
    #    표 자체는 건드리지 않고 우리 사본으로 즉치만 돌리므로, 안 돌린 자리는
    #    원문이 나온다. 그게 의도인 곳(여러 이름이 동시에 보이는 창)도 있다.
    built = Path("work/korom_all.md")
    if not built.exists():
        print("\n(work/korom_all.md 가 없어 표 조사는 건너뜀)")
        return
    rom = built.read_bytes()
    print("\n== 원본 16B 표를 아직 읽는 lea 자리 (빌드된 롬 기준)")
    for name, at in (("이름", 0x2AE64), ("클래스", 0x2B334),
                     ("아이템", 0x2B8E4), ("마법", 0x2B9AC)):
        sites = leas.get(at, [])
        left = [p for p in sites if int.from_bytes(rom[p:p + 4], "big") == at]
        print(f"  {name:4s} {at:06X}  {len(left)}/{len(sites)}곳 남음  "
              + " ".join(f"{p:06X}" for p in left))


if __name__ == "__main__":
    main()
