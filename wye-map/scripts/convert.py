"""프로젝트 폴더의 자료를 읽을 수 있는 글로 바꾸고 근거 조각(segment)으로 나눔.

- 입구: --src로 준 폴더들(읽기만), 없으면 지난번 입구(.wye/project.json), 그것도 없으면 작업 폴더
- 결과: <작업 폴더>/.wye/sources.json(파일·해시·상태), <out>/segments.jsonl(조각 정본), <out>/text/<문서 id>.md(읽기용)
- 바뀐 파일만 다시 변환(SHA-256 대조). 사라진 파일은 removed로 표시만 하고 조각은 지움
- pdf·docx·pptx·xlsx·xls·html은 markitdown CLI 필요. 없으면 그 파일은 실패로 남기고 설치 한 줄 안내
- 50MB 넘는 pdf는 pdftotext가 있으면 글자만 뽑아 변환
- --plan: 변환하지 않고 핵심·참고·제외로 나눈 표만 출력하고 .wye/plan.json에 씀(triage.py)
- --use plan: plan.json에서 group이 "핵심"인 파일만 변환. 한 번 쓰면 기억해 "다시 읽어 줘"에도 적용
- 기본(--use auto): 예전 판·같은 문서 중복·행정 서류만 빼고(뺀 파일과 이유 출력) 나머지는 변환. --use all이면 전부
- 표준 라이브러리만 씀
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from segmenter import segment_markdown  # noqa: E402
from profiles import load as load_profile  # noqa: E402
from triage import classify  # noqa: E402

PLAIN = {".md", ".txt", ".csv", ".sql", ".json", ".yaml", ".yml"}
MARKITDOWN = {".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".html", ".htm"}
# 읽지 못하지만 조용히 빼면 누락을 모름 — 실패로 보여 줌
HANCOM = {".hwp", ".hwpx"}
# Drive for Desktop의 Google 문서는 내용 없는 바로가기 파일
GOOGLE = {".gdoc", ".gsheet", ".gslides"}
# 사람이 고른 폴더 자동 수집 상한과 같은 크기. 이보다 크면 건너뛰고 알림
MAX_BYTES = 50 * 1024 * 1024
# 사람에게 먼저 확인받을 규모. 넘으면 보고 줄에 확인 요청을 붙임
CONFIRM_CHARS = 400_000
INSTALL_HINT = "pipx install 'markitdown[pdf,docx,pptx,xlsx]'"


def sha256(path: Path) -> str:
    """파일 바이트의 SHA-256."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def to_markdown(path: Path) -> str:
    """파일 하나를 markdown 글로. 변환할 수 없으면 RuntimeError(사람 말 사유)."""
    suffix = path.suffix.lower()
    if suffix == ".pdf" and path.stat().st_size > MAX_BYTES:
        # 스캔·도판이 많은 큰 pdf는 markitdown이 느리거나 실패함 — 글자 층만 뽑음
        tool = shutil.which("pdftotext")
        if not tool:
            raise RuntimeError("50MB 초과 pdf — pdftotext(poppler)가 있으면 글자만 뽑아 읽음: brew install poppler")
        done = subprocess.run([tool, str(path), "-"], capture_output=True, text=True, timeout=600)
        if not done.stdout.strip():
            raise RuntimeError("50MB 초과 pdf에서 글자를 찾지 못함(스캔본일 수 있음)")
        return done.stdout
    if suffix in PLAIN:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix in MARKITDOWN:
        tool = shutil.which("markitdown")
        if not tool:
            raise RuntimeError(f"markitdown이 없어 읽지 못함 — 설치: {INSTALL_HINT}")
        done = subprocess.run([tool, str(path)], capture_output=True, text=True, timeout=600)
        if done.returncode != 0 or not done.stdout.strip():
            raise RuntimeError("변환 실패: " + (done.stderr.strip().splitlines() or ["글을 찾지 못함"])[-1][:200])
        return done.stdout
    if suffix in GOOGLE:
        raise RuntimeError("Google 문서 바로가기라 내용이 없음 — Drive 커넥터로 내보내 받거나, 파일 > 다운로드로 docx·xlsx·pdf를 받아 두십시오")
    if suffix in HANCOM:
        raise RuntimeError("한글 문서는 아직 못 읽음 — PDF로 저장해 같은 폴더에 두십시오")
    raise RuntimeError("지원하지 않는 형식")


def candidates(root: Path, skip: list[Path]) -> list[Path]:
    """훑을 파일 목록. 숨김 폴더·결과 폴더(skip)·Office 임시 파일(~$)은 뺌."""
    found = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if not path.is_file() or any(part.startswith(".") for part in rel.parts):
            continue
        if any(s == path or s in path.parents for s in skip) or path.name.startswith("~$"):
            continue
        if path.suffix.lower() in PLAIN | MARKITDOWN | HANCOM | GOOGLE:
            found.append(path)
    return found


def print_plan(plan: dict, paths: dict) -> None:
    """자료 고르기 표: 무리별 수·크기, 핵심 전부, 제외는 이유별 수와 예시, 참고 일부."""
    import unicodedata
    show = lambda rel: unicodedata.normalize("NFC", rel)
    size = lambda rels: sum(paths[r].stat().st_size for r in rels if r in paths) / 1e6
    groups = {g: [r for r, v in plan.items() if v["group"] == g] for g in ("핵심", "참고", "제외")}
    print(" · ".join(f"{g} {len(rs)}건({size(rs):.0f}MB)" for g, rs in groups.items()))
    print("[핵심] 변환할 문서")
    for rel in sorted(groups["핵심"]):
        print(f"  - {show(rel)}")
    print("[제외] 이유별")
    reasons: dict[str, list[str]] = {}
    for rel in groups["제외"]:
        reasons.setdefault(plan[rel]["reason"].split(":")[0], []).append(rel)
    for why, rels in sorted(reasons.items(), key=lambda x: -len(x[1])):
        print(f"  - {why} {len(rels)}건 (예: {show(Path(rels[0]).name)})")
    print(f"[참고] {len(groups['참고'])}건" + (": " + ", ".join(show(Path(r).name) for r in sorted(groups["참고"])[:8]) if groups["참고"] else ""))
    print("고칠 것이 있으면 .wye/plan.json의 group을 바꾼 뒤 --use plan으로 변환")


def resolve_sources(args, work: Path, out: Path) -> list[dict]:
    """읽을 입구 목록. 이번에 준 입구가 없으면 지난번에 기억한 입구를 씀.

    - 입구 = {label, path}. label은 폴더 이름(겹치면 _2), 작업 폴더 자신이면 "."
    - 결과 폴더가 다른 입구 폴더 안에 있으면 막음(고객 폴더에 결과가 섞이는 일 방지)
    """
    memory = out / "project.json"
    project = json.loads(memory.read_text(encoding="utf-8")) if memory.exists() else {}
    given = [Path(p).expanduser().resolve() for p in args.src]
    if not given:
        given = [Path(s["path"]) for s in project.get("sources", [])] or [work]
    sources, labels = [], set()
    for path in given:
        if not path.is_dir():
            raise SystemExit(f"폴더를 찾지 못함: {path}")
        if path != work and (work == path or path in work.parents):
            raise SystemExit(f"결과 폴더({work})가 자료 폴더({path}) 안에 있음 — 다른 작업 폴더에서 돌리십시오(예: ~/Wye/<프로젝트>)")
        label = "." if path == work else path.name
        while label in labels:
            label += "_2"
        labels.add(label)
        sources.append({"label": label, "path": str(path)})
    project["sources"] = sources
    memory.write_text(json.dumps(project, ensure_ascii=False, indent=1), encoding="utf-8")
    return sources


def main() -> int:
    """입구들을 훑어 바뀐 파일만 변환하고 규모 한 줄을 출력."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", nargs="?", default=None, help="자료 폴더이자 작업 폴더(예전 방식)")
    parser.add_argument("--src", action="append", default=[], help="읽을 자료 폴더(여러 번 가능). 읽기만 함")
    parser.add_argument("--work", default=None, help="결과를 둘 작업 폴더(기본: 지금 폴더)")
    parser.add_argument("--plan", action="store_true", help="변환하지 않고 핵심·참고·제외 표만(.wye/plan.json)")
    parser.add_argument("--use", choices=["auto", "plan", "all"], default=None,
                        help="auto(기본) = 예전 판·중복·행정 서류만 빼고 변환, plan = plan.json의 핵심만, all = 전부")
    args = parser.parse_args()
    if args.folder and not args.src:
        args.src = [args.folder]
    work = Path(args.work or (args.folder if args.folder and not args.work else ".")).expanduser().resolve()
    out = work / ".wye"
    (out / "text").mkdir(parents=True, exist_ok=True)
    sources = resolve_sources(args, work, out)

    # 이전 상태 읽기. 문서 id는 경로마다 한 번 정하면 바뀌지 않음
    state_path = out / "sources.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"files": {}}
    files: dict = state["files"]
    segments_path = out / "segments.jsonl"
    old_segments: dict[str, list[dict]] = {}
    if segments_path.exists():
        for line in segments_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            old_segments.setdefault(row["doc"], []).append(row)
    next_no = 1 + max((int(f["doc"][1:]) for f in files.values()), default=0)

    counts = {"new": 0, "changed": 0, "unchanged": 0, "removed": 0, "failed": 0, "skipped": 0}
    seen = set()
    segments: dict[str, list[dict]] = {}
    found = []
    for source in sources:
        root = Path(source["path"])
        # 결과 폴더는 건너뜀. 단 입구가 결과 폴더 안(.wye/inbox/drive — 커넥터로 받은 자료)이면 그 입구는 읽음
        skip = [s for s in (out, work / "Wye") if s != root and s not in root.parents]
        for path in candidates(root, skip):
            rel = path.relative_to(root).as_posix()
            found.append((path, rel if source["label"] == "." else f"{source['label']}/{rel}"))

    # 자료 고르기: 표만 내고 끝내거나(--plan), 핵심만 남김(--use plan, 기억됨)
    memory = out / "project.json"
    project = json.loads(memory.read_text(encoding="utf-8"))
    plan_path = out / "plan.json"
    if args.plan:
        plan = classify(found, load_profile(out))
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
        print_plan(plan, dict((rel, path) for path, rel in found))
        return 0
    use = args.use or project.get("use", "auto")
    if use == "auto":
        # 작은 폴더도 예전 판·중복·행정 서류는 뺌(이유를 출력해 사람이 볼 수 있게). 전부 읽으려면 --use all
        auto = classify(found, load_profile(out))
        dropped = [(rel, auto[rel]["reason"]) for _, rel in found if auto.get(rel, {}).get("group") == "제외"]
        found = [(path, rel) for path, rel in found if auto.get(rel, {}).get("group") != "제외"]
        for rel, why in dropped:
            print(f"  - 뺌 {rel}: {why}")
    elif use == "plan":
        plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else {}
        new = [(path, rel) for path, rel in found if rel not in plan]
        if new:
            # 지난 표 뒤에 새로 생긴 파일만 분류해 덧붙임(사람이 고친 group은 그대로)
            plan.update(classify(new, load_profile(out)))
            plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
        found = [(path, rel) for path, rel in found if plan.get(rel, {}).get("group") == "핵심"]
    if project.get("use") != use:
        project["use"] = use
        memory.write_text(json.dumps(project, ensure_ascii=False, indent=1), encoding="utf-8")
    for path, rel in found:
        seen.add(rel)
        entry = files.get(rel)
        if entry is None:
            entry = files[rel] = {"doc": f"D{next_no:03d}"}
            next_no += 1
        doc = entry["doc"]
        if path.stat().st_size > MAX_BYTES and path.suffix.lower() != ".pdf":
            entry.update(status="skipped", reason="50MB 초과")
            counts["skipped"] += 1
            continue
        digest = sha256(path)
        if entry.get("sha256") == digest and entry.get("status") == "ok" and doc in old_segments:
            segments[doc] = old_segments[doc]
            entry["change"] = "unchanged"
            counts["unchanged"] += 1
            continue
        kind = "changed" if entry.get("sha256") else "new"
        try:
            markdown = to_markdown(path)
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
            entry.update(status="failed", reason=str(error), sha256=digest)
            counts["failed"] += 1
            continue
        rows = [{"id": f"{doc}-S{d.ordinal:04d}", "doc": doc, "section": d.section,
                 "page": d.page, "text": d.text} for d in segment_markdown(markdown)]
        segments[doc] = rows
        entry.update(status="ok", sha256=digest, reason="", segments=len(rows),
                     chars=sum(len(r["text"]) for r in rows), change=kind)
        counts[kind] += 1
        # 읽기용 파일: 조각마다 [id] 머리 한 줄. 인용은 머리 아래 글에서 글자 그대로 옮김
        lines = [f"<!-- {doc} · {rel} -->", ""]
        for row in rows:
            where = " · ".join(x for x in (f"p.{row['page']}" if row["page"] else "", row["section"]) if x)
            lines += [f"[{row['id']}]" + (f" ({where})" if where else ""), row["text"], ""]
        (out / "text" / f"{doc}.md").write_text("\n".join(lines), encoding="utf-8")

    # 사라진 파일: 상태만 남기고 조각·읽기 파일은 지움
    for rel, entry in files.items():
        if rel not in seen and entry.get("status") != "removed":
            entry.update(status="removed")
            (out / "text" / f"{entry['doc']}.md").unlink(missing_ok=True)
            counts["removed"] += 1

    with segments_path.open("w", encoding="utf-8") as handle:
        for doc in sorted(segments):
            for row in segments[doc]:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")

    total_chars = sum(f.get("chars", 0) for f in files.values() if f.get("status") == "ok")
    todo = [f"{f['doc']} {rel}" for rel, f in files.items() if f.get("change") in ("new", "changed") and f.get("status") == "ok"]
    print(f"파일 새 {counts['new']} · 바뀜 {counts['changed']} · 그대로 {counts['unchanged']} · "
          f"사라짐 {counts['removed']} · 실패 {counts['failed']} · 건너뜀 {counts['skipped']} | "
          f"조각 {sum(len(v) for v in segments.values())} · 글자 {total_chars:,}")
    for rel, f in files.items():
        if f.get("status") in ("failed", "skipped"):
            print(f"  ! {f['doc']} {rel}: {f['reason']}")
    if todo:
        print("이번에 읽을 문서: " + ", ".join(todo))
    if total_chars > CONFIRM_CHARS:
        print(f"확인 필요: 글자 {total_chars:,}자로 큽니다. 진행 전에 사람에게 범위를 확인하십시오.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
