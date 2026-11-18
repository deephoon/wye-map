"""공용 재료(_core)를 각 스킬 폴더에 실제 파일로 복사함. 정본은 _core 한 곳.

왜 복사인가: 스킬 안 심볼릭 링크는 파일 찾기 도구(Glob·ripgrep·find 기본값)가 따라가지 않아 에이전트가
"스크립트가 없다"고 판단했고(실제 실행에서 확인), Windows git은 링크를 글자 파일로 받음. 복사본이면 어디서나 보임.

- 복사: _core/scripts → <skill>/scripts, _core/data → data, _core/viewer → viewer, _core/docs → shared
  (wye-map·wye-requirements), _core/scripts/drive_locate.py → wye-aas/scripts/
- python3 sync_core.py          복사(바뀐 것만 덮어씀, 정본에 없는 파일은 지움)
- python3 sync_core.py --check  다르면 목록을 출력하고 종료 코드 1(시험이 씀)
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORE = ROOT / "_core"
PAIRS = [("scripts", "scripts"), ("data", "data"), ("viewer", "viewer"), ("docs", "shared")]
# 이 저장소에 있는 스킬만(공개판에는 wye-map만 있음)
SKILLS = tuple(s for s in ("wye-map", "wye-requirements") if (ROOT / s).is_dir())
SKIP = {"__pycache__", ".DS_Store"}


def files_under(folder: Path) -> dict[str, Path]:
    """상대 경로 → 파일(캐시 제외)."""
    if not folder.is_dir():
        return {}
    return {p.relative_to(folder).as_posix(): p for p in folder.rglob("*")
            if p.is_file() and not any(part in SKIP for part in p.parts)}


def plan() -> list[tuple[Path, Path | None]]:
    """(대상, 원본 또는 None=지울 것) 목록 — 실제로 다른 것만."""
    jobs: list[tuple[Path, Path | None]] = []
    pairs = [(CORE / src, ROOT / skill / dst) for skill in SKILLS for src, dst in PAIRS]
    for src_dir, dst_dir in pairs:
        # 예전 링크, 또는 Windows git이 링크를 받아 만든 글자 파일이면 먼저 지움
        if dst_dir.is_symlink() or dst_dir.is_file():
            jobs.append((dst_dir, None))
        source, target = files_under(src_dir), ({} if dst_dir.is_symlink() or dst_dir.is_file() else files_under(dst_dir))
        for rel, path in source.items():
            out = dst_dir / rel
            if rel not in target or not filecmp.cmp(path, target[rel], shallow=False):
                jobs.append((out, path))
        jobs += [(target[rel], None) for rel in target if rel not in source]
    single = (CORE / "scripts" / "drive_locate.py", ROOT / "wye-aas" / "scripts" / "drive_locate.py")
    if not single[1].parent.is_dir():
        return jobs
    if single[1].is_symlink() or not single[1].exists() or not filecmp.cmp(*single, shallow=False):
        jobs.append((single[1], single[0]))
    return jobs


def main() -> int:
    """복사하거나(기본) 다른 곳만 보고(--check)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    jobs = plan()
    if args.check:
        for target, source in jobs:
            print(("다름 " if source else "남은 파일 ") + str(target.relative_to(ROOT)))
        return 1 if jobs else 0
    # 지울 것(링크·글자 파일)을 먼저 처리해야 그 자리에 폴더를 만들 수 있음
    jobs.sort(key=lambda job: job[1] is not None)
    for target, source in jobs:
        # 예전 심볼릭 링크(폴더·파일)는 링크만 지움 — 링크가 가리키던 _core 정본은 건드리지 않음
        if target.is_symlink():
            target.unlink()
        if source is None:
            if target.exists() and not target.is_dir():
                target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    print(f"복사 {sum(1 for _, s in jobs if s)} · 지움 {sum(1 for _, s in jobs if not s)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
