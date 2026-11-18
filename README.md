# wye-map — 근거 맵 스킬 (Claude Code · Codex)

프로젝트 자료 폴더(회의록·계획서·제안서·요구사항·보고서)를 읽어 **원문 근거가 붙은 지식 맵**을 만들고, 문제를 분석합니다.
서버·로그인 없이 내 PC에서 돌고, 말 한마디로 씁니다. 업종 무관(제조 AI 프리셋 포함), 한국어·영어 자료, macOS·Windows.

| 이렇게 말하면 | 나오는 것 (`Wye/` 폴더) |
|---|---|
| "이 폴더 자료로 맵 만들고 분석해 줘" · "○○ 문제 분석해 줘" · "이게 바뀌면 뭐가 영향받아?" | `맵.html`(문제 고리·연결·우주·목록·정합성 보기) · `요약.md` · `질문지.xlsx` · `분석/<문제>.md` · `위키/` |

- 모든 인용은 원문과 글자 단위로 대조합니다(지어낸 문장은 검사에서 걸림). 문서끼리 어긋난 숫자·범위는 정합성 보기에 모입니다.
- 예전 판·중복·행정 서류는 이유와 함께 빼고 읽습니다. 자료 폴더 안에는 아무것도 쓰지 않습니다.
- 문제마다 현상 → 지표 → 현재 판단 → 데이터 → 요구사항 → 목표 고리의 빈 자리를 찾아 "물을 것"으로 돌려줍니다.

## 설치

macOS·Linux:
```sh
git clone https://github.com/deephoon/wye-map.git ~/dev/wye-map && ~/dev/wye-map/install.sh
pipx install 'markitdown[pdf,docx,pptx,xlsx]'   # pdf·Office 문서를 읽을 때
```

Windows(PowerShell):
```powershell
git clone https://github.com/deephoon/wye-map.git $HOME\dev\wye-map; & $HOME\dev\wye-map\install.ps1
pipx install "markitdown[pdf,docx,pptx,xlsx]"
```

설치가 끝나면 점검표가 나옵니다(`python3 _core/scripts/doctor.py`로 다시 볼 수 있음). Claude Code에서는 `/wye-map <폴더 경로> 분석해 줘`,
Codex에서는 `$wye-map …`처럼 부릅니다.

## 맞춤
처음 쓸 때 에이전트가 자료를 보고 프로필(`general` 업종 무관 / `manufacturing-ai` 제조 AI)을 고르고 알려 줍니다.
문서 이름 규칙·뺄 서류·단위·결과 언어(`"language": "en"`)는 작업 폴더의 `.wye/config.json`으로 바꿉니다 — `_core/docs/profiles.md`.

## 주의
`Wye/`·`.wye/`에는 자료 원문 조각이 들어 있습니다. 공개 저장소나 외부로 올리지 마십시오.

## 개발
정본은 `_core/`입니다. 고친 뒤 `python3 sync_core.py`로 스킬 폴더에 복사합니다. 시험: `python3 -m unittest discover -s _core/tests`.
