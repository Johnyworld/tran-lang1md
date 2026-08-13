#!/usr/bin/env python3
"""배포 페이지용 웹폰트 생성 — 번역에 쓴 폰트를 그대로 쓴다.

`index.html` 의 **실제 표시 문자만** 골라 부분집합을 만들고 woff2 로 굽는다.
전체 한글 11172자를 다 실으면 5~7MB 라 페이지에 쓸 수 없다.

라이선스 (폰트 name 테이블에서 확인한 사실)
-------------------------------------------
```
Galmuri11   OFL-1.1   Copyright (c) 2019-2025 Lee Minseo (quiple@quiple.dev)
            -> quiple/galmuri 의 ofl.md 저작권 줄에 "Reserved Font Name" 조항이 없다.
               그래서 부분집합을 만들어도 이름을 바꿀 필요가 없다. 라이선스 사본을
               assets/OFL.txt 로 함께 배포한다.
DungGeunMo  Public Domain   Kil Hyung-jin / Kim Jung-tae
```

실행: fonttools 가 필요하다.
```
python3 -m venv .venv && .venv/bin/pip install fonttools brotli
.venv/bin/python tools/webfont.py
```
"""
import html
import re
import subprocess
import sys
from pathlib import Path

PAGE = Path("index.html")
ASSETS = Path("assets")
FONTS = {                                  # 출력 이름 -> (원본 ttf, 폰트 패밀리)
    "galmuri11": (Path("font/galmuri11/font-58c1637749eb0742.ttf"), "Galmuri11"),
    "dunggeunmo": (Path("font/dunggeunmo/font-6883cc1477b4cbfa.ttf"), "DungGeunMo"),
}
# 페이지에 없어도 넣어 두는 것 — 나중에 문구를 조금 고쳐도 다시 굽지 않아도 되게.
EXTRA = (" !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ"
         "[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
         "◆▶▼◀▲·…—「」『』【】※→←↑↓")


def page_chars(page: str) -> set[str]:
    """마크업을 걷어내고 화면에 보이는 문자만 남긴다."""
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S | re.I)
    body = re.sub(r"<[^>]+>", " ", body)          # 태그 제거
    body = html.unescape(body)
    return {c for c in body if not c.isspace()}


def coverage_gap(woff2: Path, chars: set[str]) -> set[str]:
    """구운 폰트가 페이지 문자를 다 담았는지 — 빠지면 화면에 두부(□)가 뜬다."""
    from fontTools.ttLib import TTFont
    font = TTFont(str(woff2))
    have = {chr(c) for t in font["cmap"].tables for c in t.cmap}
    return {c for c in chars if c not in have}


def main() -> None:
    try:
        from fontTools import subset          # noqa: F401
    except ImportError:
        raise SystemExit("fonttools 가 없다 — 파일 첫머리의 설치 방법 참고")
    chars = page_chars(PAGE.read_text()) | set(EXTRA)
    ASSETS.mkdir(exist_ok=True)
    text = "".join(sorted(chars))
    gaps: dict[str, set[str]] = {}
    print(f"문자 {len(chars)}자 (페이지 표시 문자 + 여유분)")
    for name, (src, family) in FONTS.items():
        if not src.exists():
            raise SystemExit(f"{src} 가 없다")
        out = ASSETS / f"{name}.woff2"
        subprocess.run([sys.executable, "-m", "fontTools.subset", str(src),
                        f"--text={text}", "--flavor=woff2",
                        "--layout-features=", "--no-hinting",
                        "--desubroutinize", "--name-IDs=*",
                        f"--output-file={out}"], check=True)
        print(f"  {family:11s} {src.stat().st_size / 1e6:5.1f}MB -> "
              f"{out} {out.stat().st_size / 1024:.1f}KB")
        gaps[name] = coverage_gap(out, chars)
    # CSS 폰트 스택은 **글자 단위로** 대체 폰트를 찾는다. 그래서 각 폰트가 모든 글자를
    # 가질 필요는 없고, 둘의 합집합이 페이지를 덮으면 두부(□)가 안 뜬다.
    both = set.intersection(*gaps.values())
    if both:
        raise SystemExit(f"두 폰트 어디에도 없는 글자: {''.join(sorted(both))}")
    fall = gaps["dunggeunmo"] - gaps["galmuri11"]
    print("모든 표시 문자가 덮인다 (합집합 기준)")
    if fall:
        print(f"  제목용 둥근모꼴에 없어 갈무리로 넘어가는 글자: {''.join(sorted(fall))}")


if __name__ == "__main__":
    main()
