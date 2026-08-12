#!/usr/bin/env python3
"""테스트용 디버그 롬 — 아군을 강하게 만들어 진도를 빨리 낸다.

레벨업·전직 팝업처럼 **게임을 진행해야 보이는 화면**을 확인하려면 스테이지를
빨리 넘겨야 한다. 배포판과 섞이지 않게 파일을 따로 뽑는다.

클래스 스탯 표 (실측)
---------------------
```
$B5A0  lea $2C06C, a0 / a0 += 클래스 x 128     -> 클래스별 128바이트 레코드
```
클래스 번호는 이름표(`0x2B334`)와 같은 색인이다. 레코드 1 이 파이터고 값이
레딘의 L1 실측값(HP10 AT23 DF21 MV6, 지휘범위 3)과 정확히 맞아 확정했다.

알아낸 필드
```
+02  HP        전투 병력 수 — 10 이 최대로 보이므로 건드리지 않는다
+04  MP
+06  AT
+08  DF
+0A  MV
+70  지휘범위
+78  수정 A+
+7A  수정 D+
+7C  레벨업 경험치 문턱 / 8      (0x0D3BA: d1 = $7C(a2) << 3, EXP 와 비교)
```
`+78/+7A` 는 볼코프(소드마스터 = 레코드 7)의 실측값 `A+0 D+9` 로 교차 검증했다.
처음에 `+7A/+7C` 로 적었는데 클래스 7 이 `9, 3` 이어서 틀린 것이 드러났다.

레벨·전직 규칙 (실측)
---------------------
```
0x0D3B0  7(a1) += 획득 EXP           유닛 +07 = 누적 EXP, +08 = 레벨
0x0D3C0  문턱 = 클래스 +7C x 8       파이터 16 / 로드 32 / 소드마스터·나이트 24
0x0D3D2  레벨 9 이상 + 전직 후보 없음($FFE252 == -1) 이면 레벨 정지
0x0D4D2  cmpi.b #$A, $8(a1)          **전직은 레벨 10 부터** (그 아래는 팝업 안 뜬다)
```

클래스 1..33 이 광 진영(아군) 계열이고 34..62 가 암 진영이다. 표에 같은 이름이
세 벌씩 있는 것(1,2,3 파이터 / 4,5,6 로드)이 그 구획의 근거다.
"""
import sys
from pathlib import Path

CLS_TBL, CLS_STRIDE = 0x2C06C, 128
ALLY = range(1, 34)              # 광 진영 계열
FOE = range(34, 63)              # 암 진영 계열
OFF = {"MP": 4, "AT": 6, "DF": 8, "MV": 0xA, "CMD": 0x70}

BOOST = {"MP": 99, "AT": 99, "DF": 99, "MV": 40, "CMD": 8}
WEAKEN = {"AT": 1, "DF": 1}
EXP_OFF, EXP_FAST = 0x7C, 0          # 문턱 = 값 x 8 -> 0 이면 한 마리로 레벨업
# 전직 레벨 조건. `cmpi.b #$A, $8(a1)` 의 즉치 바이트 한 개다.
CC_IMM, CC_ORIG, CC_DEBUG = 0xD4D5, 0x0A, 0x01

IN, OUT = Path("work/korom_all.md"), Path("work/korom_debug.md")
# 헤더 노트 필드(게임 동작과 무관)에 표식을 남긴다. 나중에 어느 파일이 무엇인지
# 구분되고, `build_all.py --release` 와 `release_check.py` 가 이것을 거부한다.
NOTE_AT, NOTE = 0x1C8, b"DEBUG BUILD - NOT FOR RELEASE"


def poke(rom: bytearray, cls: int, field: str, value: int) -> int:
    at = CLS_TBL + cls * CLS_STRIDE + OFF[field]
    old = int.from_bytes(rom[at:at + 2], "big")
    rom[at:at + 2] = value.to_bytes(2, "big")
    return old


def main() -> None:
    weak = "--weak-enemy" in sys.argv
    if not IN.exists():
        raise SystemExit(f"{IN} 가 없다 — 먼저 python3 tools/build_all.py")
    rom = bytearray(IN.read_bytes())

    for cls in ALLY:
        for field, value in BOOST.items():
            poke(rom, cls, field, value)
        at = CLS_TBL + cls * CLS_STRIDE + EXP_OFF
        rom[at:at + 2] = EXP_FAST.to_bytes(2, "big")
    print(f"아군 클래스 {ALLY.start}..{ALLY.stop - 1}: "
          + " ".join(f"{k}={v}" for k, v in BOOST.items())
          + f" / 레벨업 문턱 {EXP_FAST * 8} EXP")
    assert rom[CC_IMM] == CC_ORIG, f"{CC_IMM:06X} 가 전직 레벨 조건이 아니다"
    rom[CC_IMM] = CC_DEBUG
    print(f"전직 레벨 조건 {CC_IMM:06X}: {CC_ORIG} -> {CC_DEBUG} "
          f"(레벨 {CC_DEBUG} 부터 전직 팝업)")
    if weak:
        for cls in FOE:
            for field, value in WEAKEN.items():
                poke(rom, cls, field, value)
        print(f"적 클래스 {FOE.start}..{FOE.stop - 1}: "
              + " ".join(f"{k}={v}" for k, v in WEAKEN.items()))

    # 레딘(클래스 1) 이 실제로 바뀌었는지 눈으로 확인할 수 있게 찍는다
    p = CLS_TBL + 1 * CLS_STRIDE
    print(f"\n클래스 1 (레딘) @ {p:06X}")
    for field in ("MP", "AT", "DF", "MV", "CMD"):
        q = p + OFF[field]
        print(f"  {field:3s} +{OFF[field]:02X}  "
              f"{int.from_bytes(IN.read_bytes()[q:q+2], 'big'):3d}"
              f" -> {int.from_bytes(rom[q:q+2], 'big'):3d}")

    rom[NOTE_AT:NOTE_AT + len(NOTE)] = NOTE
    print(f"\n헤더 표식 {NOTE_AT:04X}: {NOTE.decode()}")
    # 바이트를 고쳤으니 체크섬은 어차피 안 맞는다. 재계산하지 않고 **우회**를 쓴다
    # (0x18E = 0 이면 0x4630 이 비교를 건너뛴다). 입력이 --release 빌드여도 된다.
    rom[0x18E] = rom[0x18F] = 0
    print("체크섬 우회 0x18E = 0000 (디버그 롬은 항상 우회)")
    OUT.write_bytes(rom)
    print(f"\n-> {OUT}  ({len(rom)} bytes)")


if __name__ == "__main__":
    main()
