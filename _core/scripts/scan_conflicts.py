"""자료 간 불일치 후보 찾기. 같은 대상에 문서마다 다른 숫자를 적은 곳을 모음. AI를 쓰지 않음, 후보만 냄.

- 숫자+단위(프로필 units — 범용: %·원·명·건·대·일·hours…, 제조: 호기·㎛·℃·kWh…)를 찾고, 그 앞 낱말("대상 17대"의 '대상')과
  그 문장에 든 맵 항목 이름을 열쇠로 삼음
- 같은 (열쇠, 단위)에 서로 다른 문서가 겹치지 않는 값을 적었으면 후보
- 점수: 문서 수 × 값 수, 열쇠가 맵 항목 이름이면 가산. 상위 N개를 출력하고 <wye>/conflict_candidates.json에 씀
- 판단은 에이전트 몫: 같은 대상인지 보고, 판단을 바꾸는 것만 map.json conflicts로 옮김(check.py가 검사)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from profiles import load as load_profile  # noqa: E402

def number_pattern(units: list[str]) -> re.Pattern:
    """숫자+단위 정규식. 긴 단위부터(회/일이 회보다 먼저), 단위 뒤에 영문 글자가 이어지면 안 맞음."""
    alts = "|".join(re.escape(u) for u in sorted(set(units), key=len, reverse=True))
    return re.compile(rf"(\d+(?:[.,]\d+)?)\s*({alts})(?![A-Za-z])")
# 단위 바로 뒤에 와도 되는 글자(조사·어미 첫 글자). 그 밖의 한글이면 낱말 일부(예: 3대상, 5분석)로 보고 버림
AFTER_UNIT = set("을를이가은는의에로와과도만씩까부으")
# 문장 경계: 줄바꿈·표 칸, 한국어 종결(다·음·함·됨·임 + 마침표), 영어 마침표 뒤 대문자
SPLIT = re.compile(r"[\n|。]|(?<=[다음함됨임])\.\s|(?<=[a-z0-9)])\.\s+(?=[A-Z])")
# 조사·꾸밈 떼기. 열쇠 낱말을 맞추기 위함
PARTICLE = re.compile(r"(은|는|이|가|을|를|의|에|에서|으로|로|도|만|과|와)$")
# 열쇠로 쓸 뜻이 없는 낱말
STOP = {"약", "총", "및", "등", "기준", "최대", "최소", "이상", "이하", "현재", "목표", "중", "각", "전", "후", "→", "~", "", "월", "년"}
TOP = 20
# 열쇠 낱말이 숫자 앞 이 글자 수 안에 있어야 그 숫자의 주인으로 봄
NEAR = 25
# 조각의 이 비율 넘게 나오는 낱말은 흔해서 열쇠로 못 씀(데이터·범위·분석 등)
COMMON = 0.15
# 불일치는 보통 값 2~4개. 그보다 많으면 서로 다른 대상이 섞인 것
MAX_VALUES = 4


def key_before(text: str) -> str:
    """숫자 바로 앞의 낱말(조사 뗌). 숫자·기호뿐이면 그 앞 낱말."""
    tokens = [t for t in re.split(r"[\s,:;()\[\]{}/·\-~→]+", text) if t]
    for token in reversed(tokens[-3:]):
        token = PARTICLE.sub("", re.sub(r"[^0-9A-Za-z가-힣]", "", token))
        if token and not token.isdigit() and token not in STOP and not re.fullmatch(r"\d+[A-Za-z가-힣]*", token):
            return token
    return ""


def terms_of(data: dict) -> list[str]:
    """맵 항목 제목·aliases에서 숫자 없는 2자 이상 낱말(열쇠 후보)."""
    found = set()
    for e in data.get("entities", []):
        for name in [e.get("title", "")] + list(e.get("aliases") or []):
            for word in re.split(r"[\s·,()/]+", str(name)):
                word = re.sub(r"[^0-9A-Za-z가-힣]", "", word)
                if len(word) >= 2 and not re.search(r"\d", word):
                    found.add(word)
    return sorted(found, key=len, reverse=True)


def scan(segments: list[dict], terms: list[str], units: list[str]) -> list[dict]:
    """후보 목록(점수 순)."""
    num = number_pattern(units)
    if segments:
        terms = [t for t in terms if sum(t in s["text"] for s in segments) / len(segments) <= COMMON]
    common = {w for w in STOP}
    seen: dict[tuple[str, str], list[dict]] = {}
    for seg in segments:
        for sentence in SPLIT.split(seg["text"]):
            if not num.search(sentence) or len(sentence) > 400:
                continue
            in_sentence = [t for t in terms if t in sentence]
            for m in num.finditer(sentence):
                tail = sentence[m.end():m.end() + 1]
                if tail and "가" <= tail <= "힣" and tail not in AFTER_UNIT:
                    continue
                value, unit = m.group(1).replace(",", ""), m.group(2).replace("µm", "㎛").replace("um", "㎛")
                before = sentence[max(0, m.start() - NEAR):m.start()]
                keys = {key_before(sentence[:m.start()])} | {t for t in in_sentence if t in before}
                keys -= common
                for key in keys - {""}:
                    seen.setdefault((key, unit), []).append({"doc": seg["doc"], "segmentId": seg["id"], "value": value,
                                                             "sentence": re.sub(r"\s+", " ", sentence).strip()[:160]})
    out = []
    for (key, unit), hits in seen.items():
        by_doc: dict[str, set] = {}
        for h in hits:
            by_doc.setdefault(h["doc"], set()).add(h["value"])
        values = set().union(*by_doc.values())
        if len(by_doc) < 2 or not 2 <= len(values) <= MAX_VALUES:
            continue
        # 모든 문서가 같은 값을 하나라도 공유하면 같은 말을 되풀이한 것으로 봄
        if set.intersection(*by_doc.values()):
            continue
        score = len(by_doc) * (2 if key in terms else 1) / len(values)
        # 값마다 대표 문장 하나(문서가 다른 것 우선)
        examples, used = [], set()
        for h in hits:
            if h["value"] not in used:
                used.add(h["value"])
                examples.append(h)
        out.append({"key": key, "unit": unit, "values": sorted(values, key=lambda v: float(v)), "docs": sorted(by_doc),
                    "score": score, "examples": examples[:5]})
    return sorted(out, key=lambda c: -c["score"])


def main() -> int:
    """후보를 출력하고 json으로 씀."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wye", nargs="?", default=".wye")
    parser.add_argument("--top", type=int, default=TOP)
    args = parser.parse_args()
    wye = Path(args.wye).resolve()
    segments = [json.loads(l) for l in (wye / "segments.jsonl").read_text(encoding="utf-8").splitlines() if l]
    data = json.loads((wye / "map.json").read_text(encoding="utf-8")) if (wye / "map.json").exists() else {}
    candidates = scan(segments, terms_of(data), load_profile(wye)["units"])
    (wye / "conflict_candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=1), encoding="utf-8")
    for c in candidates[: args.top]:
        print(f"후보 '{c['key']}' {c['unit']}: {' / '.join(c['values'])} — 문서 {', '.join(c['docs'])}")
        for ex in c["examples"][:3]:
            print(f"   {ex['value']}{c['unit']} [{ex['segmentId']}] {ex['sentence'][:100]}")
    print(f"후보 {len(candidates)}건(상위 {min(args.top, len(candidates))}건 출력) → 같은 대상이고 판단을 바꾸는 것만 map.json conflicts로")
    return 0


if __name__ == "__main__":
    sys.exit(main())
