#!/usr/bin/env python3
"""번역문이 화면에 들어가는지 검사하고 미리보기를 그린다.

화면 제약 (프롤로그 창 실측)
---------------------------
  한 줄 34칸, 본문 5줄 = 170칸
  한글 2칸 / 공백·숫자·영문·구두점 1칸

한글이 2칸인 이유: 게임 본문 폰트가 8x16(세로로 붙은 두 타일)이고 렌더러가
칸당 8px 씩 전진한다. 한글 16x16 은 세로로는 그대로 맞지만 가로로 두 칸이
필요하다. 렌더러의 `addq.w #$1, $E81C` 를 `#$2` 로 바꿔 대응한다.

usage:
  python3 tools/fit.py                 translation/ko.tsv 전체 검사
  python3 tools/fit.py "번역문"         한 줄만 계산
"""
import sys
from pathlib import Path

LINE_CELLS = 34
BODY_LINES = 5
KO_TSV = Path("translation/ko.tsv")


def cost(ch: str) -> int:
    """글자 하나가 먹는 칸 수."""
    if "가" <= ch <= "힣" or "ㄱ" <= ch <= "ㅣ":
        return 2
    return 1                      # 공백·ASCII·게임 폰트의 、。「」・ー


def cells(text: str) -> int:
    return sum(cost(c) for c in text)


def preview(text: str, limit: int = LINE_CELLS) -> list[str]:
    """34칸 격자에 찍어 화면 모습을 보여준다. 넘치는 줄은 표시한다."""
    out = []
    for i, line in enumerate(text.split("\n")):
        n = cells(line)
        bar = "!" * (n - limit) if n > limit else ""
        out.append(f"  {i + 1} |{line}{bar}  [{n:2d}/{limit}]")
    return out


def check(text: str) -> list[str]:
    """제약 위반 목록. 비어 있으면 통과."""
    errs = []
    lines = text.split("\n")
    if len(lines) > BODY_LINES:
        errs.append(f"줄 수 {len(lines)} > {BODY_LINES}")
    for i, line in enumerate(lines):
        if (n := cells(line)) > LINE_CELLS:
            errs.append(f"{i + 1}행 {n}칸 (초과 {n - LINE_CELLS})")
    return errs


def main() -> None:
    if len(sys.argv) > 1:
        t = sys.argv[1].replace("\\n", "\n")
        print("\n".join(preview(t)))
        print(f"\n합계 {cells(t)}칸 / {BODY_LINES * LINE_CELLS}")
        for e in check(t):
            print(f"  ✗ {e}")
        return

    rows = [ln.split("\t") for ln in KO_TSV.read_text().rstrip("\n").split("\n")]
    head, body = rows[0], rows[1:]
    col = {name: i for i, name in enumerate(head)}
    bad = 0
    for r in body:
        kr = r[col["kr"]].replace("\\n", "\n")
        if not kr:
            continue
        errs = check(kr)
        mark = "✗" if errs else "✓"
        print(f"{mark} {r[col['id']]}  {cells(kr):3d}칸")
        print("\n".join(preview(kr)))
        for e in errs:
            print(f"    ✗ {e}")
        bad += bool(errs)
    print(f"\n검사 완료 — 위반 {bad}건")


if __name__ == "__main__":
    main()
