"""맵(.wye/map.json)으로 하는 결정적 분석. AI를 쓰지 않음.

- 문제 고리: 문제마다 현상·지표·현재 판단·판단에 쓰는 데이터·요구사항·개선에 필요한 데이터·목표 자리를
  온톨로지 problemChain대로 한 칸씩 걸어 채우고 빈 필수 자리를 표시(Wye problem_chain.assemble_chain 포팅)
- 영향 범위(--impact <항목 id 또는 이름>): 그 항목에서 관계를 따라 닿는 항목을 깊이별로
- 구조 진단: 고립(관계 0)·한 줄로만 매달림(관계 1)·연결이 몰린 중심(상위 5)·빈 자리 수(check.json)
- 결과: <wye>/analysis.json + 출력 요약. 스킬은 이 숫자 위에 문제별 분석 한 장을 씀
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
ONTOLOGY = HERE.parent / "data" / "ontology.json"
ANCHOR = "anchor"
# 영향 범위 기본 깊이. 더 깊으면 맵 전체가 "영향"이 되어 뜻이 없어짐
IMPACT_DEPTH = 2


def adjacency(relations: list[dict]) -> tuple[dict, dict]:
    """(항목 id, 관계 종류) → 상대 id 목록. 나가는 쪽·들어오는 쪽."""
    outgoing: dict[tuple[str, str], list[str]] = {}
    incoming: dict[tuple[str, str], list[str]] = {}
    for r in relations:
        outgoing.setdefault((r["fromId"], r["type"]), []).append(r["toId"])
        incoming.setdefault((r["toId"], r["type"]), []).append(r["fromId"])
    return outgoing, incoming


def assemble_chain(entities: dict[str, dict], relations: list[dict], chain: dict, problem_id: str) -> dict | None:
    """문제 하나의 고리. 문제가 아니면 None. 슬롯마다 정의된 길로 앞 슬롯에서 한 칸만 걸어 순환에도 끝남."""
    problem = entities.get(problem_id)
    if problem is None or problem.get("type") != chain["anchor"]:
        return None
    outgoing, incoming = adjacency(relations)
    found: dict[str, list[str]] = {ANCHOR: [problem_id]}
    slots = []
    for slot in chain["slots"]:
        ids: list[str] = []
        for via in slot["via"]:
            table = outgoing if via["direction"] == "outgoing" else incoming
            for start in found.get(via["from_slot"], ()):
                for other in table.get((start, via["relation"]), ()):
                    node = entities.get(other)
                    if node is None or other == problem_id or other in ids or (via["types"] and node.get("type") not in via["types"]):
                        continue
                    ids.append(other)
        found[slot["key"]] = ids
        slots.append({"key": slot["key"], "ko": slot["ko"], "required": slot["required"],
                      "nodes": [{"id": i, "title": entities[i].get("title", i), "type": entities[i].get("type", "")} for i in ids],
                      "empty": not ids})
    missing = [s["ko"] for s in slots if s["required"] and s["empty"]]
    return {"problem": {"id": problem_id, "title": problem.get("title", problem_id)}, "slots": slots,
            "missing": missing, "complete": not missing}


def impact(entities: dict[str, dict], relations: list[dict], start: str, depth: int) -> list[dict]:
    """start에서 방향 없이 depth 단계까지 닿는 항목. 각 항목에 처음 닿은 깊이·경로의 관계."""
    near: dict[str, list[tuple[str, str]]] = {}
    for r in relations:
        near.setdefault(r["fromId"], []).append((r["toId"], f"{r['type']}→"))
        near.setdefault(r["toId"], []).append((r["fromId"], f"←{r['type']}"))
    seen = {start: 0}
    queue = deque([start])
    out = []
    while queue:
        current = queue.popleft()
        if seen[current] >= depth:
            continue
        for other, via in near.get(current, ()):
            if other in seen or other not in entities:
                continue
            seen[other] = seen[current] + 1
            out.append({"id": other, "title": entities[other].get("title", other), "type": entities[other].get("type", ""),
                        "depth": seen[other], "from": entities[current].get("title", current), "via": via})
            queue.append(other)
    return out


def diagnose(entities: dict[str, dict], relations: list[dict]) -> dict:
    """고립·한 줄 매달림·중심 항목."""
    degree = {i: 0 for i in entities}
    for r in relations:
        for end in (r["fromId"], r["toId"]):
            if end in degree:
                degree[end] += 1
    title = lambda i: entities[i].get("title", i)  # noqa: E731
    hubs = sorted((i for i in degree if degree[i] > 0), key=lambda i: -degree[i])[:5]
    return {"isolated": [title(i) for i, d in degree.items() if d == 0],
            "single": [title(i) for i, d in degree.items() if d == 1],
            "hubs": [{"title": title(i), "degree": degree[i]} for i in hubs]}


def find(entities: dict[str, dict], key: str) -> str | None:
    """id 또는 제목(부분 일치 하나)으로 항목 찾기."""
    if key in entities:
        return key
    exact = [i for i, e in entities.items() if e.get("title", "") == key]
    if len(exact) == 1:
        return exact[0]
    hits = [i for i, e in entities.items() if key in e.get("title", "")]
    return hits[0] if len(hits) == 1 else None


def main() -> int:
    """분석 결과를 analysis.json에 쓰고 요약을 출력."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wye", nargs="?", default=".wye")
    parser.add_argument("--impact", default=None, help="영향 범위를 볼 항목 id 또는 이름")
    parser.add_argument("--depth", type=int, default=IMPACT_DEPTH)
    args = parser.parse_args()
    wye = Path(args.wye).resolve()
    data = json.loads((wye / "map.json").read_text(encoding="utf-8"))
    onto = json.loads(ONTOLOGY.read_text(encoding="utf-8"))
    entities = {e["id"]: e for e in data.get("entities", [])}
    relations = [r for r in data.get("relations", []) if r.get("fromId") in entities and r.get("toId") in entities]
    chains = [c for c in (assemble_chain(entities, relations, onto["problem_chain"], i) for i in entities) if c]
    result = {"chains": chains, "diagnosis": diagnose(entities, relations)}
    check_path = wye / "check.json"
    if check_path.exists():
        checked = json.loads(check_path.read_text(encoding="utf-8"))
        result["diagnosis"]["gaps"] = len(checked.get("gaps", []))
        result["diagnosis"]["held"] = len(checked.get("held", {}))
    if args.impact:
        start = find(entities, args.impact)
        if start is None:
            print(f"항목을 하나로 찾지 못함: {args.impact} — id나 더 긴 이름으로")
            return 1
        result["impact"] = {"start": entities[start].get("title"), "items": impact(entities, relations, start, args.depth)}
    (wye / "analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    for chain in chains:
        filled = " · ".join(f"{s['ko']} {len(s['nodes'])}" for s in chain["slots"])
        state = "완성" if chain["complete"] else "빈 자리: " + ", ".join(chain["missing"])
        print(f"문제 [{chain['problem']['id']}] {chain['problem']['title']} — {state} | {filled}")
    if not chains:
        print("맵에 문제(Problem) 항목이 없음 — 문제 분석 전에 자료에서 문제를 찾아 맵에 넣어야 함")
    d = result["diagnosis"]
    print(f"구조: 고립 {len(d['isolated'])} · 한 줄 매달림 {len(d['single'])} · 중심 "
          + ", ".join(f"{h['title']}({h['degree']})" for h in d["hubs"]))
    if "impact" in result:
        print(f"영향 범위 — {result['impact']['start']}에서 {args.depth}단계: {len(result['impact']['items'])}개")
        for item in result["impact"]["items"]:
            print(f"  {item['depth']}단계 {item['title']} ({item['type']}) ← {item['from']} {item['via']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
