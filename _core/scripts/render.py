"""map.json + check.json → 사람이 보는 결과물. AI를 쓰지 않음.

- 결과는 작업 폴더의 보이는 폴더 Wye/에 씀(재료 .wye/와 나눔)
- Wye/맵.html: 오프라인 한 장. 문제 고리 보드·연결(계층 레인)·목록·정합성 보기와 항목 상세(근거 원문)
- 정합성: check.json(맵 검사)·map.json conflicts(자료 간 불일치)·verify(결과 문서 인용·판정 규칙)를 함께 보임
- Wye/위키/: 개요 1쪽 + 계층 7쪽. 항목마다 절 하나
- Wye/요약.md: 보낼 수 있는 한 장 — 결론·막힌 곳(분석 한 장 판정·조건)·자료 간 불일치·담당별 확인. 새 문장 없이 맵·분석에서 조립
- Wye/질문지.xlsx: 확인 질문(맵 빈 자리)·불일치 물을 것·분석 한 장 다음 확인을 물을 곳별로. 답·담당·기한 칸
- check.py를 먼저 돌려야 함(보류·질문을 check.json에서 읽음)
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from analyze import assemble_chain  # noqa: E402
from check import load_segments  # noqa: E402
from profiles import load as load_profile  # noqa: E402
from verify import FOLDERS, verify_file  # noqa: E402
import xlsx  # noqa: E402

ONTOLOGY = HERE.parent / "data" / "ontology.json"
TEMPLATE = HERE.parent / "viewer" / "map.html"


def load(wye: Path) -> dict:
    """화면·위키에 쓸 자료를 한 묶음으로 모음."""
    onto = json.loads(ONTOLOGY.read_text(encoding="utf-8"))
    data = json.loads((wye / "map.json").read_text(encoding="utf-8"))
    checked = json.loads((wye / "check.json").read_text(encoding="utf-8"))
    sources = json.loads((wye / "sources.json").read_text(encoding="utf-8"))["files"]
    doc_path = {f["doc"]: rel for rel, f in sources.items()}
    pages = {}
    seg_file = wye / "segments.jsonl"
    for line in seg_file.read_text(encoding="utf-8").splitlines() if seg_file.exists() else []:
        row = json.loads(line)
        pages[row["id"]] = row.get("page")
    held = checked.get("held", {})
    asked: dict[str, int] = {}
    for q in checked.get("questions", []):
        asked[q["entityId"]] = asked.get(q["entityId"], 0) + 1
    layers = [{"id": l["id"], "ko": l["ko"], "definition": l["definition"], "color": l["color"],
               "colorLight": l["color_light"]} for l in onto["layers"]]
    entities = []
    for e in data.get("entities", []):
        type_def = onto["entity_types"].get(e["type"], {})
        evidence = [{**item, "file": doc_path.get(item.get("segmentId", "").split("-")[0], ""),
                     "page": pages.get(item.get("segmentId"))} for item in e.get("evidence", [])]
        entities.append({**e, "evidence": evidence, "typeKo": type_def.get("ko", e["type"]),
                         "layer": type_def.get("layer", "SCOPE"), "held": held.get(e["id"], []),
                         "questions": asked.get(e["id"], 0)})
    relations = []
    for r in data.get("relations", []):
        rule = onto["relation_types"].get(r["type"], {})
        evidence = [{**item, "file": doc_path.get(item.get("segmentId", "").split("-")[0], ""),
                     "page": pages.get(item.get("segmentId"))} for item in r.get("evidence", [])]
        relations.append({**r, "evidence": evidence, "ko": rule.get("ko", r["type"]),
                          "inverseKo": rule.get("inverse_ko", r["type"]), "verbKo": rule.get("verb_ko", "")})
    def located(items: list) -> list:
        """인용에 파일 이름·쪽 붙이기."""
        return [{**item, "file": doc_path.get(str(item.get("segmentId", "")).split("-")[0], ""),
                 "page": pages.get(item.get("segmentId"))} for item in items or []]

    profile = load_profile(wye)
    by_id = {e["id"]: e for e in data.get("entities", [])}
    chains = [c for c in (assemble_chain(by_id, data.get("relations", []), onto["problem_chain"], i) for i in by_id) if c]
    conflicts = [{**c, "claims": located(c.get("claims"))} for c in data.get("conflicts", [])]
    # 결과 문서 검사는 화면을 만들 때마다 새로 함(verify.json이 낡았을 수 있음)
    segments = load_segments(wye)
    out = wye.parent / "Wye"
    documents = []
    for folder in FOLDERS:
        for path in sorted((out / folder).glob("*.md")):
            result = verify_file(path, segments, data, onto["problem_chain"])
            documents.append({**result, "path": f"{folder}/{path.name}", "name": path.stem})
    return {"brief": data.get("brief", ""), "title": data.get("title") or wye.parent.name,
            "verdictTitle": profile["analysis"]["verdictTitle"],
            "language": profile.get("language") if profile.get("language") in TEXT else "ko",
            "chains": chains, "conflicts": conflicts, "documents": documents,
            "checkErrors": checked.get("errors", []), "warnings": checked.get("warnings", []),
            "layers": layers, "entities": entities, "relations": relations,
            "questions": checked.get("questions", []), "ok": checked.get("ok", False),
            "errors": len(checked.get("errors", []))}


def cite(item: dict) -> str:
    """근거 한 줄: 인용 — 파일 p.N."""
    where = item.get("file", "") + (f" p.{item['page']}" if item.get("page") else "")
    return f"> {item.get('quote', '').strip()}  \n> — `{where or item.get('segmentId', '')}`"


def wiki(bundle: dict, out: Path) -> int:
    """위키 Markdown 쓰기. 쓴 쪽 수를 돌려줌."""
    out.mkdir(exist_ok=True)
    for old in out.glob("*.md"):
        old.unlink()
    by_id = {e["id"]: e for e in bundle["entities"]}
    index = [f"# {bundle['title']}", "", bundle["brief"], "",
             f"항목 {len(bundle['entities'])} · 관계 {len(bundle['relations'])} · "
             f"보류 {sum(1 for e in bundle['entities'] if e['held'])} · 확인 질문 {len(bundle['questions'])}", "",
             "## 계층", ""]
    written = 1
    for no, layer in enumerate(bundle["layers"], start=1):
        members = [e for e in bundle["entities"] if e["layer"] == layer["id"]]
        name = f"{no}-{layer['id'].lower()}.md"
        if not members:
            index.append(f"- {layer['ko']} — 아직 없음 · {layer['definition']}")
            continue
        index.append(f"- [{layer['ko']}]({name}) — {len(members)}개 · {layer['definition']}")
        lines = [f"# {layer['ko']}", "", layer["definition"], ""]
        for e in sorted(members, key=lambda x: -x.get("importance", 0)):
            lines += [f"## {e['title']}", "", f"*{e['typeKo']}*" + (" · **보류: " + ", ".join(e["held"]) + "**" if e["held"] else ""), ""]
            for key, label in (("definition", "무엇"), ("summary", "이 프로젝트에서"), ("whyItMatters", "왜 중요한가"),
                               ("whatWeKnow", "아는 것"), ("whatIsMissing", "모르는 것"), ("nextAction", "다음 행동")):
                if e.get(key):
                    lines.append(f"- **{label}**: {e[key]}")
            for key, value in (e.get("properties") or {}).items():
                lines.append(f"- `{key}`: {value}")
            links = [f"- {r['ko']} → {by_id[r['toId']]['title']}" for r in bundle["relations"] if r["fromId"] == e["id"] and r["toId"] in by_id]
            links += [f"- {r['inverseKo']} ← {by_id[r['fromId']]['title']}" for r in bundle["relations"] if r["toId"] == e["id"] and r["fromId"] in by_id]
            if links:
                lines += ["", "연결", *links]
            if e["evidence"]:
                lines += ["", "근거", *[cite(item) for item in e["evidence"]]]
            lines.append("")
        (out / name).write_text("\n".join(lines), encoding="utf-8")
        written += 1
    index += ["", "요약과 담당별 확인은 [../요약.md](<../요약.md>), 질문지는 `../질문지.xlsx`."]
    (out / "index.md").write_text("\n".join(index), encoding="utf-8")
    return written


# 결과 언어별 낱말. 분석 한 장 표시어(조건·다음 확인)는 두 언어 다 읽음
TEXT = {
    "ko": {"summary": "요약.md", "sheet": "질문지.xlsx", "title": "진단 요약", "blocked": "막힌 곳", "conflicts": "자료 간 불일치",
           "byOwner": "담당별 확인", "none": "기록된 불일치가 없습니다.", "more": "자세히", "noVerdict": "판정 없음", "gaps": "빈 자리",
           "tableHead": "| 무엇 | 문서마다 다른 값 | 물을 것 |", "sheetNote": "질문지 엑셀: `{sheet}` (답·담당·기한 칸을 채워 자료 폴더에 넣으면 다음 분석에서 근거로 읽힘)",
           "internalNote": "맵을 다듬을 내부 점검 {n}개는 질문지 두 번째 시트에 있습니다.", "srcGap": "맵 빈 자리", "srcConflict": "자료 간 불일치",
           "srcAnalysis": "분석", "tbd": "미정", "sheetAsk": "질문지", "sheetInternal": "내부 점검",
           "header": ["번호", "물을 곳", "질문", "출처", "관련 항목", "답(작성해 주십시오)", "담당", "기한", "wye-id"]},
    "en": {"summary": "Summary.md", "sheet": "Questions.xlsx", "title": "Diagnosis summary", "blocked": "Where it is blocked", "conflicts": "Conflicts between sources",
           "byOwner": "Checks by owner", "none": "No conflicts recorded.", "more": "Details", "noVerdict": "no verdict", "gaps": "Empty slots",
           "tableHead": "| What | Values by document | Ask |", "sheetNote": "Question sheet: `{sheet}` (fill answer, owner and due date and put it in the source folder — the next run reads it as evidence)",
           "internalNote": "{n} internal map checks are on the second sheet.", "srcGap": "map gap", "srcConflict": "conflict",
           "srcAnalysis": "analysis", "tbd": "TBD", "sheetAsk": "Questions", "sheetInternal": "Internal checks",
           "header": ["No", "Ask", "Question", "Source", "Related item", "Answer (please fill)", "Owner", "Due", "wye-id"]},
}
VERDICT_EN = {"가능": "Feasible", "조건부 가능": "Conditionally feasible", "지금은 불가": "Not feasible now"}
LABELS = {"다음 확인": ("다음 확인", "Next checks", "Next check"), "조건": ("조건", "Conditions", "Condition")}


def section_lines(text: str, label: str) -> list[str]:
    """분석 한 장에서 '- **<label>**:' 줄과 그 아래 들여쓴 줄들(다음 '- **'까지). 영어 표시어도 읽음."""
    lines, on = [], False
    names = LABELS.get(label, (label,))
    for line in text.splitlines():
        if any(line.startswith(f"- **{name}**") for name in names):
            on = True
            rest = line.split(":", 1)[1].strip() if ":" in line else ""
            if rest:
                lines.append(rest)
            continue
        if on and (line.startswith("- **") or line.startswith("#")):
            break
        if on and line.strip():
            lines.append(line.strip().lstrip("-").strip())
    return lines


# 맵 구조 빈 자리 중 컨설턴트가 맵을 고쳐 닫을 것(고객에게 묻지 않음)
INTERNAL = "컨설턴트"


def who_of(text: str) -> tuple[str, str]:
    """'누구: 질문' 또는 '누구는/은 …' → (물을 곳, 질문). 못 가르면 ('미정', 원문)."""
    if ":" in text and len(text.split(":", 1)[0]) <= 30:
        head, rest = text.split(":", 1)
        return head.strip(), rest.strip()
    m = re.match(r"^(.{2,25}?)(?:에게는|에게|는|은) (.+)$", text)
    if m:
        return m.group(1).strip(), text
    # 영어: "Client IT: …"는 위에서, "Client IT should …"·"Client IT to …"는 여기서
    m = re.match(r"^([A-Z][\w &/.-]{1,30}?) (?:should|to|must|will|needs to) ", text)
    return (m.group(1).strip(), text) if m else ("미정", text)


def question_rows(bundle: dict, out: Path) -> list[dict]:
    """질문지 행: 맵 빈 자리 질문 + 불일치 물을 것 + 분석 한 장 다음 확인. 물을 곳 순으로."""
    t = TEXT[bundle["language"]]
    by_id = {e["id"]: e for e in bundle["entities"]}
    rows = [{"who": q["askWho"] or "미정", "question": q["text"], "source": t["srcGap"], "about": by_id.get(q["entityId"], {}).get("title", ""),
             "id": q["entityId"]} for q in bundle["questions"]]
    for c in bundle["conflicts"]:
        if c.get("ask"):
            who, question = who_of(c["ask"])
            rows.append({"who": who, "question": question, "source": f"{t['srcConflict']} · {c.get('topic', '')}",
                         "about": ", ".join(by_id[i]["title"] for i in c.get("entityIds", []) if i in by_id), "id": c.get("id", "")})
    for d in bundle["documents"]:
        if not d.get("problemId"):
            continue
        text = (out / d["path"]).read_text(encoding="utf-8")
        for line in section_lines(text, "다음 확인"):
            who, question = who_of(line)
            rows.append({"who": who, "question": question, "source": f"{t['srcAnalysis']} · {d['name']}", "about": d["name"], "id": d["problemId"]})
    for r in rows:
        if r["who"] == "미정":
            r["who"] = t["tbd"]
    return sorted(rows, key=lambda r: (r["who"] == t["tbd"], r["who"]))


def summary(bundle: dict, out: Path, rows: list[dict]) -> None:
    """요약(요약.md / Summary.md): 보낼 수 있는 한 장. 문장은 맵·분석·불일치에서 가져옴."""
    t = TEXT[bundle["language"]]
    lines = [f"# {bundle['title']} — {t['title']}", "", bundle["brief"], ""]
    docs = [d for d in bundle["documents"] if d.get("problemId")]
    lines += [f"## {t['blocked']}", ""]
    if docs:
        for d in docs:
            text = (out / d["path"]).read_text(encoding="utf-8")
            head = next((l.strip() for l in text.splitlines() if l.startswith("**판정") or l.lower().startswith("**verdict")), "")
            verdict = d.get("verdict") or t["noVerdict"]
            lines.append(f"### {d['name']} — {VERDICT_EN.get(verdict, verdict) if bundle['language'] == 'en' else verdict}")
            if head:
                lines.append(head)
            for cond in section_lines(text, "조건"):
                lines.append(f"- {cond}")
            lines += [f"- {t['more']}: [{d['path']}](<{d['path']}>)", ""]
    else:
        for c in sorted(bundle["chains"], key=lambda c: -len(c["missing"]))[:3]:
            lines.append(f"- **{c['problem']['title']}** — {t['gaps']}: {', '.join(c['missing']) or '-'}")
        lines.append("")
    lines += [f"## {t['conflicts']}", ""]
    if bundle["conflicts"]:
        lines += [t["tableHead"], "|---|---|---|"]
        for c in bundle["conflicts"]:
            values = " / ".join(f"{x['value']} [{str(x['segmentId']).split('-')[0]}]" for x in c["claims"])
            lines.append(f"| {c['topic']} | {values} | {c.get('ask', '')} |")
    else:
        lines.append(t["none"])
    lines += ["", f"## {t['byOwner']}", ""]
    current = None
    internal = [r for r in rows if r["who"] == INTERNAL]
    for r in [r for r in rows if r["who"] != INTERNAL]:
        if r["who"] != current:
            current = r["who"]
            lines += ["", f"**{current}**"]
        lines.append(f"- {r['question']} _({r['source']})_")
    lines += ["", t["sheetNote"].format(sheet=t["sheet"]), t["internalNote"].format(n=len(internal)) if internal else ""]
    (out / t["summary"]).write_text("\n".join(lines), encoding="utf-8")


def question_sheet(rows: list[dict], out: Path, language: str = "ko") -> None:
    """질문지(질문지.xlsx / Questions.xlsx): 첫 시트는 고객·담당에게 물을 것(출처별 색, 숨은 id 열), 둘째 시트는 내부 점검."""
    t = TEXT[language]
    fill = lambda src: "warn" if src.startswith(t["srcConflict"]) else "info" if src.startswith(t["srcAnalysis"]) else None
    ask = [r for r in rows if r["who"] != INTERNAL]
    internal = [r for r in rows if r["who"] == INTERNAL]
    sheet = lambda name, items: {"name": name, "header": t["header"], "fills": [fill(r["source"]) for r in items],
                                 "rows": [[i + 1, r["who"], r["question"], r["source"], r["about"], "", "", "", r["id"]] for i, r in enumerate(items)],
                                 "widths": [6, 18, 60, 26, 22, 44, 12, 12, 8], "hidden": [8]}
    xlsx.write(out / t["sheet"], [sheet(t["sheetAsk"], ask)] + ([sheet(t["sheetInternal"], internal)] if internal else []))


def main() -> int:
    """맵·요약·질문지·위키를 쓰고 열 경로를 출력."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wye", nargs="?", default=".wye")
    args = parser.parse_args()
    wye = Path(args.wye).resolve()
    if not (wye / "check.json").exists():
        print("check.json 없음 — 먼저 check.py를 돌리십시오")
        return 1
    bundle = load(wye)
    out = wye.parent / "Wye"
    out.mkdir(exist_ok=True)
    rows = question_rows(bundle, out)
    bundle["questionCount"] = len(rows)
    bundle["files"] = {"summary": TEXT[bundle["language"]]["summary"], "sheet": TEXT[bundle["language"]]["sheet"]}
    payload = json.dumps(bundle, ensure_ascii=False).replace("</", "<\\/")
    page = TEMPLATE.read_text(encoding="utf-8")
    page = page.replace("__TITLE__", html.escape(bundle["title"])).replace("__DATA__", payload)
    (out / "맵.html").write_text(page, encoding="utf-8")
    pages = wiki(bundle, out / "위키")
    summary(bundle, out, rows)
    question_sheet(rows, out, bundle["language"])
    state = "" if bundle["ok"] else f" (검사 오류 {bundle['errors']}건 남음)"
    print(f"맵 {out / '맵.html'} · 요약 {out / bundle['files']['summary']} · 질문지 {out / bundle['files']['sheet']}({len(rows)}개) · 위키 {pages}쪽{state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
