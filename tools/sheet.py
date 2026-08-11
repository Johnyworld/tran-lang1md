#!/usr/bin/env python3
"""`translation/dialogue.tsv` 를 이야기 순서로 다시 만든다. 기존 번역은 보존한다.

앵커를 두 곳에서 모은다:
  1. 스테이지 이벤트 표 (events.py) — 스테이지·이벤트 번호가 붙는다
  2. `work/refs.json` 의 `$E82C` 즉치 — 이벤트 표에 없는 것 (전투 중 대사 등)

같은 대사가 여러 앵커에 복사돼 있는 경우가 많다 (화자 워드 `W` 만 다르고 본문이
같은 것). 워크시트에는 **처음 것만** 싣고, 빌드 쪽에서 원문이 같은 메시지를
찾아 번역을 재사용한다(`build_all.load_dialogue` 의 원문 기억). 그래서 같은
문장을 여러 번 옮겨 적지 않는다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chain import parse_chain  # noqa: E402
from events import stage_events  # noqa: E402
from script import decode  # noqa: E402

OUT = Path("translation/dialogue.tsv")
REFS = Path("work/refs.json")
HEADER = "stage\tevent\tanchor\tidx\tw\tjp\tko\tnote"


def esc(s: str) -> str:
    return s.replace("\n", "\\n").replace("\t", " ")


def load_existing() -> tuple[dict[tuple[str, int], list[str]], dict[str, str]]:
    """(앵커, idx) -> [ko, note] 와 원문 -> ko 기억."""
    by_key: dict[tuple[str, int], list[str]] = {}
    by_jp: dict[str, str] = {}
    if not OUT.exists():
        return by_key, by_jp
    rows = OUT.read_text().rstrip("\n").split("\n")
    cols = rows[0].split("\t")
    a, i, j, k = (cols.index(c) for c in ("anchor", "idx", "jp", "ko"))
    note = cols.index("note") if "note" in cols else None
    for ln in rows[1:]:
        c = ln.split("\t")
        if len(c) <= k or not c[k]:
            continue
        by_key[(c[a], int(c[i]))] = [c[k], c[note] if note is not None and len(c) > note else ""]
        by_jp.setdefault(c[j], c[k])
    return by_key, by_jp


def main() -> None:
    rom = Path("/Users/rotein/Downloads/Langrisser.md").read_bytes()
    by_key, by_jp = load_existing()

    found: list[tuple[int, int, int]] = []          # (스테이지, 이벤트, 앵커)
    seen: set[int] = set()
    for s, events in enumerate(stage_events(rom), 1):
        for e, (_cond, _act, anchors) in enumerate(events):
            for a in anchors:
                if a not in seen:
                    seen.add(a)
                    found.append((s, e, a))
    extra = sorted({int(r["target"], 16) for r in json.loads(REFS.read_text())
                    if r["dest"] == "e82c"} - seen)
    found += [(0, 0, a) for a in extra]

    rows, sigs, kept, reused = [], {}, 0, 0
    for s, e, a in found:
        try:
            msgs = parse_chain(rom, a)
        except ValueError:
            continue
        sig = tuple(decode(m["s1"] or m["s2"]) for m in msgs)
        if sig in sigs:
            continue                                # 본문이 같은 복사본은 싣지 않는다
        sigs[sig] = a
        kept += 1
        for i, m in enumerate(msgs):
            jp = esc(decode(m["s1"] or m["s2"]))
            ko, note = by_key.get((f"{a:06X}", i), ["", ""])
            if not ko and jp in by_jp:
                ko, reused = by_jp[jp], reused + 1
            rows.append(f"{s}\t{e}\t{a:06X}\t{i}\t{m['w']:04X}\t{jp}\t{ko}\t{note}")

    OUT.write_text(HEADER + "\n" + "\n".join(rows) + "\n")
    done = sum(1 for r in rows if r.split("\t")[6])
    print(f"앵커 {len(found)}개 -> 서로 다른 대사 {kept}개 / 메시지 {len(rows)}개")
    print(f"번역 완료 {done}개 ({done * 100 // len(rows)}%)  원문 기억으로 되살린 것 {reused}개")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
