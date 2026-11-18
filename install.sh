#!/bin/sh
# 스킬을 Claude Code(~/.claude/skills)와 Codex(~/.codex/skills)에 링크로 설치함.
# 이 저장소를 가리키던 옛 링크(wye-project·aas-datasource-structuring)는 지움.
# 이미 같은 이름의 진짜 폴더가 있으면 덮지 않고 알림. 지우기: 같은 경로의 링크를 rm
set -eu
ROOT=$(cd "$(dirname "$0")" && pwd)
# 공용 재료(_core)를 스킬 폴더에 실제 파일로 복사(링크는 파일 찾기 도구에 안 보여 에이전트가 스크립트를 못 찾음)
python3 "$ROOT/sync_core.py"
SKILLS="wye-map wye-requirements wye-aas"
for HOME_DIR in "$HOME/.claude/skills" "$HOME/.codex/skills"; do
  mkdir -p "$HOME_DIR"
  for OLD in wye-project aas-datasource-structuring; do
    LINK="$HOME_DIR/$OLD"
    # 이 저장소를 가리키는 링크만 지움. 다른 곳의 같은 이름은 건드리지 않음
    if [ -L "$LINK" ] && case "$(readlink "$LINK")" in "$ROOT"/*) true;; *) false;; esac; then
      rm "$LINK" && echo "옛 링크 지움: $LINK"
    fi
  done
  for SKILL in $SKILLS; do
    [ -d "$ROOT/$SKILL" ] || continue
    TARGET="$HOME_DIR/$SKILL"
    if [ -L "$TARGET" ]; then
      ln -sfn "$ROOT/$SKILL" "$TARGET"
    elif [ -e "$TARGET" ]; then
      echo "건너뜀: $TARGET 이 이미 있음(링크 아님). 직접 확인하십시오."
      continue
    else
      ln -s "$ROOT/$SKILL" "$TARGET"
    fi
    echo "설치: $TARGET"
  done
done
python3 "$ROOT/_core/scripts/doctor.py" || true
