# 프로필·프로젝트 맞춤

같은 스킬을 업종·회사·언어가 다른 프로젝트에 쓰기 위한 설정. 코드를 고치지 않고 `.wye/config.json` 한 파일로 바꾼다.

## 프로필 고르기

| 프로필 | 쓰는 곳 | 다른 점 |
|---|---|---|
| `general` (기본) | 업종 무관 — IT 구축, 서비스 기획, 일반 컨설팅·PM 자료 | 판정 이름 "해결 방향 판정", 접근 = 절차 개선·시스템·전산화·데이터 분석·외부 도입·범위 밖 |
| `manufacturing-ai` | 제조 AI·스마트공장 컨설팅 | general + 설비·태그·레시피 낱말, 호기·㎛·℃·kWh 단위, "AI 적용 판정"과 라벨 규칙 |

```sh
python3 SKILL/scripts/profiles.py .wye                         # 지금 설정 보기
python3 SKILL/scripts/profiles.py .wye --init manufacturing-ai  # 프로필 지정(다른 맞춤 값은 유지)
```

에이전트는 첫 실행 때 자료 폴더 이름·첫 문서로 고르고 이유를 한 줄로 알린다. 사람이 "이 프로젝트는 ○○야"라고 하면 바꾼다.

## 프로젝트 맞춤 (`.wye/config.json`)

```json
{
 "profile": "general",
 "language": "en",
 "triage": {"core": ["SRS", "화면설계"], "admin": ["견적"], "oldFolders": ["구버전"]},
 "signals": ["장애", "SLA"],
 "units": ["TPS", "ms"],
 "remove": {"triage.admin": ["경비"]},
 "caps": {"maxEntities": 90}
}
```

| 키 | 무엇 | 어디에 쓰임 |
|---|---|---|
| `language` | 결과 언어(`ko`/`en`). 인용은 늘 원문 그대로. `en`이면 분석 한 장 표시어·폴더(`Wye/Analysis/`)와 요약·질문지(`Summary.md`·`Questions.xlsx`)가 영어. 맵 화면 틀은 한국어 | 맵 내용·분석 한 장·요약·질문지 |
| `triage.core` | 이름에 들면 핵심 문서 | `convert.py --plan` |
| `triage.admin` | 이름에 들면 행정·양식으로 제외(`triage.strong`이 같이 들면 핵심 유지) | `convert.py --plan` |
| `triage.oldFolders` / `asideFolders` / `raw` | 예전 판 폴더 / 범위 밖·참고 폴더 / 녹취 원문 | `convert.py --plan` |
| `signals` | 먼저 읽을 조각을 고르는 신호어 | `outline.py` |
| `units` | 불일치 후보로 볼 숫자 단위 | `scan_conflicts.py` |
| `analysis.verdictTitle`·`approaches` | 분석 한 장의 판정 이름과 접근 목록 | 분석 한 장 양식 |
| `remove` | 기본 목록에서 뺄 낱말(`"triage.admin": [...]`) | 위 전부 |
| `caps` | 맵 상한(항목·목표·질문·제목 길이·불일치) | `check.py` |

낱말은 정규식 조각이다(`사업\\s*계획`처럼 띄어쓰기 허용 가능). 영문 낱말은 대소문자를 가리지 않고, 앞에 영문 글자가 붙으면 맞지 않는다(golden 속 old 방지).

## 새 업종 프로필 만들기
자주 쓰는 맞춤이 생기면 `_core/data/profiles/<이름>.json`에 `"extends": "general"`과 더할 값만 적는다. 목록은 기본값에 더해지고 한 값은 덮어쓴다.
