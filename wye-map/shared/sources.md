# 자료 입구 — 파일·로컬 폴더·Google Drive 링크

`SKILL` = 스킬 폴더 절대 경로. **작업 폴더** = 결과(`Wye/`)와 재료(`.wye/`)를 두는 곳.

## 작업 폴더 정하기
- 사람이 지금 폴더에서 "이 폴더"라고 하면: 지금 폴더가 자료이자 작업 폴더.
- 다른 폴더나 Drive를 가리키면: 작업 폴더는 지금 폴더. 지금 폴더가 그 자료 폴더 안이면 `~/Wye/<프로젝트 이름>`을 만들어 쓴다.
- **자료 폴더 안에는 아무것도 만들지 않는다.** 고객 공유 폴더·Drive 동기화 폴더에 결과가 올라가는 일을 막기 위함. `convert.py`도 결과 폴더가 자료 폴더 안이면 멈춘다.

## 입구별로
| 사람이 준 것 | 할 일 |
|---|---|
| 지금 폴더 | `python3 SKILL/scripts/convert.py .` |
| 로컬 폴더 경로(여럿 가능) | `python3 SKILL/scripts/convert.py --src "<경로1>" --src "<경로2>" --work "<작업 폴더>"` |
| Google Drive 링크(폴더·파일) | 아래 순서 |
| (모든 입구 공통) | 기본으로 예전 판·같은 문서 중복·행정 서류는 빼고 변환(`- 뺌` 줄에 이유). 전부 읽으려면 `--use all` |
| 파일이 많은 폴더(30개 넘음) | 같은 명령에 `--plan` → 표를 보이고 한 번 묻기 → `--use plan` (예전 판·중복·행정 서류가 이유와 함께 빠짐, 선택은 기억됨) |
| "다시 읽어 줘" | `python3 SKILL/scripts/convert.py --work "<작업 폴더>"` — 지난번 입구와 고르기(`.wye/project.json`)대로 다시 훑고 바뀐 파일만. 새 파일은 자동 분류 |

## Google Drive 링크
1. **이 PC의 Drive for Desktop에서 찾기** (먼저, 인터넷 안 씀, macOS만 — Windows는 `doctor.py`가 보여 주는 Drive 위치에서 사람이 경로를 복사해 줌): `python3 SKILL/scripts/drive_locate.py "<링크>"` → 경로가 나오면 그 경로를 `--src`로. 파일 링크면 그 파일이 든 폴더가 아니라 파일 하나만 쓰도록 임시 폴더 대신 그 파일의 폴더를 입구로 주고, 읽을 문서를 그 파일로 한정한다.
2. **Drive 커넥터(MCP)가 붙어 있으면** (Claude Code의 Google Drive 연결 등): 폴더 안 파일 목록을 읽고, 작업 폴더의 `.wye/inbox/drive/<폴더 이름>/`에 내려받는다. Google 문서·시트·슬라이드는 docx·xlsx·pdf로 내보내 받는다. 받은 폴더를 `--src`로. 파일마다 수정 시각을 `.wye/inbox/drive/manifest.json`에 적어 다음에는 바뀐 것만 받는다.
3. **둘 다 안 되면** 한 줄로 멈춘다: "Drive for Desktop으로 동기화하거나, Drive 연결을 켜거나, 폴더를 내려받아 경로를 알려 주십시오." 링크를 웹으로 긁지 않는다(권한·DRM 우회 금지).

## 읽지 못한 파일
`convert.py` 출력의 `!` 줄을 그대로 사람에게 보인다: 크기 초과, 한글 문서(hwp — PDF로 저장), Google 문서 바로가기(.gdoc — 2번 경로나 다운로드), markitdown 없음(설치 한 줄), DRM.
