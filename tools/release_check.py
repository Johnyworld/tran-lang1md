#!/usr/bin/env python3
"""배포판 검사 — 번역이 아닌 변경이 남아 있지 않은지 기계가 본다.

`docs/RELEASE.md` 의 항목을 그대로 확인한다. 사람이 눈으로 훑는 대신,
빠뜨리면 실패하게 만드는 것이 목적이다.
"""
import sys
from pathlib import Path

SRC = Path("/Users/rotein/Downloads/Langrisser.md")
ROM = Path(sys.argv[1] if len(sys.argv) > 1 else "work/korom_all.md")
CLS_TBL, CLS_N, CLS_STRIDE = 0x2C06C, 91, 128
NOTE_AT, DEBUG_NOTE = 0x1C8, b"DEBUG"
ROM_SIZE = 0x100000
# 디버그 롬이 코드에 손대는 자리. 표 비교로는 안 잡히므로 따로 적는다.
# 늘어나면 여기 한 줄 추가 — docs/RELEASE.md 와 짝을 맞춘다.
# (주소, 길이, 설명) — 길이로 비교한다. 한 바이트만 보면 4바이트 즉치의 변경을
# 놓친다 (0x31020 -> 0x32A8E 는 앞 두 바이트가 같다. 실제로 한 번 놓쳤다).
CODE_SITES = ((0xD4D5, 1, "전직 레벨 조건 (cmpi.b #$A, $8(a1))"),
              (0x10528, 4, "마법못씀 팝업 레코드 즉치 (--force-popup)"),
              (0x11E8E, 4, "아이템없음 팝업 레코드 즉치 (예전 트리거)"))


def main() -> None:
    rom, src = ROM.read_bytes(), SRC.read_bytes()
    fails = []

    total = sum(int.from_bytes(rom[p:p + 2], "big")
                for p in range(0x200, len(rom), 2)) & 0xFFFF
    stored = int.from_bytes(rom[0x18E:0x190], "big")
    ok = stored == total
    print(f"{'OK ' if ok else '✗  '} 체크섬  기록 {stored:04X} / 실제 {total:04X}"
          + ("" if ok else "  <- 우회가 남아 있다. --release 로 빌드할 것"))
    if not ok:
        fails.append("체크섬")

    note = rom[NOTE_AT:NOTE_AT + 32]
    ok = DEBUG_NOTE not in note
    print(f"{'OK ' if ok else '✗  '} 헤더 표식  {note.rstrip(bytes([0x20, 0x00]))!r}")
    if not ok:
        fails.append("디버그 표식")

    for at, n, what in CODE_SITES:
        ok = rom[at:at + n] == src[at:at + n]
        print(f"{'OK ' if ok else '✗  '} 코드 {at:06X}  {what}  "
              f"{src[at:at+n].hex()} / 지금 {rom[at:at+n].hex()}")
        if not ok:
            fails.append(f"코드 {at:06X}")

    end = CLS_TBL + CLS_N * CLS_STRIDE
    ok = rom[CLS_TBL:end] == src[CLS_TBL:end]
    print(f"{'OK ' if ok else '✗  '} 클래스 스탯 표 {CLS_TBL:06X}..{end:06X}  "
          + ("원본과 동일" if ok else "달라졌다 — 디버그 강화가 샜다"))
    if not ok:
        fails.append("스탯 표")

    ok = int.from_bytes(rom[0x1A4:0x1A8], "big") == ROM_SIZE - 1 and len(rom) == ROM_SIZE
    print(f"{'OK ' if ok else '✗  '} 롬 크기  {len(rom)} / 헤더 끝 "
          f"{int.from_bytes(rom[0x1A4:0x1A8], 'big'):06X}")
    if not ok:
        fails.append("롬 크기")

    print()
    if fails:
        raise SystemExit(f"✗ 배포 불가 — {', '.join(fails)}")
    print("배포 가능")


if __name__ == "__main__":
    main()
