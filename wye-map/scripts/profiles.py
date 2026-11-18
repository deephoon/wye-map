"""프로필(업종별 설정) 읽기·고르기. 자료 고르기 낱말·신호어·단위·판정 이름을 코드 밖으로 뺌. AI를 쓰지 않음.

- 기본 프로필: _core/data/profiles/<이름>.json (general = 업종 무관, manufacturing-ai = 제조 AI 컨설팅)
- 프로젝트 맞춤: <wye>/config.json — {"profile": "general", "language": "ko", "triage": {"admin": ["추가 낱말"]},
  "units": ["추가 단위"], "remove": {"triage.admin": ["뺄 낱말"]}, "caps": {...}}
  목록은 기본값에 더해지고(remove로 뺌), 한 값(문자열·숫자)은 덮어씀
- CLI: profiles.py <wye> (지금 설정 보기) · profiles.py <wye> --init <이름> (config.json에 프로필 지정, 다른 값은 유지)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROFILES = Path(__file__).resolve().parent.parent / "data" / "profiles"
DEFAULT = "general"


def merge(base: dict, extra: dict) -> dict:
    """목록은 이어 붙여 중복 제거, 사전은 안으로 들어가 합침, 나머지는 덮어씀."""
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, list) and isinstance(out.get(key), list):
            out[key] = list(dict.fromkeys(out[key] + value))
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def builtin(name: str) -> dict:
    """기본 프로필 하나(extends를 따라 올라가며 합침)."""
    path = PROFILES / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"프로필 '{name}' 없음 — 있는 것: {', '.join(p.stem for p in sorted(PROFILES.glob('*.json')))}")
    data = json.loads(path.read_text(encoding="utf-8"))
    parent = data.pop("extends", None)
    return merge(builtin(parent), data) if parent else data


def load(wye: Path | None) -> dict:
    """작업 폴더의 실제 설정 = 기본 프로필 + config.json 맞춤 − remove."""
    config = {}
    if wye is not None and (Path(wye) / "config.json").exists():
        config = json.loads((Path(wye) / "config.json").read_text(encoding="utf-8"))
    extra = {k: v for k, v in config.items() if k not in ("profile", "remove", "caps")}
    result = merge(builtin(config.get("profile", DEFAULT)), extra)
    # remove: {"triage.admin": ["원가"]} 꼴로 기본 목록에서 뺌
    for dotted, words in (config.get("remove") or {}).items():
        node = result
        *parents, leaf = dotted.split(".")
        for part in parents:
            node = node.get(part, {})
        if isinstance(node.get(leaf), list):
            node[leaf] = [w for w in node[leaf] if w not in words]
    return result


def main() -> int:
    """지금 설정을 보이거나 프로필을 지정."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wye", nargs="?", default=".wye")
    parser.add_argument("--init", metavar="이름", help="config.json에 이 프로필을 지정(다른 맞춤 값은 유지)")
    args = parser.parse_args()
    wye = Path(args.wye).resolve()
    if args.init:
        builtin(args.init)
        wye.mkdir(parents=True, exist_ok=True)
        path = wye / "config.json"
        config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        config["profile"] = args.init
        path.write_text(json.dumps(config, ensure_ascii=False, indent=1), encoding="utf-8")
    cfg = load(wye)
    print(f"프로필 {cfg['name']} — {cfg.get('description', '')}")
    print(f"결과 언어 {cfg.get('language', 'ko')} · 판정 이름 '{cfg['analysis']['verdictTitle']}' · 접근 {' / '.join(cfg['analysis']['approaches'])}")
    print(f"핵심 낱말 {len(cfg['triage']['core'])} · 행정 낱말 {len(cfg['triage']['admin'])} · 신호어 {len(cfg['signals'])} · 단위 {len(cfg['units'])}")
    print("있는 프로필: " + ", ".join(p.stem for p in sorted(PROFILES.glob("*.json"))) + f" · 맞춤 파일 {wye / 'config.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
