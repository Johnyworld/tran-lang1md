#!/usr/bin/env python3
"""롬 패치 빌더. 원본은 절대 수정하지 않고 work/ 에 사본을 만든다.

메가드라이브 헤더 체크섬은 0x18E 에 있고, 0x200 부터 끝까지의 16비트 워드 합
(mod 0x10000) 이다. 이 게임이 부팅 시 체크섬을 검사하는지는 아직 모른다.
--no-checksum 으로 검사 여부를 실험할 수 있다.
"""
import argparse
import shutil
from pathlib import Path

SRC = Path("/Users/rotein/Downloads/Langrisser.md")
CHECKSUM_AT = 0x18E
CHECKSUM_FROM = 0x200


def checksum(rom: bytes) -> int:
    total = 0
    for i in range(CHECKSUM_FROM, len(rom) - 1, 2):
        total += (rom[i] << 8) | rom[i + 1]
    return total & 0xFFFF


def patch(rom: bytearray, at: int, data: bytes, label: str = "") -> None:
    """지정 위치에 바이트를 덮어쓴다. 길이가 늘어나는 일은 없어야 한다."""
    if at + len(data) > len(rom):
        raise ValueError(f"{label}: 롬 범위 초과")
    rom[at:at + len(data)] = data
    print(f"  patch {at:06X} +{len(data):<4d} {label}")


def build(out: Path, patches: list[tuple[int, bytes, str]], fix_checksum: bool) -> None:
    rom = bytearray(SRC.read_bytes())
    orig = checksum(rom)
    stored = (rom[CHECKSUM_AT] << 8) | rom[CHECKSUM_AT + 1]
    print(f"원본 체크섬: 저장값 {stored:04X} / 계산값 {orig:04X}"
          f" {'일치' if stored == orig else '불일치'}")

    for at, data, label in patches:
        patch(rom, at, data, label)

    new = checksum(rom)
    if fix_checksum:
        rom[CHECKSUM_AT] = new >> 8
        rom[CHECKSUM_AT + 1] = new & 0xFF
        print(f"체크섬 재계산: {new:04X}")
    else:
        print(f"체크섬 그대로 둠 (계산값은 {new:04X})")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(rom)
    print(f"-> {out}  ({len(rom):,} bytes)")


# ---------------------------------------------------------------- 테스트 문자열
NL = b"\x0d\x0d"          # 한 줄 = 0x0D 두 개 (렌더러가 Y+=1, 글리프는 2행)
TEST = (
    b"KOROM TEST" + NL           # ASCII 경로
    + b"\xc3\xbd\xc4" + NL       # 카타카나 (기본 모드)
    + b"\x7e\xc3\xbd\xc4\x7e" + NL   # 히라가나 (0x7E 토글 on/off)
    + b"\xc3\xde"                # 탁점 결합
    + b"\xff"                    # 종료
)
PROLOGUE_AT = 0x38C42


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-checksum", action="store_true",
                    help="체크섬을 고치지 않는다 (검사 여부 실험용)")
    ap.add_argument("-o", "--out", default="work/test.md")
    a = ap.parse_args()
    print(f"테스트 문자열 {len(TEST)} bytes (원본 메시지 자리에 덮어씀)")
    build(Path(a.out), [(PROLOGUE_AT, TEST, "프롤로그 자리 테스트 문자열")],
          fix_checksum=not a.no_checksum)


if __name__ == "__main__":
    main()
