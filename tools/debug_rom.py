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

알아낸 필드 (상태창이 그리는 자리에서 역추적)
```
+02  HP        전투 병력 수 — 10 이 최대로 보이므로 건드리지 않는다
+04  MP
+06  AT
+08  DF
+0A  MV
+70  지휘범위
+7A  수정 A+
+7C  수정 D+
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

BOOST = {"MP": 99, "AT": 99, "DF": 99, "MV": 10, "CMD": 8}
WEAKEN = {"AT": 1, "DF": 1}

IN, OUT = Path("work/korom_all.md"), Path("work/korom_debug.md")


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
    print(f"아군 클래스 {ALLY.start}..{ALLY.stop - 1}: "
          + " ".join(f"{k}={v}" for k, v in BOOST.items()))
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

    # 체크섬은 이미 우회돼 있다(0x18E = 0000). 배포판에서만 정상값을 넣는다.
    assert rom[0x18E:0x190] == b"\x00\x00", "체크섬 우회가 풀렸다 — 부팅이 죽는다"
    OUT.write_bytes(rom)
    print(f"\n-> {OUT}  ({len(rom)} bytes)")


if __name__ == "__main__":
    main()
