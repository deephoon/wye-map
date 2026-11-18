"""맵 항목과 원문 조각에서 낱말 찾기. AI·네트워크 없음.

- 사용: python3 search.py "압착 편차" [--wye .wye] [--limit 8]
- 항목: 제목·별칭·정의·요약에 든 낱말 수로 줄 세움. 이웃 관계도 함께 보임
- 원문: 조각 글에 든 낱말 수로 줄 세움. 조각 id로 `.wye/text/<문서>.md`에서 앞뒤를 읽음
- 낱말 맞춤은 부분 문자열(한국어 조사 붙은 꼴도 잡힘)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def terms(query: str) -> list[str]:
    """찾을 낱말. 공백으로 나누고 한 글자는 뺌(조사·잡음)."""
    return [t for t in query.casefold().split() if len(t) > 1] or [query.casefold().strip()]


def score(text: str, words: list[str]) -> int:
    """글에 든 서로 다른 낱말 수."""
    low = text.casefold()
    return sum(1 for w in words if w in low)


def main() -> int:
    """찾은 항목과 조각을 출력."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("query")
    parser.add_argument("--wye", default=".wye")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    wye = Path(args.wye)
    words = terms(args.query)

    data = json.loads((wye / "map.json").read_text(encoding="utf-8")) if (wye / "map.json").exists() else {}
    entities = data.get("entities", [])
    by_id = {e["id"]: e for e in entities}
    ranked = sorted(((score(" ".join([e.get("title", ""), *e.get("aliases", []), e.get("definition", ""), e.get("summary", "")]), words), e)
                     for e in entities), key=lambda x: -x[0])
    print("## 항목")
    for hit, e in [x for x in ranked if x[0]][: args.limit]:
        near = [f"{r['type']}→{by_id[r['toId']]['title']}" for r in data.get("relations", []) if r["fromId"] == e["id"] and r["toId"] in by_id]
        near += [f"{by_id[r['fromId']]['title']}→{r['type']}" for r in data.get("relations", []) if r["toId"] == e["id"] and r["fromId"] in by_id]
        refs = ", ".join(x.get("segmentId", "") for x in e.get("evidence", []))
        print(f"- {e['id']} {e['title']} ({e['type']}) 근거 {refs or '없음'}" + (f" | {'; '.join(near[:6])}" if near else ""))

    print("## 원문 조각")
    rows = []
    seg_file = wye / "segments.jsonl"
    for line in seg_file.read_text(encoding="utf-8").splitlines() if seg_file.exists() else []:
        row = json.loads(line)
        hit = score(row["text"], words)
        if hit:
            rows.append((hit, row))
    rows.sort(key=lambda x: -x[0])
    for hit, row in rows[: args.limit]:
        text = " ".join(row["text"].split())
        print(f"- [{row['id']}] {text[:160]}{'…' if len(text) > 160 else ''}")
    if not rows and not any(x[0] for x in ranked):
        print("찾은 것 없음 — 다른 낱말이나 동의어로 다시 찾으십시오")
    return 0


if __name__ == "__main__":
    sys.exit(main())
