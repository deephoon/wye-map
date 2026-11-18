"""골라 읽기 색인. 큰 자료를 다 읽지 않고 어디부터 읽을지 정하는 데 씀. AI를 쓰지 않음.

- 문서마다: 파일 이름·글자 수·조각 수·절 이름(앞쪽 몇 개)
- 신호 조각: 프로필 신호어(문제·목표·KPI·미정·결정·범위, problem·goal·TBD·decision 등)가 두 가지 이상 든 조각(문서당 상한)
- 짧은 문서(1.5만 자 이하): "전부 읽기"
- 큰 표 문서(xlsx·csv): 시트 이름과 머리 행만(태그 목록처럼 행을 다 읽을 필요가 거의 없음)
- 결과: <wye>/outline.md + 출력 끝에 "신호 조각만 읽으면 N자(전체의 M%)"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from profiles import load as load_profile  # noqa: E402

# 문서당 신호 조각 상한. 넘치면 신호어가 많은 순
PER_DOC = 12
TABLE = {".xlsx", ".xls", ".csv"}
# 이보다 짧은 문서는 통째로 읽는 편이 빠름(요구사항 정의서·리스크 대장·회의록 한 편 크기)
READ_ALL = 15_000


def signals_in(text: str, signals: list[str]) -> list[str]:
    """조각에 든 신호어(중복 없이, 대소문자 무시)."""
    low = text.lower()
    return [w for w in signals if w.lower() in low]


def first_line(text: str, width: int = 70) -> str:
    """조각 첫 의미 있는 줄(표 기호·공백 정리)."""
    for line in text.splitlines():
        line = re.sub(r"[|#*>\-]+", " ", line).strip()
        if len(line) > 3:
            return line[:width]
    return ""


def main() -> int:
    """outline.md를 쓰고 요약을 출력."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wye", nargs="?", default=".wye")
    args = parser.parse_args()
    wye = Path(args.wye).resolve()
    signals = load_profile(wye)["signals"]
    files = json.loads((wye / "sources.json").read_text(encoding="utf-8"))["files"]
    rows: dict[str, list[dict]] = {}
    for line in (wye / "segments.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        rows.setdefault(row["doc"], []).append(row)
    total = picked = 0
    out = ["# 골라 읽기 색인", "", "신호 조각부터 읽고, 모자라면 `search.py`로 찾아 읽는다. 표 문서는 머리 행만 보고 필요한 열을 찾는다.", ""]
    for rel, f in sorted(files.items(), key=lambda x: x[1]["doc"]):
        if f.get("status") != "ok":
            continue
        doc, segs = f["doc"], rows.get(f["doc"], [])
        chars = sum(len(s["text"]) for s in segs)
        total += chars
        sections = list(dict.fromkeys(s["section"] for s in segs if s.get("section")))
        out.append(f"## {doc} · {Path(rel).name} — {chars:,}자 · 조각 {len(segs)}")
        if chars <= READ_ALL:
            picked += chars
            out += ["- 전부 읽기(짧음)", ""]
            continue
        if Path(rel).suffix.lower() in TABLE:
            # 표: 시트 이름(## 머리)과 첫 표의 머리 행만
            heads = [(m.group(1), s["id"]) for s in segs for m in re.finditer(r"^## (.+)$", s["text"], re.M)]
            out.append("- 표 문서. 시트: " + (", ".join(f"{h} [{sid}]" for h, sid in heads[:12]) or "없음"))
            header = next((l for s in segs for l in s["text"].splitlines() if l.startswith("|") and "---" not in l), "")
            if header:
                out.append(f"- 머리 행: {header[:200]}")
            out.append("")
            continue
        if sections:
            out.append("- 절: " + " / ".join(sections[:10]) + (" …" if len(sections) > 10 else ""))
        hits = sorted(((len(signals_in(s["text"], signals)), s) for s in segs), key=lambda x: -x[0])
        hits = [s for n, s in hits if n >= 2][:PER_DOC]
        for s in sorted(hits, key=lambda s: s["id"]):
            picked += len(s["text"])
            out.append(f"- [{s['id']}] {first_line(s['text'])} ({', '.join(signals_in(s['text'], signals)[:4])})")
        out.append("")
    (wye / "outline.md").write_text("\n".join(out), encoding="utf-8")
    share = picked / total * 100 if total else 0
    print(f"색인 {wye / 'outline.md'} · 문서 {sum(1 for f in files.values() if f.get('status') == 'ok')} · "
          f"이 색인대로 읽으면 {picked:,}자(전체 {total:,}자의 {share:.0f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
