# Windows용 설치: 스킬을 Claude Code(%USERPROFILE%\.claude\skills)와 Codex(%USERPROFILE%\.codex\skills)에 폴더 연결(junction)로 설치함.
# 관리자 권한·개발자 모드 없이 됨(junction). 이미 같은 이름의 진짜 폴더가 있으면 덮지 않음.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Skills = @("wye-map", "wye-requirements", "wye-aas")
# 공용 재료(_core)를 스킬 폴더에 실제 파일로 복사(git이 받은 심볼릭 링크·글자 파일을 대체)
python (Join-Path $Root "sync_core.py")

foreach ($dest in @("$env:USERPROFILE\.claude\skills", "$env:USERPROFILE\.codex\skills")) {
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  foreach ($skill in $Skills) {
    if (-not (Test-Path (Join-Path $Root $skill))) { continue }
    $target = Join-Path $dest $skill
    if (Test-Path $target) {
      $existing = Get-Item $target
      if ($existing.LinkType -eq "Junction") { Remove-Item $target } else { Write-Host "건너뜀: $target 이 이미 있음(연결 아님)"; continue }
    }
    New-Item -ItemType Junction -Path $target -Target (Join-Path $Root $skill) | Out-Null
    Write-Host "설치: $target"
  }
}
python (Join-Path $Root "_core\scripts\doctor.py")
