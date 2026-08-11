#!/usr/bin/env python3
"""대본 주소를 싣는 68000 명령의 즉치(immediate) 를 모두 찾는다.

랑그릿사 MD 는 대사 주소를 포인터 테이블이 아니라 코드 안 즉치로 갖는다.
예: 21 FC 00 03 35 4A E8 32  =  move.l #$0003354A, $E832.w

따라서 재삽입 시 고쳐야 할 대상은 "테이블 엔트리"가 아니라 "코드 안 즉치"다.
이 목록이 곧 리로케이션 대상 전체다.
"""
import json
from collections import Counter
from pathlib import Path

ROM = Path("/Users/rotein/Downloads/Langrisser.md")

# (opcode 바이트, 즉치까지의 오프셋, 즉치 뒤 추가 바이트, 설명)
FORMS = [
    (b"\x21\xfc", 2, 2, "move.l #imm,(d16).w"),
    (b"\x23\xfc", 2, 4, "move.l #imm,(xxx).l"),
    (b"\x41\xf9", 2, 0, "lea imm.l,a0"),
    (b"\x43\xf9", 2, 0, "lea imm.l,a1"),
    (b"\x45\xf9", 2, 0, "lea imm.l,a2"),
    (b"\x20\x7c", 2, 0, "movea.l #imm,a0"),
    (b"\x22\x7c", 2, 0, "movea.l #imm,a1"),
]


def main() -> None:
    rom = ROM.read_bytes()
    blocks = [(int(a, 16), int(b)) for a, b in
              (ln.split() for ln in
               Path("work/script_blocks.txt").read_text().split("\n") if ln)]
    inblk = bytearray(len(rom))
    for o, n in blocks:
        for k in range(max(0, o - 8), min(len(rom), o + n + 8)):
            inblk[k] = 1

    msgs = json.loads(Path("work/script.json").read_text())
    starts = {int(m["addr"], 16) for m in msgs}

    refs, kinds, dests = [], Counter(), Counter()
    for op, imm_at, tail, desc in FORMS:
        pos = 0
        while (i := rom.find(op, pos)) >= 0:
            pos = i + 2
            a = i + imm_at
            if a + 4 > len(rom):
                continue
            v = int.from_bytes(rom[a:a + 4], "big")
            if v >= len(rom) or not inblk[v]:
                continue
            dst = (rom[a + 4:a + 4 + tail].hex() if tail else "")
            refs.append({"site": f"{i:06X}", "imm_at": f"{a:06X}",
                         "target": f"{v:06X}", "form": desc, "dest": dst,
                         "exact_msg": v in starts})
            kinds[desc] += 1
            if dst:
                dests[dst] += 1

    refs.sort(key=lambda r: r["site"])
    Path("work/refs.json").write_text(json.dumps(refs, ensure_ascii=False, indent=1))

    exact = sum(1 for r in refs if r["exact_msg"])
    print(f"대본을 가리키는 코드 즉치 {len(refs)}개 (메시지 시작 정확 일치 {exact}개)")
    print("\n명령 형태별:")
    for k, n in kinds.most_common():
        print(f"  {k:24} {n:4d}")
    print("\n목적지(move.l 계열의 대상 주소) 상위:")
    for d, n in dests.most_common(8):
        print(f"  ${d.upper():8} {n:4d}")
    print(f"\n서로 다른 타겟 주소: {len({r['target'] for r in refs})}개")
    print("-> work/refs.json")


if __name__ == "__main__":
    main()
