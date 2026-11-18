"""스크립트 시험. 실행: python3 -m unittest discover -s wye-project/tests"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import check  # noqa: E402

DOC = """# 압착 공정 개선 회의

A사 2라인 압착 공정의 불량률을 3%에서 1%로 낮추는 것이 목표다.

현재 작업자가 시료를 육안으로 보고 합부를 정한다.
"""


def run(script, *args):
    """스크립트를 돌려 (종료 코드, 출력)."""
    done = subprocess.run([sys.executable, str(SCRIPTS / script), *args], capture_output=True, text=True)
    return done.returncode, done.stdout + done.stderr


def entity(eid, type_, title, seg, quote):
    """시험용 항목 하나."""
    return {"id": eid, "type": type_, "title": title, "importance": 3,
            "evidence": [{"segmentId": seg, "quote": quote}]}


class Pipeline(unittest.TestCase):
    """변환 → 검사 → 결과물."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "회의록.md").write_text(DOC, encoding="utf-8")
        self.wye = self.dir / ".wye"
        code, out = run("convert.py", str(self.dir))
        self.assertEqual(code, 0, out)

    def write_map(self, entities, relations):
        (self.wye / "map.json").write_text(json.dumps(
            {"brief": "b", "entities": entities, "relations": relations}, ensure_ascii=False), encoding="utf-8")

    def good_map(self):
        self.write_map(
            [entity("e1", "Project", "압착 공정 개선", "D001-S0001", "압착 공정 개선 회의"),
             entity("e2", "Goal", "불량률 1% 달성", "D001-S0002", "불량률을 3%에서 1%로 낮추는 것이 목표다."),
             entity("e3", "CurrentPractice", "육안 합부 판정", "D001-S0003", "작업자가 시료를 육안으로 보고")],
            [{"fromId": "e1", "type": "HAS_GOAL", "toId": "e2", "why": "회의가 정한 목표"}])

    def problem_map(self, conflicts=None):
        """문제 하나가 목표를 막는 맵 + 선택적 불일치."""
        self.good_map()
        data = json.loads((self.wye / "map.json").read_text(encoding="utf-8"))
        data["entities"].append(entity("e4", "Problem", "육안 판정 편차", "D001-S0003", "작업자가 시료를 육안으로 보고"))
        data["relations"].append({"fromId": "e4", "type": "BLOCKS", "toId": "e2", "why": "판정이 흔들리면 불량률을 못 잰다"})
        if conflicts is not None:
            data["conflicts"] = conflicts
        (self.wye / "map.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def sheet(self, body):
        folder = self.dir / "Wye" / "분석"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "육안 판정 편차.md").write_text("# 육안 판정 편차\n\n" + body, encoding="utf-8")

    def test_conflict_needs_real_quotes_from_two_segments(self):
        claim = lambda seg, value, quote: {"segmentId": seg, "value": value, "quote": quote}
        good = {"id": "X1", "topic": "판정 방식", "entityIds": ["e4"],
                "claims": [claim("D001-S0002", "3%", "불량률을 3%에서 1%로"), claim("D001-S0003", "육안", "작업자가 시료를 육안으로 보고")]}
        self.problem_map([good])
        code, out = run("check.py", str(self.wye))
        self.assertEqual(code, 0, out)
        self.assertIn("불일치 1", out)
        one_segment = {**good, "claims": [good["claims"][0], {**good["claims"][0], "value": "5%"}]}
        invented = {**good, "claims": [good["claims"][0], claim("D001-S0003", "기계", "기계가 자동으로 판정한다")]}
        for bad, message in ((one_segment, "서로 다른 조각"), (invented, "글자 그대로 없음")):
            self.problem_map([bad])
            code, out = run("check.py", str(self.wye))
            self.assertNotEqual(code, 0)
            self.assertIn(message, out)

    def test_verify_catches_invented_quote_and_verdict_rule(self):
        self.problem_map()
        run("check.py", str(self.wye))
        self.sheet('근거: "작업자가 시료를 육안으로 보고" [D001-S0003]\n\n- **판정**: 조건부 가능\n')
        code, out = run("verify.py", str(self.wye))
        self.assertEqual(code, 0, out)
        self.assertIn("인용 1", out)
        self.sheet('근거: "작업자가 저울로 무게를 잰다" [D001-S0003]\n\n- **판정**: 가능\n')
        code, out = run("verify.py", str(self.wye))
        self.assertNotEqual(code, 0)
        self.assertIn("글자 그대로 없음", out)
        self.assertIn("판단에 쓰는 데이터 자리가 비었는데", out)

    def test_render_shows_integrity(self):
        claim = lambda seg, value, quote: {"segmentId": seg, "value": value, "quote": quote}
        self.problem_map([{"id": "X1", "topic": "판정 방식 불일치", "entityIds": ["e4"],
                           "claims": [claim("D001-S0002", "3%", "불량률을 3%에서 1%로"), claim("D001-S0003", "육안", "작업자가 시료를 육안으로 보고")]}])
        run("check.py", str(self.wye))
        self.sheet('근거: "작업자가 시료를 육안으로 보고"\n\n- **판정**: 조건부 가능\n')
        code, out = run("render.py", str(self.wye))
        self.assertEqual(code, 0, out)
        page = (self.dir / "Wye" / "맵.html").read_text(encoding="utf-8")
        self.assertIn("판정 방식 불일치", page)
        self.assertIn('"verdict": "조건부 가능"', page)
        self.assertIn('"chains": [{', page)

    def test_doc_only_citation_gets_segment_id(self):
        self.good_map()
        data = json.loads((self.wye / "map.json").read_text(encoding="utf-8"))
        data["entities"][1]["evidence"] = [{"doc": "D001", "quote": "불량률을 3%에서 1%로 낮추는 것이 목표다."}]
        data["entities"][2]["evidence"] = [{"doc": "D001", "quote": "로봇이 자동으로 판정한다"}]
        (self.wye / "map.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        code, out = run("check.py", str(self.wye))
        self.assertNotEqual(code, 0)
        self.assertIn("e3: 인용이 D001 원문에 글자 그대로 없음", out)
        saved = json.loads((self.wye / "map.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["entities"][1]["evidence"][0]["segmentId"], "D001-S0002")
        self.assertEqual(saved["entities"][2]["evidence"][0].get("doc"), "D001")

    def test_verify_points_to_right_segment(self):
        self.problem_map()
        run("check.py", str(self.wye))
        self.sheet('근거: "작업자가 시료를 육안으로 보고" [D001-S0001] / "불량률을 3%에서 1%로" [D001]\n\n- **판정**: 조건부 가능\n')
        code, out = run("verify.py", str(self.wye))
        self.assertNotEqual(code, 0)
        self.assertIn("D001-S0003에 있음", out)
        self.assertNotIn("3%에서", out)

    def test_outline_and_conflict_scan(self):
        (self.dir / "보고서.md").write_text("# 주간 보고\n\n수집 대상 17대를 확정했다.\n", encoding="utf-8")
        (self.dir / "계획서.md").write_text("# 사업 계획\n\n수집 대상 19대를 기준으로 한다.\n", encoding="utf-8")
        run("convert.py", str(self.dir))
        self.good_map()
        code, out = run("outline.py", str(self.wye))
        self.assertEqual(code, 0, out)
        self.assertIn("전부 읽기", (self.wye / "outline.md").read_text(encoding="utf-8"))
        code, out = run("scan_conflicts.py", str(self.wye))
        self.assertEqual(code, 0, out)
        self.assertIn("후보 '대상' 대: 17 / 19", out)

    def test_convert_is_incremental_and_ids_stable(self):
        segments = (self.wye / "segments.jsonl").read_text(encoding="utf-8")
        code, out = run("convert.py", str(self.dir))
        self.assertIn("그대로 1", out)
        self.assertEqual(segments, (self.wye / "segments.jsonl").read_text(encoding="utf-8"))

    def test_removed_file_is_marked(self):
        (self.dir / "회의록.md").unlink()
        code, out = run("convert.py", str(self.dir))
        self.assertIn("사라짐 1", out)
        self.assertFalse((self.wye / "text" / "D001.md").exists())

    def test_invented_quote_fails(self):
        self.write_map([entity("e1", "Project", "압착 공정 개선", "D001-S0001", "지어낸 문장")], [])
        errors, _ = check.check(self.wye)
        self.assertTrue(any("글자 그대로 없음" in e for e in errors))

    def test_whitespace_in_quote_is_ignored(self):
        self.write_map([entity("e1", "Project", "압착 공정 개선", "D001-S0002", "불량률을 3%에서\n  1%로")], [])
        errors, _ = check.check(self.wye)
        self.assertEqual(errors, [])

    def test_caps_and_title_length(self):
        (self.wye / "config.json").write_text('{"caps": {"maxEntities": 1}}', encoding="utf-8")
        self.write_map([entity("e1", "Project", "가" * 31, "D001-S0001", "압착 공정 개선 회의"),
                        entity("e2", "Goal", "목표", "D001-S0001", "압착 공정 개선 회의")], [])
        errors, _ = check.check(self.wye)
        self.assertTrue(any("상한 1" in e for e in errors))
        self.assertTrue(any("31자" in e for e in errors))

    def test_disallowed_relation_and_missing_why(self):
        self.good_map()
        data = json.loads((self.wye / "map.json").read_text(encoding="utf-8"))
        data["relations"].append({"fromId": "e2", "type": "HAS_GOAL", "toId": "e1"})
        (self.wye / "map.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        errors, _ = check.check(self.wye)
        self.assertTrue(any("허용되지 않음" in e for e in errors))
        self.assertTrue(any("why 없음" in e for e in errors))

    def test_disconnected_item_is_held_and_rendered(self):
        self.good_map()
        code, out = run("check.py", str(self.wye))
        self.assertEqual(code, 0, out)
        result = json.loads((self.wye / "check.json").read_text(encoding="utf-8"))
        self.assertIn("e3", result["held"])
        self.assertNotIn("e3", result["promoted"])
        code, out = run("render.py", str(self.wye))
        self.assertEqual(code, 0, out)
        page = (self.dir / "Wye" / "맵.html").read_text(encoding="utf-8")
        self.assertNotIn("__DATA__", page)
        self.assertTrue((self.dir / "Wye" / "위키" / "index.md").exists())
        self.assertIn("진단 요약", (self.dir / "Wye" / "요약.md").read_text(encoding="utf-8"))
        self.assertTrue((self.dir / "Wye" / "질문지.xlsx").exists())

    def test_search_finds_entity_and_segment(self):
        self.good_map()
        code, out = run("search.py", "불량률", "--wye", str(self.wye))
        self.assertIn("e2", out)
        self.assertIn("[D001-S0002]", out)


if __name__ == "__main__":
    unittest.main()


class Sources(unittest.TestCase):
    """여러 입구: 읽기만, 결과는 작업 폴더에만."""

    def setUp(self):
        base = Path(tempfile.mkdtemp())
        self.a, self.b, self.work = base / "고객A", base / "고객B", base / "작업"
        for folder, name in ((self.a, "회의록.md"), (self.b, "회의록.md")):
            folder.mkdir()
            (folder / name).write_text(DOC, encoding="utf-8")
        self.work.mkdir()

    def listing(self, folder):
        return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*"))

    def test_two_sources_no_writes_inside_and_remembered(self):
        before = (self.listing(self.a), self.listing(self.b))
        code, out = run("convert.py", "--src", str(self.a), "--src", str(self.b), "--work", str(self.work))
        self.assertEqual(code, 0, out)
        self.assertEqual(before, (self.listing(self.a), self.listing(self.b)))
        files = json.loads((self.work / ".wye" / "sources.json").read_text(encoding="utf-8"))["files"]
        self.assertEqual(sorted(files), ["고객A/회의록.md", "고객B/회의록.md"])
        self.assertEqual(len({f["doc"] for f in files.values()}), 2)
        (self.a / "회의록.md").write_text(DOC + "\n추가 문장.\n", encoding="utf-8")
        code, out = run("convert.py", "--work", str(self.work))
        self.assertIn("바뀜 1", out)
        self.assertIn("그대로 1", out)

    def test_work_inside_source_is_refused(self):
        inside = self.a / "결과"
        inside.mkdir()
        code, out = run("convert.py", "--src", str(self.a), "--work", str(inside))
        self.assertNotEqual(code, 0)
        self.assertIn("자료 폴더", out)


    def test_connector_inbox_inside_work_is_read(self):
        inbox = self.work / ".wye" / "inbox" / "drive" / "회의록"
        inbox.mkdir(parents=True)
        (inbox / "회의록.md").write_text(DOC, encoding="utf-8")
        code, out = run("convert.py", "--src", str(inbox), "--work", str(self.work))
        self.assertEqual(code, 0, out)
        files = json.loads((self.work / ".wye" / "sources.json").read_text(encoding="utf-8"))["files"]
        self.assertEqual(sorted(files), ["회의록/회의록.md"])


class Triage(unittest.TestCase):
    """자료 고르기: 예전 판·중복·행정 서류 제외, 핵심만 변환."""

    def test_plan_then_use_plan_converts_core_only(self):
        src, work = Path(tempfile.mkdtemp()) / "자료", Path(tempfile.mkdtemp())
        (src / "_이전버전").mkdir(parents=True)
        files = {"회의록_v1.0_20261101.md": DOC, "회의록_v1.1_20261105.md": DOC, "_이전버전/회의록_v0.9.md": DOC,
                 "원가보고서_v3.md": "원가", "사업계획서_원가감리반영_최종.md": DOC, "메모.md": "메모"}
        for name, text in files.items():
            (src / name).write_text(text, encoding="utf-8")
        code, out = run("convert.py", "--src", str(src), "--work", str(work), "--plan")
        self.assertEqual(code, 0, out)
        plan = {Path(k).name: v for k, v in json.loads((work / ".wye" / "plan.json").read_text(encoding="utf-8")).items()}
        self.assertEqual(plan["회의록_v1.1_20261105.md"]["group"], "핵심")
        self.assertTrue(plan["회의록_v1.0_20261101.md"]["reason"].startswith("더 새 판 있음"))
        self.assertEqual(plan["회의록_v0.9.md"]["reason"], "예전 판 폴더")
        self.assertEqual(plan["원가보고서_v3.md"]["reason"], "행정·양식 서류")
        self.assertEqual(plan["사업계획서_원가감리반영_최종.md"]["group"], "핵심")
        self.assertEqual(plan["메모.md"]["group"], "참고")
        self.assertFalse((work / ".wye" / "segments.jsonl").exists())
        code, out = run("convert.py", "--src", str(src), "--work", str(work), "--use", "plan")
        self.assertEqual(code, 0, out)
        converted = sorted(Path(k).name for k, v in json.loads((work / ".wye" / "sources.json").read_text(encoding="utf-8"))["files"].items() if v.get("status") == "ok")
        self.assertEqual(converted, ["사업계획서_원가감리반영_최종.md", "회의록_v1.1_20261105.md"])


class General(unittest.TestCase):
    """범용: 영어 자료, 프로필·맞춤 설정."""

    def test_english_names_are_triaged(self):
        sys.path.insert(0, str(SCRIPTS))
        import triage
        items = [(Path(n), n) for n in ("Kickoff_Meeting_Minutes_rev2.docx", "Kickoff_Meeting_Minutes_rev3.docx",
                                        "archive/Proposal_v1.pdf", "Travel_Expense_2026-10.xlsx", "Golden_Sample_Report_final.pdf")]
        plan = triage.classify(items)
        self.assertEqual(plan["Kickoff_Meeting_Minutes_rev3.docx"]["group"], "핵심")
        self.assertTrue(plan["Kickoff_Meeting_Minutes_rev2.docx"]["reason"].startswith("더 새 판 있음"))
        self.assertEqual(plan["archive/Proposal_v1.pdf"]["reason"], "예전 판 폴더")
        self.assertEqual(plan["Travel_Expense_2026-10.xlsx"]["reason"], "행정·양식 서류")
        self.assertEqual(plan["Golden_Sample_Report_final.pdf"]["group"], "핵심")

    def test_profile_merge_and_remove(self):
        sys.path.insert(0, str(SCRIPTS))
        import profiles
        wye = Path(tempfile.mkdtemp())
        (wye / "config.json").write_text(json.dumps({"profile": "manufacturing-ai", "units": ["TPS"], "remove": {"triage.admin": ["경비"]}}), encoding="utf-8")
        cfg = profiles.load(wye)
        self.assertIn("호기", cfg["units"])
        self.assertIn("TPS", cfg["units"])
        self.assertIn("%", cfg["units"])
        self.assertNotIn("경비", cfg["triage"]["admin"])
        self.assertEqual(cfg["analysis"]["verdictTitle"], "AI 적용 판정")
        self.assertEqual(profiles.load(None)["analysis"]["verdictTitle"], "해결 방향 판정")

    def test_english_outline_and_scan(self):
        folder = Path(tempfile.mkdtemp())
        (folder / "minutes.md").write_text("# Kickoff minutes\n\nThe current issue is a delay. Goal decided: migrate 120 users. Scope TBD.\n", encoding="utf-8")
        (folder / "proposal.md").write_text("# Proposal\n\nWe plan to migrate 150 users in phase one.\n", encoding="utf-8")
        run("convert.py", str(folder))
        wye = folder / ".wye"
        (wye / "map.json").write_text(json.dumps({"entities": []}), encoding="utf-8")
        code, out = run("scan_conflicts.py", str(wye))
        self.assertIn("후보 'migrate' users: 120 / 150", out)
        (folder / "long.md").write_text("# Long\n\n" + "\n\n".join(f"Section {i}. The current issue and goal are pending decision." for i in range(600)), encoding="utf-8")
        run("convert.py", str(folder))
        code, out = run("outline.py", str(wye))
        self.assertEqual(code, 0, out)
        self.assertIn("issue", (wye / "outline.md").read_text(encoding="utf-8"))

    def test_english_sheet_and_summary(self):
        sys.path.insert(0, str(SCRIPTS))
        import verify
        self.assertEqual(verify.verdict_of("- **Verdict**: Conditionally feasible — needs export"), "조건부 가능")
        self.assertEqual(verify.verdict_of("- **Verdict**: Not feasible now"), "지금은 불가")
        folder = Path(tempfile.mkdtemp())
        (folder / "minutes.md").write_text("# Minutes\n\nTickets are copied into a spreadsheet by hand.\n\nGoal: weekly first-response report.\n", encoding="utf-8")
        run("convert.py", str(folder))
        wye = folder / ".wye"
        (wye / "config.json").write_text(json.dumps({"language": "en"}), encoding="utf-8")
        (wye / "map.json").write_text(json.dumps({"title": "T", "brief": "b", "entities": [
            entity("p", "Project", "Helpdesk", "D001-S0001", "Minutes"),
            entity("g", "Goal", "Weekly report", "D001-S0003", "Goal: weekly first-response report."),
            entity("x", "Problem", "No baseline", "D001-S0002", "Tickets are copied into a spreadsheet by hand.")],
            "relations": [{"fromId": "p", "type": "HAS_GOAL", "toId": "g", "why": "w"}, {"fromId": "x", "type": "BLOCKS", "toId": "g", "why": "w"}]}), encoding="utf-8")
        run("check.py", str(wye))
        (folder / "Wye" / "Analysis").mkdir(parents=True)
        (folder / "Wye" / "Analysis" / "No baseline.md").write_text('# No baseline\n\n"Tickets are copied into a spreadsheet by hand." [D001]\n\n- **Verdict**: Conditionally feasible\n- **Next checks**:\n  - Client IT should send the export.\n', encoding="utf-8")
        code, out = run("verify.py", str(wye))
        self.assertEqual(code, 0, out)
        code, out = run("render.py", str(wye))
        self.assertEqual(code, 0, out)
        summary = (folder / "Wye" / "Summary.md").read_text(encoding="utf-8")
        self.assertIn("No baseline — Conditionally feasible", summary)
        self.assertIn("**Client IT**", summary)
        self.assertTrue((folder / "Wye" / "Questions.xlsx").exists())

    def test_doctor_runs(self):
        code, out = run("doctor.py")
        self.assertIn("파이썬", out)
        self.assertIn(code, (0, 1))


class Sync(unittest.TestCase):
    """스킬 폴더의 공용 재료 복사본이 _core 정본과 같은지(고친 뒤 sync_core.py를 안 돌리면 실패)."""

    def test_skill_copies_match_core(self):
        root = SCRIPTS.parents[1]
        done = subprocess.run([sys.executable, str(root / "sync_core.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, "python3 sync_core.py 를 돌리십시오:\n" + done.stdout)


class Analyze(unittest.TestCase):
    """문제 고리·영향 범위·구조 진단."""

    def setUp(self):
        sys.path.insert(0, str(SCRIPTS))
        import analyze
        self.a = analyze
        self.onto = json.loads(analyze.ONTOLOGY.read_text(encoding="utf-8"))
        self.ents = {i: {"id": i, "type": t, "title": n} for i, t, n in (
            ("p", "Problem", "압착 불량 사후 파악"), ("o", "Observation", "조건 편차 반복"), ("k", "KPI", "불량률"),
            ("c", "CurrentPractice", "육안 판정"), ("g", "Goal", "불량률 1.5%"), ("x", "System", "MES"))}
        self.rels = [{"fromId": "o", "type": "INDICATES", "toId": "p"}, {"fromId": "o", "type": "HURTS", "toId": "k"},
                     {"fromId": "c", "type": "JUDGES", "toId": "k"}, {"fromId": "p", "type": "BLOCKS", "toId": "g"}]

    def test_chain_marks_missing_data_slot(self):
        chain = self.a.assemble_chain(self.ents, self.rels, self.onto["problem_chain"], "p")
        filled = {s["key"]: [n["id"] for n in s["nodes"]] for s in chain["slots"]}
        self.assertEqual(filled["observation"], ["o"])
        self.assertEqual(filled["judgment"], ["c"])
        self.assertEqual(chain["missing"], ["판단에 쓰는 데이터"])
        self.assertIsNone(self.a.assemble_chain(self.ents, self.rels, self.onto["problem_chain"], "k"))

    def test_impact_depth_and_isolated(self):
        items = self.a.impact(self.ents, self.rels, "p", 1)
        self.assertEqual({i["id"] for i in items}, {"o", "g"})
        self.assertEqual({i["id"] for i in self.a.impact(self.ents, self.rels, "p", 2)}, {"o", "g", "k"})
        self.assertEqual(self.a.diagnose(self.ents, self.rels)["isolated"], ["MES"])


class Excel(unittest.TestCase):
    """xlsx 쓰기·내보내기·고객 회신 왕복."""

    def test_xlsx_is_valid_zip_with_sheets(self):
        import zipfile
        sys.path.insert(0, str(SCRIPTS))
        import xlsx
        path = Path(tempfile.mkdtemp()) / "t.xlsx"
        xlsx.write(path, [{"name": "가/나", "header": ["a", "b"], "rows": [["값<&>", 3]], "fills": ["ok"], "hidden": [1], "widths": [10, 5]}])
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            sheet = z.read("xl/worksheets/sheet1.xml").decode()
            book = z.read("xl/workbook.xml").decode()
        self.assertIn("xl/styles.xml", names)
        self.assertIn("값&lt;&amp;&gt;", sheet)
        self.assertIn('hidden="1"', sheet)
        self.assertIn('name="가_나"', book)

    @unittest.skipUnless(__import__("shutil").which("markitdown"), "markitdown 없음")
    def test_customer_reply_becomes_quotable_source(self):
        sys.path.insert(0, str(SCRIPTS))
        import xlsx
        base = Path(tempfile.mkdtemp())
        src, work = base / "자료", base / "작업"
        src.mkdir()
        work.mkdir()
        xlsx.write(src / "질문지_회신.xlsx", [{"name": "질문지", "header": ["번호", "요구 번호", "질문", "왜 묻나", "답(작성해 주십시오)"],
                                            "rows": [[1, "R001", "건수는?", "데이터", "2025년 1월부터 LOT 41만 건"]]}])
        code, out = run("convert.py", "--src", str(src), "--work", str(work))
        self.assertEqual(code, 0, out)
        segments = (work / ".wye" / "segments.jsonl").read_text(encoding="utf-8")
        self.assertIn("2025년 1월부터 LOT 41만 건", segments)
