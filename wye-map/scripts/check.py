"""map.json을 원문 조각·온톨로지·상한과 대조함. AI를 쓰지 않는 결정적 검사.

- 오류(exit 1): 고쳐야 통과. 모르는 종류, 허용되지 않은 관계, 원문에 없는 인용으로 근거가 0이 된 항목,
  제목 길이·항목 수 상한 초과, why 없는 관계, 같은 이름 중복
- 보류(맵에는 남되 표시): 목표·문제·공정·프로젝트에서 관계로 닿지 않음, 목표 수 초과, 팩 필수값 빠짐
- 인용을 {"doc", "quote"}로 쓰면 조각 번호(segmentId)를 찾아 map.json에 채움
- 결과: <wye>/check.json(통과·보류·확인 질문). render.py가 읽음
- 규칙 출처: Wye gate.run_gate · structural_gaps.find_structural_gaps · synthesis_validation._validate (commit 3973709e)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ONTOLOGY = HERE.parent / "data" / "ontology.json"
DEFAULT_CAPS = {"maxEntities": 60, "maxGoals": 6, "maxQuestions": 15, "maxTitle": 30, "maxConflicts": 10}
GOAL_DISCONNECTED = "GOAL_DISCONNECTED"
GOAL_OVERFLOW = "GOAL_OVERFLOW"
MISSING_MUST_HAVE = "MISSING_MUST_HAVE"
HOLD_KO = {GOAL_DISCONNECTED: "목표·문제·공정·프로젝트와 이어지지 않음",
           GOAL_OVERFLOW: "목표가 너무 많아 연결이 적은 목표를 보류",
           MISSING_MUST_HAVE: "꼭 필요한 값이 빠짐"}


def flatten(text: object) -> str:
    """인용 대조용. 공백·줄바꿈을 모두 지움(Wye output_cleanup._flatten)."""
    return re.sub(r"\s+", "", str(text or ""))


def normalize(text: object) -> str:
    """이름 비교용. 대소문자 접고 숫자·영문·한글만 남김(Wye gate._normalize)."""
    return re.sub(r"[^0-9a-z가-힣]+", "", str(text or "").casefold())


def load_segments(wye: Path) -> dict[str, str]:
    """조각 id → 공백 지운 원문."""
    path = wye / "segments.jsonl"
    if not path.exists():
        return {}
    rows = (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line)
    return {row["id"]: flatten(row["text"]) for row in rows}


def locate(quote: object, doc: str, segments: dict[str, str]) -> str:
    """문서(D013) 안에서 인용이 글자 그대로 든 첫 조각 id. 없으면 빈칸. doc이 비면 전체에서."""
    flat = flatten(quote)
    if not flat:
        return ""
    prefix = f"{doc}-" if doc else ""
    return next((sid for sid, text in segments.items() if sid.startswith(prefix) and flat in text), "")


def fill_segment_ids(data: dict, segments: dict[str, str]) -> int:
    """{"doc", "quote"}로 쓴 인용에 segmentId를 채움(조각 번호를 사람·에이전트가 외우지 않게). 채운 수.

    - 항목 evidence, 관계 evidence, 불일치 claims가 대상
    - 못 찾으면 그대로 둠(doc 유지) → 검사가 '원문에 없음'으로 잡고, 인용만 고치면 다음 검사에서 채워짐
    """
    filled = 0
    groups = [e.get("evidence") for e in data.get("entities", [])] + [r.get("evidence") for r in data.get("relations", [])]
    groups += [c.get("claims") for c in data.get("conflicts", [])]
    for items in groups:
        for item in items or []:
            if item.get("segmentId") or "doc" not in item:
                continue
            found = locate(item.get("quote"), str(item["doc"]), segments)
            if found:
                item.pop("doc")
                item["segmentId"] = found
                filled += 1
    return filled


def real_evidence(items: list, segments: dict[str, str]) -> tuple[list, list]:
    """원문 조각에 글자 그대로 있는 인용과 없는 인용으로 가름."""
    good, bad = [], []
    for item in items or []:
        quote = flatten(item.get("quote"))
        (good if quote and quote in segments.get(item.get("segmentId", ""), "") else bad).append(item)
    return good, bad


def gate(entities: list, relations: list, onto: dict, max_goals: int) -> dict[str, list[str]]:
    """맵 승격 판정. 보류 항목 id → 사유 목록. 규칙은 Wye run_gate와 같음."""
    ids = {e["id"] for e in entities}
    adjacency = {i: set() for i in ids}
    for r in relations:
        if r["fromId"] in ids and r["toId"] in ids:
            adjacency[r["fromId"]].add(r["toId"])
            adjacency[r["toId"]].add(r["fromId"])
    anchors = [e["id"] for e in entities if e["type"] in onto["anchor_types"]]
    reachable, frontier = set(anchors), list(anchors)
    while frontier:
        for neighbor in adjacency[frontier.pop()]:
            if neighbor not in reachable:
                reachable.add(neighbor)
                frontier.append(neighbor)
    goals = [e for e in entities if e["type"] == "Goal"]
    overflow = set()
    if len(goals) > max_goals:
        ranked = sorted(goals, key=lambda e: (-len(adjacency[e["id"]]), entities.index(e)))
        overflow = {e["id"] for e in ranked[max_goals:]}
    held: dict[str, list[str]] = {}
    for e in entities:
        reasons = [] if e["id"] in reachable else [GOAL_DISCONNECTED]
        if e["id"] in overflow:
            reasons.append(GOAL_OVERFLOW)
        reasons += [f"{MISSING_MUST_HAVE}:{f}" for f in missing_must_have(e, onto)]
        if reasons:
            held[e["id"]] = reasons
    return held


def missing_must_have(entity: dict, onto: dict) -> list[str]:
    """이름이 팩 개념과 맞고 그 개념에 승격 규칙이 있으면 빠진 필수 칸 id 목록."""
    keys = {normalize(entity["title"]), *(normalize(a) for a in entity.get("aliases", []))} - {""}
    for concept in onto["concepts"].values():
        if concept["entity_type"] != entity["type"]:
            continue
        names = {normalize(concept["ko"]), *(normalize(a) for a in concept.get("aliases", []))}
        if not keys & names:
            continue
        # 처음 맞은 개념 하나만 봄. 규칙이 없으면 빠진 것 없음
        rule = onto["promotion_rules"].get(concept["id"])
        if not rule:
            return []
        props = entity.get("properties") or {}
        return [f for f in rule["must_have"]
                if not (entity.get("evidence") if f == "evidence" else str(props.get(f, "")).strip())]
    return []


def structural_gaps(entities: list, relations: list, onto: dict) -> list[dict]:
    """지도에서 팩 규칙이 요구한 관계·속성이 빈 자리. 규칙은 Wye find_structural_gaps와 같음."""
    by_id = {e["id"]: e for e in entities}
    found = []
    for rule in onto["structural_gaps"]:
        for e in entities:
            if e["type"] != rule["entity_type"]:
                continue
            if rule["property_id"]:
                filled = bool(str((e.get("properties") or {}).get(rule["property_id"]) or "").strip())
            else:
                filled = False
                for r in relations:
                    if r["type"] != rule["relation"]:
                        continue
                    near, far = ((r["toId"], r["fromId"]) if rule["direction"] == "incoming"
                                 else (r["fromId"], r["toId"]))
                    other = by_id.get(far)
                    if near == e["id"] and (not rule["other_types"] or (other and other["type"] in rule["other_types"])):
                        filled = True
                        break
            if not filled:
                found.append({"ruleId": rule["id"], "entityId": e["id"], "entityTitle": e["title"],
                              "text": f"{e['title']} — {rule['text']}", "action": rule["action"],
                              "askWho": rule["ask_who"]})
    return found


def check(wye: Path) -> tuple[list[str], dict]:
    """검사 실행. (오류 목록, check.json 내용)."""
    onto = json.loads(ONTOLOGY.read_text(encoding="utf-8"))
    config_path = wye / "config.json"
    caps = {**DEFAULT_CAPS, **(json.loads(config_path.read_text(encoding="utf-8")).get("caps", {})
                               if config_path.exists() else {})}
    data = json.loads((wye / "map.json").read_text(encoding="utf-8"))
    segments = load_segments(wye)
    if fill_segment_ids(data, segments):
        (wye / "map.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    entities, relations = data.get("entities", []), data.get("relations", [])
    errors: list[str] = []
    warnings: list[str] = []

    # 1) 항목: 종류·제목·근거·중복
    seen: dict[tuple, str] = {}
    ids = set()
    for e in entities:
        eid = e.get("id", "?")
        if eid in ids:
            errors.append(f"{eid}: id 중복")
        ids.add(eid)
        if e.get("type") not in onto["entity_types"]:
            errors.append(f"{eid}: 모르는 종류 '{e.get('type')}' — ontology의 entity_types만 씀")
        title = str(e.get("title", "")).strip()
        if not title:
            errors.append(f"{eid}: 제목 없음")
        elif len(title) > caps["maxTitle"]:
            errors.append(f"{eid}: 제목 {len(title)}자 — {caps['maxTitle']}자 이하의 이름으로(문장 금지)")
        key = (e.get("type"), normalize(title))
        if key in seen:
            errors.append(f"{eid}: '{title}'이 {seen[key]}와 같은 종류·이름 — 하나로 합치고 다른 표기는 aliases로")
        seen[key] = eid
        good, bad = real_evidence(e.get("evidence"), segments)
        for item in bad:
            errors.append(f"{eid}: 인용이 {item.get('segmentId') or item.get('doc')} 원문에 글자 그대로 없음 — \"{str(item.get('quote'))[:40]}\"")
        if not good and not bad:
            errors.append(f"{eid}: 근거 인용 없음 — 원문 한 문장을 evidence로")
        for prop in (e.get("properties") or {}):
            allowed = {p["id"] for p in onto["entity_types"].get(e.get("type"), {}).get("properties", [])}
            if prop not in allowed:
                errors.append(f"{eid}: 속성 '{prop}'은 {e.get('type')}에 없음 — 허용: {', '.join(sorted(allowed)) or '없음'}")
    if len(entities) > caps["maxEntities"]:
        errors.append(f"항목 {len(entities)}개 — 상한 {caps['maxEntities']}. 곁가지는 지우거나 aliases·properties로 접기")

    # 2) 관계: 종류·끝점 종류·why·근거
    by_id = {e["id"]: e for e in entities}
    seen_rel = set()
    for i, r in enumerate(relations):
        label = f"관계 {r.get('fromId')} -{r.get('type')}-> {r.get('toId')}"
        rule = onto["relation_types"].get(r.get("type"))
        source, target = by_id.get(r.get("fromId")), by_id.get(r.get("toId"))
        if rule is None:
            errors.append(f"{label}: 모르는 관계 종류")
            continue
        if source is None or target is None:
            errors.append(f"{label}: 없는 항목을 가리킴")
            continue
        if source["type"] not in rule["from_types"] or target["type"] not in rule["to_types"]:
            errors.append(f"{label}: {source['type']}→{target['type']}는 허용되지 않음 "
                          f"(허용 {'/'.join(rule['from_types'])}→{'/'.join(rule['to_types'])})")
        if not str(r.get("why", "")).strip():
            errors.append(f"{label}: why 없음 — 왜 이었는지 한 문장, 못 쓰면 관계를 지움")
        if (r.get("fromId"), r.get("type"), r.get("toId")) in seen_rel:
            errors.append(f"{label}: 중복")
        seen_rel.add((r.get("fromId"), r.get("type"), r.get("toId")))
        _, bad = real_evidence(r.get("evidence"), segments)
        if bad:
            errors.append(f"{label}: 인용이 원문에 글자 그대로 없음 — 고치거나 evidence를 비움")

    # 3) 자료 간 불일치: 같은 대상에 문서마다 다른 값. 값마다 원문 인용, 서로 다른 조각 둘 이상
    conflicts = data.get("conflicts", [])
    conflict_ids = set()
    for c in conflicts:
        cid = c.get("id", "?")
        label = f"불일치 {cid}"
        if cid in conflict_ids:
            errors.append(f"{label}: id 중복")
        conflict_ids.add(cid)
        if not str(c.get("topic", "")).strip():
            errors.append(f"{label}: topic 없음 — 무엇이 어긋나는지 이름으로")
        claims = c.get("claims") or []
        if len({str(x.get("segmentId")) for x in claims}) < 2:
            errors.append(f"{label}: 서로 다른 조각의 주장이 둘 이상 필요")
        if len({normalize(x.get("value")) for x in claims}) < 2:
            errors.append(f"{label}: 값이 모두 같음 — 불일치가 아님")
        _, bad = real_evidence(claims, segments)
        for item in bad:
            errors.append(f"{label}: 인용이 {item.get('segmentId') or item.get('doc')} 원문에 글자 그대로 없음 — \"{str(item.get('quote'))[:40]}\"")
        for eid in c.get("entityIds") or []:
            if eid not in by_id:
                errors.append(f"{label}: 없는 항목 {eid}")
        if not c.get("entityIds"):
            errors.append(f"{label}: entityIds 없음 — 어긋난 값이 걸린 항목을 하나 이상")
    if len(conflicts) > caps["maxConflicts"]:
        errors.append(f"불일치 {len(conflicts)}건 — 상한 {caps['maxConflicts']}. 판단을 바꾸는 것만 남기기")
    in_conflict = {eid for c in conflicts for eid in c.get("entityIds") or []}
    for e in entities:
        if "자료 간 불일치" in str(e.get("whatIsMissing", "")) and e["id"] not in in_conflict:
            warnings.append(f"{e['id']}: whatIsMissing의 자료 간 불일치를 conflicts로 옮기면 화면·검사에 잡힘")

    # 4) 승격·공백·질문 (오류가 있어도 계산해 둠)
    valid_rel = [r for r in relations if r.get("fromId") in by_id and r.get("toId") in by_id
                 and r.get("type") in onto["relation_types"]]
    held = gate(entities, valid_rel, onto, caps["maxGoals"])
    gaps = structural_gaps(entities, valid_rel, onto)
    weight = {e["id"]: e.get("importance", 0) for e in entities}
    gaps.sort(key=lambda g: -weight.get(g["entityId"], 0))
    questions = [{"text": g["text"], "action": g["action"], "askWho": g["askWho"], "entityId": g["entityId"]}
                 for g in gaps if g["entityId"] not in held][: caps["maxQuestions"]]
    if held:
        warnings.append(f"보류 {len(held)}건: " + ", ".join(f"{k}({'·'.join(v)})" for k, v in list(held.items())[:10]))
    result = {"ok": not errors, "errors": errors, "warnings": warnings,
              "promoted": [e["id"] for e in entities if e["id"] not in held],
              "held": {k: [HOLD_KO.get(v.split(":")[0], v) + (f"({v.split(':', 1)[1]})" if ":" in v else "") for v in vs]
                       for k, vs in held.items()},
              "gaps": gaps, "questions": questions, "caps": caps,
              "conflicts": len(conflicts)}
    return errors, result


def main() -> int:
    """검사 후 check.json을 쓰고 오류를 출력."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wye", nargs="?", default=".wye")
    args = parser.parse_args()
    wye = Path(args.wye).resolve()
    errors, result = check(wye)
    (wye / "check.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    for line in errors:
        print("오류 " + line)
    for line in result["warnings"]:
        print("알림 " + line)
    print(f"{'통과' if not errors else '실패'} — 항목 {len(result['promoted']) + len(result['held'])} · "
          f"맵 {len(result['promoted'])} · 보류 {len(result['held'])} · 빈 자리 {len(result['gaps'])} · "
          f"질문 {len(result['questions'])} · 불일치 {result['conflicts']} · 오류 {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
