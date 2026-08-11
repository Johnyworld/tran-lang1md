#!/usr/bin/env python3
"""스테이지 이벤트 표 -> 대사 앵커. 번역을 **이야기 순서**로 놓기 위한 도구.

`work/refs.json` 은 앵커를 전부 찾아주지만 순서가 없다. 대사는 앞뒤 맥락에 따라
말투와 호칭이 달라지므로, 어느 스테이지 몇 번째 이벤트인지 알고 번역해야 한다.

표 구조 (0x32BB0 을 읽어 확정)
------------------------------
```
0x32BB0   스테이지 포인터 20개 -> 각 스테이지의 이벤트 목록
목록      (조건 루틴, 동작 루틴) 쌍 x N, 0xFFFFFFFF 로 끝
동작      move.l #메시지주소, $E82C.w  +  move.l #$1533A, d0  +  jsr $485E
```

조건 루틴도 코드다. 예: 스테이지 1 첫 이벤트 `0x3306A` 는 `$ae72 == 1` 을 보고
`$E830` 의 비트로 한 번만 켜지게 한다 — 스테이지 시작 직후 재생된다는 뜻이다.
"""
import sys
from pathlib import Path

STAGE_PTRS, NSTAGE = 0x32BB0, 20
RTS, TERM = 0x4E75, 0xFFFFFFFF
SET_E82C = bytes.fromhex("21fc")            # move.l #imm, (d16).w
E82C_DISP = bytes.fromhex("e82c")
MAX_ROUTINE = 512


def anchors_in(rom: bytes, routine: int) -> list[int]:
    """동작 루틴이 싣는 메시지 주소들. rts 까지 훑는다.

    한 루틴이 조건에 따라 두 메시지 중 하나를 고르는 경우가 있어(0x181E6) 목록이다.
    """
    out, p, end = [], routine, min(len(rom) - 6, routine + MAX_ROUTINE)
    while p < end:
        if rom[p:p + 2] == SET_E82C and rom[p + 6:p + 8] == E82C_DISP:
            out.append(int.from_bytes(rom[p + 2:p + 6], "big"))
            p += 8
            continue
        if int.from_bytes(rom[p:p + 2], "big") == RTS:
            break
        p += 2
    return out


def e82c_sites(rom: bytes) -> dict[int, list[int]]:
    """메시지 주소 -> 그 주소를 `$E82C` 에 넣는 즉치 위치들.

    앵커를 다른 자리로 옮기려면 이 즉치를 전부 고쳐야 한다. `work/refs.json` 은
    대본 주소 범위로 걸러낸 목록이라 이벤트 표에만 있는 앵커(0x18BC6 등)를
    놓친다. 8바이트 패턴을 직접 훑으면 그런 누락이 없다.
    """
    out: dict[str, list[int]] = {}
    for p in range(0, len(rom) - 8, 2):
        if rom[p:p + 2] == SET_E82C and rom[p + 6:p + 8] == E82C_DISP:
            out.setdefault(int.from_bytes(rom[p + 2:p + 6], "big"), []).append(p + 2)
    return out


def stage_events(rom: bytes) -> list[list[tuple[int, int, list[int]]]]:
    """스테이지별 [(조건, 동작, [앵커...])]."""
    stages = []
    for s in range(NSTAGE):
        lst = int.from_bytes(rom[STAGE_PTRS + s * 4:STAGE_PTRS + s * 4 + 4], "big")
        events, p = [], lst
        while True:
            cond = int.from_bytes(rom[p:p + 4], "big")
            if cond == TERM:
                break
            act = int.from_bytes(rom[p + 4:p + 8], "big")
            events.append((cond, act, anchors_in(rom, act)))
            p += 8
        stages.append(events)
    return stages


if __name__ == "__main__":
    rom = Path(sys.argv[1] if len(sys.argv) > 1
               else "/Users/rotein/Downloads/Langrisser.md").read_bytes()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from chain import parse_chain
    from script import decode

    total = 0
    for s, events in enumerate(stage_events(rom), 1):
        print(f"== 스테이지 {s}  이벤트 {len(events)}개")
        for i, (cond, act, anchors) in enumerate(events):
            for a in anchors:
                try:
                    msgs = parse_chain(rom, a)
                except ValueError as e:
                    print(f"  {i:2d} {a:06X}  파싱 실패: {e}")
                    continue
                total += len(msgs)
                first = decode(msgs[0]["s1"] or msgs[0]["s2"]) if msgs else ""
                print(f"  {i:2d} {a:06X}  cond {cond:06X}  메시지 {len(msgs):2d}  "
                      f"{first.replace(chr(10), ' ')[:44]}")
            if not anchors:
                print(f"  {i:2d} ------  cond {cond:06X}  act {act:06X}  (대사 없음)")
    print(f"\n총 메시지 {total}개")
