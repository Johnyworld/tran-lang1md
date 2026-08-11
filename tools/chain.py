#!/usr/bin/env python3
"""본편 대사 스트림 파서 — 앵커 하나에서 대화 한 덩이(체인)를 통째로 읽는다.

프롤로그는 포인터 테이블이 있어 문자열 단위로 다뤘지만, 본편 대사는 앵커
주소가 **코드 즉치**로 박혀 있고(`move.l #msg, $E82C.w`) 인터프리터가 그
자리에서 여러 메시지를 이어 재생한다. 그래서 번역 단위는 문자열이 아니라
**체인**이다.

인터프리터(0x1533A~)를 읽어 확정한 문법
---------------------------------------
메시지 시작 위치는 **짝수 정렬**이다 (0x1537A / 0x156CC 의 `btst #0`).

    message := W:word  str1 0xFF  str2 0xFF
    chain   := message*  (W 의 상위비트가 서면 종료)

  W          화자·연출 코드. 0x1F4 = $E83A 참조, 0x50..0xA0 = $E82A 설정 후
             창만 열기, 그 밖 = 초상화 테이블 참조. 상위비트가 서 있으면
             (= 첫 바이트가 0x80 이상, 실제 데이터에서는 0xFF) 체인 끝.
  str1       화면에 그려지는 본문. 0x15650 이 a1 에 담아 `jsr $60BE` 로 그린다.
  str2       $E824(화자 테이블에서 옴) 가 0 이면 건너뛰어진다. 실제 데이터에서는
             비어 있거나 str1 의 사본이다. 런타임 값을 모르니 **원본의 모양을
             그대로 보존**한다 — 비어 있었으면 비우고, 사본이었으면 사본을 넣는다.

렌더러는 프롤로그와 같은 `$5F60` 이다 ($60BE 는 카메라 오프셋만 더하는 껍데기).
따라서 코드->타일 표 `$62BC` 와 8x8 글리프 슬롯 배정이 그대로 통한다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from script import decode  # noqa: E402

TERM = 0xFF


def parse_chain(rom: bytes, anchor: int, limit: int = 64) -> list[dict]:
    """앵커에서 체인 하나를 읽는다. 반환값은 메시지 목록.

    각 메시지: {"at", "w", "s1", "s2", "dup"}
      dup   str2 가 str1 의 사본인지 (모양 보존용)
    """
    msgs, pos = [], anchor
    while len(msgs) < limit:
        if pos & 1:
            pos += 1
        w = int.from_bytes(rom[pos:pos + 2], "big")
        if w & 0x8000:
            break
        at, pos = pos, pos + 2
        parts = []
        for _ in range(2):
            end = rom.find(bytes([TERM]), pos)
            if end < 0:
                raise ValueError(f"{pos:06X}: 종료자 없음")
            parts.append(rom[pos:end])
            pos = end + 1
        s1, s2 = parts
        msgs.append({"at": at, "w": w, "s1": s1, "s2": s2, "dup": bool(s2) and s2 == s1})
    return msgs


def chain_span(rom: bytes, anchor: int) -> tuple[int, int]:
    """체인이 차지하는 [시작, 끝) 바이트 범위. 끝은 종료 워드를 포함한다."""
    msgs = parse_chain(rom, anchor)
    if not msgs:
        return anchor, anchor + 2
    last = msgs[-1]
    pos = last["at"] + 2 + len(last["s1"]) + 1 + len(last["s2"]) + 1
    if pos & 1:
        pos += 1
    return anchor, pos + 2


def show(rom: bytes, anchor: int) -> None:
    msgs = parse_chain(rom, anchor)
    lo, hi = chain_span(rom, anchor)
    print(f"{anchor:06X}  메시지 {len(msgs)}개 / {hi - lo} bytes  [{lo:06X}..{hi:06X})")
    for i, m in enumerate(msgs):
        tag = "dup" if m["dup"] else ("s2" if m["s2"] else "-")
        print(f"  {i}  {m['at']:06X}  W={m['w']:04X} {tag:>3}  "
              f"{decode(m['s1']).replace(chr(10), ' / ')}")


STAGE1 = [0x333BA, 0x332E8, 0x33302, 0x33322, 0x33376, 0x3354A, 0x33348]

if __name__ == "__main__":
    rom = Path(sys.argv[1] if len(sys.argv) > 1
               else "/Users/rotein/Downloads/Langrisser.md").read_bytes()
    args = sys.argv[2:]
    for a in ([int(x, 16) for x in args] if args else STAGE1):
        show(rom, a)
        print()
