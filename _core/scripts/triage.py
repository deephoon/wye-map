"""자료 고르기(변환 전 훑기). 파일 이름·폴더만 보고 핵심·참고·제외로 나눔. AI를 쓰지 않음.

- 낱말 목록은 프로필(profiles.py, data/profiles/*.json)과 프로젝트 config.json에서 옴 — 업종·회사마다 바꿀 수 있음
- 제외: 예전 판 폴더, 같은 문서의 낮은 판·초안, 같은 이름 pdf와 Office 파일 중 pdf, 행정·양식 서류
- 핵심: 프로필 core 낱말(회의록·계획서·요구사항·리스크·보고·minutes·proposal 등)이 이름에 든 문서
- 참고: 나머지(녹취 원문, 생성 리포트 html, 데이터 json/sql, 범위 밖 폴더, DRM 표시 파일)
- 판 표시: v1.2·rev3·Rev.2, 날짜 20261113·2026-11-13·261113, draft·final·초안·최종·(1)
- 이름 규칙이 틀릴 수 있으므로 결과는 사람에게 보여 주고 한 번 묻는 데 씀(.wye/plan.json은 손으로 고쳐도 됨)
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from profiles import load as load_profile


def nfc(text: str) -> str:
    """한글 비교용 정규화. macOS 파일 이름은 자모가 풀린 꼴(NFD)이라 그대로는 한글 규칙이 안 맞음."""
    return unicodedata.normalize("NFC", text)


def pattern(words: list[str]) -> re.Pattern:
    """낱말 목록 → 정규식. 영문 낱말은 앞에 영문 글자가 붙으면 안 맞게(golden 속 old 방지)."""
    parts = [rf"(?<![A-Za-z]){w}" if re.match(r"[A-Za-z]", w) else w for w in words]
    return re.compile("(" + "|".join(parts) + ")", re.I) if parts else re.compile(r"(?!x)x")


VERSION = re.compile(r"(?:(?<![A-Za-z])[vV]|rev\.?\s*)(\d+(?:\.\d+)*)", re.I)
DATE8 = re.compile(r"(20\d{2})[-.]?([01]\d)[-.]?([0-3]\d)")
DATE6 = re.compile(r"(?<!\d)(2[5-9][01]\d[0-3]\d)(?!\d)")
# 판 표시·초안 표시: 같은 문서인지 볼 때 이름에서 지움
NOISE = re.compile(r"(_?(?:(?<![A-Za-z])[vV]|rev\.?\s*)\d+(?:\.\d+)*|20\d{2}[-.]?[01]\d[-.]?[0-3]\d|(?<!\d)2[5-9][01]\d[0-3]\d(?!\d)|"
                   r"\(송부\)|\(수정\)|수정|송부용|송부|draft|초안|검토본|공유본|최종|final|copy|사본|\(\d\)|n\.drm|drm|\[?ix\s*(내부|송부)\]?)", re.I)
DRAFT = re.compile(r"(draft|초안|이전본|wip)", re.I)
OFFICE = {".pptx", ".docx", ".xlsx", ".xls"}
DATA = {".html", ".htm", ".json", ".sql", ".csv"}


def doc_key(path: Path) -> str:
    """같은 문서의 여러 판을 한 묶음으로 보는 이름(판·날짜·초안 표시와 기호를 뺀 이름)."""
    stem = NOISE.sub("", nfc(path.stem))
    return re.sub(r"[\s_\-\.\(\)\[\]]+", "", stem).lower()


def rank(path: Path) -> tuple:
    """같은 묶음 안에서 무엇이 최신인지: 초안 아님 → 판 번호 → 날짜 → Office 우선 → 수정 시각."""
    name = nfc(path.name)
    found = VERSION.findall(name)
    version = tuple(int(x) for x in found[-1].split(".")) if found else ()
    dates = ["".join(d) for d in DATE8.findall(name)] or ["20" + d for d in DATE6.findall(name)]
    drm = "drm" in name.lower() and "drm_x" not in name.lower()
    office = path.suffix.lower() in OFFICE and not drm
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0
    return (not DRAFT.search(name), version, max(dates) if dates else "", office, mtime)


def classify(items: list[tuple[Path, str]], cfg: dict | None = None) -> dict[str, dict]:
    """(실제 경로, 표시 이름) 목록 → 표시 이름별 {group, reason}. group = 핵심 | 참고 | 제외. cfg = 프로필 설정."""
    words = (cfg or load_profile(None))["triage"]
    old, admin, strong = pattern(words["oldFolders"]), pattern(words["admin"]), pattern(words["strong"])
    aside, core, raw = pattern(words["asideFolders"]), pattern(words["core"]), pattern(words["raw"])
    result: dict[str, dict] = {}
    groups: dict[str, list[tuple[Path, str]]] = {}
    for path, rel in items:
        parts, name = [nfc(p) for p in Path(rel).parts[:-1]], nfc(path.name)
        if any(old.search(p) for p in parts):
            result[rel] = {"group": "제외", "reason": "예전 판 폴더"}
            continue
        if admin.search(name) and not strong.search(name):
            result[rel] = {"group": "제외", "reason": "행정·양식 서류"}
            continue
        # 같은 폴더 안에서만 판·중복을 비교(다른 폴더의 같은 이름 문서는 다른 문서일 수 있음 — 고객A/회의록, 고객B/회의록)
        groups.setdefault((nfc(str(Path(rel).parent)), doc_key(path)), []).append((path, rel))
    for members in groups.values():
        members.sort(key=lambda m: rank(m[0]), reverse=True)
        best_path, best_rel = members[0]
        for path, rel in members[1:]:
            same_edition = path.suffix.lower() != best_path.suffix.lower() and rank(path)[1:3] == rank(best_path)[1:3]
            why = "같은 문서 pdf·Office 중 하나만" if same_edition else "더 새 판 있음"
            result[rel] = {"group": "제외", "reason": f"{why}: {best_path.name}"}
        shown = nfc(best_rel)
        if re.search(r"n\.drm", shown, re.I):
            result[best_rel] = {"group": "참고", "reason": "DRM 보호 표시 — 열리지 않을 수 있음"}
        elif any(aside.search(p) for p in Path(shown).parts[:-1]):
            result[best_rel] = {"group": "참고", "reason": "범위 밖·참고 폴더"}
        elif raw.search(shown):
            result[best_rel] = {"group": "참고", "reason": "녹취 원문 — 회의록이 없을 때만"}
        elif best_path.suffix.lower() in DATA:
            result[best_rel] = {"group": "참고", "reason": "생성 결과·데이터 파일"}
        elif core.search(shown):
            result[best_rel] = {"group": "핵심", "reason": ""}
        else:
            result[best_rel] = {"group": "참고", "reason": ""}
    return result
