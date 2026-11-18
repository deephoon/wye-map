---
name: wye-map
description: 프로젝트 자료(파일·로컬 폴더·Google Drive 링크의 회의록·사업계획서·정의서)를 읽어 근거가 붙은 지식 맵을 만들고, 맵으로 문제를 분석한다 — 문제마다 현상·지표·현재 판단·데이터 고리의 빈 자리, 영향 범위, 해결 방향 판정(가능/조건부/지금은 불가 — 제조 AI 프로필이면 AI 적용 판정). 업종 무관, 한국어·영어 자료. "맵 만들어 줘", "이 폴더(드라이브) 자료 분석해 줘", "불량 문제 분석해 줘", "이게 바뀌면 뭐가 영향받아?", "자료 근거로 답해 줘"에 쓴다.
---

# Wye 맵 분석

`SKILL` = 이 파일이 있는 폴더의 절대 경로. 결과는 작업 폴더의 `Wye/`(볼 것)와 `.wye/`(재료).

| 요청 | 읽을 문서 |
|---|---|
| 자료 넣기(파일·폴더·Drive 링크·"다시 읽어 줘") | `SKILL/shared/sources.md` |
| 처음 쓸 때·도구 점검("설치 확인해 줘") | `python3 SKILL/scripts/doctor.py` |
| 업종·회사 맞춤("이 프로젝트는 IT 구축이야", 낱말·단위 추가) | `SKILL/shared/profiles.md` |
| 맵 만들기·갱신 | `SKILL/shared/map.md` |
| 문제 분석·영향 범위·AI 적용 판정 | `SKILL/references/analyze.md` (맵이 없으면 맵부터) |
| 자료 근거로 답하기·위키 | `SKILL/references/wiki-and-ask.md` |
| 정합성 확인("맞게 썼는지 봐 줘", 자료끼리 어긋난 곳) | `python3 SKILL/scripts/check.py .wye` → `python3 SKILL/scripts/verify.py .wye` → `render.py` 후 화면의 정합성 보기 |

## 언제나
- 스크립트는 `SKILL/scripts/`, 공용 문서는 `SKILL/shared/`에 있다. 손으로 대신 만들지 말고 스크립트를 돌린다. 안 보이거나 실패하면 `python3 SKILL/scripts/doctor.py`로 점검하고 결과를 사람에게 보인다.
- 첫 줄은 결론. 문장마다 `확인`(원문 인용)·`추론`(무엇에서)·`미확인`(누구에게 물을지).
- 근거 없는 내용을 쓰지 않는다. 모르는 칸은 비우고 질문으로 남긴다.
- 사람이 정할 것은 한 번에 묻되 선택지·추천·이유를 붙인다.
- 하위 에이전트를 띄우지 않는다(사람이 요청할 때만). 고객 원문을 작업 폴더 밖으로 옮기지 않는다.
- 끝 보고는 세 줄: 한 일 · 열 파일(`Wye/…`) · 다음에 할 말 예시(wye-requirements·wye-aas가 설치돼 있으면 요구사항·AAS로 이어 가기).
