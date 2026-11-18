"""설치·도구 점검. 다른 사람 PC(macOS·Windows·Linux)에서 처음 쓸 때 무엇이 빠졌는지 한 번에 보여 줌. 고치지는 않음.

- 파이썬 판(3.9 이상), markitdown(pdf·Office 읽기), pdftotext(50MB 넘는 pdf), Google Drive for Desktop 위치
- 스킬 설치(~/.claude/skills·~/.codex/skills), 스킬 안 공용 폴더 연결(scripts·data·shared — Windows에서 git이
  심볼릭 링크를 글자 파일로 받으면 깨짐), AAS 전용 환경(.venv)
- 줄마다 ✓ / ✗ / · (선택) 와 고치는 한 줄. 필수가 빠지면 종료 코드 1
"""

from __future__ import annotations

import os
import shutil
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# 이 저장소에 있는 스킬만 점검(공개판에는 wye-map만 있음)
SKILLS = tuple(s for s in ("wye-map", "wye-requirements", "wye-aas") if (ROOT / s).is_dir())
WINDOWS = sys.platform.startswith("win")


def drive_roots() -> list[Path]:
    """Drive for Desktop이 보이는 곳. macOS는 CloudStorage, Windows는 드라이브 문자 아래 '내 드라이브'·'공유 드라이브'."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "CloudStorage"
        return sorted(base.glob("GoogleDrive-*")) if base.exists() else []
    if WINDOWS:
        found = []
        for letter in string.ascii_uppercase:
            for name in ("My Drive", "내 드라이브", "Shared drives", "공유 드라이브"):
                path = Path(f"{letter}:\\") / name
                if path.exists():
                    found.append(path)
        return found
    return []


def main() -> int:
    """점검표를 출력."""
    rows: list[tuple[str, str, str]] = []
    need_fail = False

    def add(ok: bool | None, what: str, fix: str = "") -> None:
        nonlocal need_fail
        mark = "✓" if ok else ("·" if ok is None else "✗")
        need_fail |= ok is False
        rows.append((mark, what, fix))

    add(sys.version_info >= (3, 9), f"파이썬 {sys.version.split()[0]}", "파이썬 3.9 이상 설치")
    pip = "pipx install 'markitdown[pdf,docx,pptx,xlsx]'" if not WINDOWS else 'pipx install "markitdown[pdf,docx,pptx,xlsx]"'
    add(bool(shutil.which("markitdown")), "markitdown — pdf·docx·pptx·xlsx 읽기", pip)
    poppler = "brew install poppler" if sys.platform == "darwin" else ("winget install oschwartz10612.Poppler" if WINDOWS else "apt install poppler-utils")
    add(True if shutil.which("pdftotext") else None, "pdftotext — 50MB 넘는 pdf (선택)", poppler)
    roots = drive_roots()
    add(True if roots else None, "Google Drive for Desktop — " + (", ".join(str(r) for r in roots[:3]) if roots else "못 찾음 (선택: 폴더 경로를 직접 주거나 Drive 커넥터 사용)"))
    if roots and sys.platform != "darwin":
        rows.append(("·", "Drive 링크 → 폴더 자동 찾기는 macOS만 됨. 이 PC에서는 위 위치에서 폴더 경로를 복사해 주십시오", ""))
    for home in (Path.home() / ".claude" / "skills", Path.home() / ".codex" / "skills"):
        for skill in SKILLS:
            target = home / skill
            installer = "install.ps1" if WINDOWS else "install.sh"
            add(True if target.exists() else (None if "codex" in str(home) else False), f"스킬 설치 {target}", f"{ROOT / installer} 실행")
    for skill in [s for s in SKILLS if s != "wye-aas"]:
        for link in ("scripts", "data", "shared"):
            path = ROOT / skill / link
            add(path.is_dir(), f"{skill}/{link} 연결", ("install.ps1을 다시 실행(심볼릭 링크를 폴더 연결로 바꿈)" if WINDOWS else "git checkout으로 링크 복구"))
    venv = ROOT / "wye-aas" / ".venv"
    if "wye-aas" in SKILLS:
        add(True if venv.exists() else None, "AAS 전용 환경 wye-aas/.venv (선택 — 처음 AAS를 만들 때 자동 설치, 인터넷 필요)")
    for mark, what, fix in rows:
        print(f"{mark} {what}" + (f"  → {fix}" if fix and mark == "✗" else ""))
    print("필수 항목이 모두 갖춰졌습니다" if not need_fail else "✗ 항목을 고친 뒤 다시 점검하십시오")
    return 1 if need_fail else 0


if __name__ == "__main__":
    sys.exit(main())
