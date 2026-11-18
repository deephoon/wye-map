"""결과 문서 정합성 검사. 에이전트가 쓴 글(Wye/분석·Wye/회의)을 원문·맵과 대조함. AI를 쓰지 않음.

- 인용: 큰따옴표 안 글(공백 빼고 6자 이상)이 원문 조각에 글자 그대로 있는지. 바로 뒤 [D001-S0003]이 있으면 그 조각에서만,
  [D001](문서만)이면 그 문서에서만 찾음. 조각 번호가 틀렸으면 맞는 번호를 알려 줌
- 조각 표시: 문서에 적힌 [D001-S0003]이 실제로 있는 조각인지
- 판정 규칙(분석 한 장): 제목(# 문제 이름)으로 맵의 문제를 찾아,
  고리에서 판단에 쓰는 데이터가 비었거나 필요한 데이터가 미수령·설치 전·없음이면 판정 '가능'은 오류(조건부 이하로)
- 결과: <wye>/verify.json + 출력 요약. 오류가 있으면 종료 코드 1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from analyze import ONTOLOGY, assemble_chain  # noqa: E402
from check import flatten, load_segments, locate, normalize  # noqa: E402

# 검사할 결과 폴더(Wye/ 아래). 위키·확인 질문은 스크립트가 만든 것이라 뺌
FOLDERS = ("분석", "회의", "Analysis", "Meetings")
# 분석 한 장 폴더(한국어·영어 결과)
ANALYSIS = ("분석", "Analysis")
# 이보다 짧은 인용("분 단위" 등)은 어디에나 있을 수 있어 검사 뜻이 없음
MIN_QUOTE = 6
QUOTE = re.compile(r'["“]([^"”\n]{2,300})["”]\s*(\[(D\d{3}(?:-S\d{4})?)[^\]]*\])?')
TAG = re.compile(r"\b(D\d{3}-S\d{4})\b")
VERDICT = re.compile(r"\*\*(?:판정|Verdict)\*\*\s*[:：]\s*([^\n]+)", re.I)
# 영어 판정 낱말 → 화면·규칙이 쓰는 한국어 낱말(앞에서부터 먼저 맞는 것)
VERDICT_WORDS = [("지금은 불가", "지금은 불가"), ("not feasible", "지금은 불가"), ("조건부", "조건부 가능"),
                 ("conditional", "조건부 가능"), ("가능", "가능"), ("feasible", "가능")]
# 데이터가 아직 없다는 표시. 이 상태의 데이터에 기대는 문제는 '가능' 판정 금지
NOT_READY = ("미수령", "설치 전", "없음", "미확보", "미정")


def verdict_of(text: str) -> str:
    """'- **판정**: …'(영어 '- **Verdict**: …') 줄에서 판정 낱말. 없으면 빈칸. 불가·조건부를 먼저 봄."""
    m = VERDICT.search(text)
    if not m:
        return ""
    line = m.group(1).lower()
    return next((ko for word, ko in VERDICT_WORDS if word in line), m.group(1).strip()[:20])


def rule_errors(title: str, verdict: str, data: dict, chain_def: dict) -> tuple[str, list[str]]:
    """(문제 id, 판정 규칙 위반 목록). 맵에서 문제를 못 찾으면 그 자체를 오류로."""
    entities = {e["id"]: e for e in data.get("entities", [])}
    problem = next((e for e in entities.values() if e.get("type") == "Problem" and normalize(e.get("title")) == normalize(title)), None)
    if problem is None:
        return "", [f"맵에 '{title}' 문제가 없음 — 제목을 맵의 문제 이름과 같게"]
    if verdict != "가능":
        return problem["id"], []
    chain = assemble_chain(entities, data.get("relations", []), chain_def, problem["id"])
    errors = []
    slots = {s["key"]: s for s in chain["slots"]}
    judge_data = next((s for s in chain["slots"] if s["ko"] == "판단에 쓰는 데이터"), None)
    if judge_data and judge_data["empty"]:
        errors.append("판단에 쓰는 데이터 자리가 비었는데 판정 '가능' — 조건부 이하로")
    for slot in slots.values():
        for node in slot["nodes"]:
            props = entities[node["id"]].get("properties") or {}
            if node["type"] == "DataRequirement" and any(w in str(props.get("availability", "")) for w in NOT_READY):
                errors.append(f"필요 데이터 '{node['title']}'이 {props['availability']}인데 판정 '가능' — 조건부 이하로")
    return problem["id"], errors


def verify_file(path: Path, segments: dict[str, str], data: dict, chain_def: dict) -> dict:
    """문서 하나 검사 결과."""
    text = path.read_text(encoding="utf-8")
    everything = list(segments.values())
    quotes, missing = 0, []
    for m in QUOTE.finditer(text):
        quote, seg = m.group(1), m.group(3)
        flat = flatten(quote)
        if len(flat) < MIN_QUOTE:
            continue
        quotes += 1
        if seg and "-S" in seg:
            pool = [segments.get(seg, "")]
        elif seg:
            pool = [text for sid, text in segments.items() if sid.startswith(seg + "-")]
        else:
            pool = everything
        if not any(flat in s for s in pool):
            # 표시한 곳에는 없지만 다른 조각에 있으면 그 번호를 알려 줌(번호만 틀린 경우가 대부분)
            hint = locate(quote, seg.split("-")[0] if seg else "", segments) or locate(quote, "", segments)
            missing.append({"quote": quote[:80], "segmentId": seg or "", "foundIn": hint})
    bad_tags = sorted({t for t in TAG.findall(text) if t not in segments})
    result = {"path": str(path), "quotes": quotes, "missing": missing, "badTags": bad_tags, "rules": []}
    if path.parent.name in ANALYSIS:
        title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), path.stem)
        result["verdict"] = verdict_of(text)
        result["problemId"], result["rules"] = rule_errors(title, result["verdict"], data, chain_def)
        if not result["verdict"]:
            result["rules"].append("'- **판정**: …'(영어 '- **Verdict**: …') 줄이 없음")
    result["ok"] = not (missing or bad_tags or result["rules"])
    return result


def main() -> int:
    """Wye/분석·Wye/회의의 md를 모두 검사하고 verify.json을 씀."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wye", nargs="?", default=".wye")
    args = parser.parse_args()
    wye = Path(args.wye).resolve()
    segments = load_segments(wye)
    map_path = wye / "map.json"
    data = json.loads(map_path.read_text(encoding="utf-8")) if map_path.exists() else {"entities": [], "relations": []}
    chain_def = json.loads(ONTOLOGY.read_text(encoding="utf-8"))["problem_chain"]
    files = [p for folder in FOLDERS for p in sorted((wye.parent / "Wye" / folder).glob("*.md"))]
    results = [verify_file(p, segments, data, chain_def) for p in files]
    (wye / "verify.json").write_text(json.dumps({"files": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    problems = 0
    for r in results:
        name = Path(r["path"]).relative_to(wye.parent)
        for item in r["missing"]:
            where = f" — {item['foundIn']}에 있음, 표시만 고치면 됨" if item.get("foundIn") else ""
            print(f"오류 {name}: 인용이 {item['segmentId'] or '원문'}에 글자 그대로 없음 — \"{item['quote'][:40]}\"{where}")
        for tag in r["badTags"]:
            print(f"오류 {name}: 없는 조각 {tag}")
        for rule in r["rules"]:
            print(f"오류 {name}: {rule}")
        problems += len(r["missing"]) + len(r["badTags"]) + len(r["rules"])
    quotes = sum(r["quotes"] for r in results)
    print(f"{'통과' if not problems else '실패'} — 문서 {len(results)} · 인용 {quotes} · 오류 {problems}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
