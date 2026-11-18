"""Google Drive 링크 → 이 PC의 Drive for Desktop 경로. 인터넷에 접속하지 않음.

- 사용: python3 drive_locate.py "https://drive.google.com/drive/folders/<id>"
- macOS Drive for Desktop은 파일·폴더마다 확장 속성 com.google.drivefs.item-id#S에 Drive id를 둠 → 그 값으로 찾음
- 폴더 링크는 폴더만 훑음(파일보다 훨씬 적음). 찾으면 경로 한 줄 출력, 못 찾으면 exit 1과 안내
- Windows·Drive for Desktop 없음: 찾지 못함으로 끝냄. 스킬이 Drive 커넥터나 직접 경로로 넘어감
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import re
import sys
import time
from pathlib import Path

ATTR = b"com.google.drivefs.item-id#S"
# 훑기 시간 상한(초). 공유 드라이브가 크면 오래 걸려 멈춘 것처럼 보임
TIME_LIMIT = 60


def drive_id(link: str) -> str:
    """링크에서 Drive id. folders/<id>, /d/<id>, ?id=<id>, 또는 id만."""
    for pattern in (r"/folders/([\w-]{10,})", r"/d/([\w-]{10,})", r"[?&]id=([\w-]{10,})"):
        found = re.search(pattern, link)
        if found:
            return found.group(1)
    if re.fullmatch(r"[\w-]{10,}", link.strip()):
        return link.strip()
    raise SystemExit("Drive 링크에서 id를 찾지 못함")


def reader():
    """경로 → Drive id 읽기 함수. macOS libc getxattr을 ctypes로 부름(프로세스를 띄우지 않아 빠름)."""
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    getxattr = libc.getxattr
    getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    getxattr.restype = ctypes.c_ssize_t
    buf = ctypes.create_string_buffer(256)

    def read(path: str) -> str:
        size = getxattr(os.fsencode(path), ATTR, buf, 256, 0, 0)
        return buf.raw[:size].decode("utf-8", "replace") if size > 0 else ""
    return read


def roots() -> list[Path]:
    """Drive for Desktop의 내 드라이브·공유 드라이브 폴더들."""
    base = Path.home() / "Library" / "CloudStorage"
    found = []
    for account in sorted(base.glob("GoogleDrive-*")):
        found += [p for p in account.iterdir() if p.is_dir()]
    return found


def locate(target: str) -> Path | None:
    """id가 같은 폴더·파일을 넓이 우선으로 찾음. 시간 상한을 넘으면 None."""
    read = reader()
    started = time.monotonic()
    queue = list(roots())
    while queue:
        if time.monotonic() - started > TIME_LIMIT:
            return None
        folder = queue.pop(0)
        if read(str(folder)) == target:
            return folder
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                queue.append(Path(entry.path))
            elif read(entry.path) == target:
                return Path(entry.path)
    return None


def main() -> int:
    """찾은 경로를 출력. 못 찾으면 이유와 다음 길."""
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    if sys.platform != "darwin" or not roots():
        print("Drive 링크로 폴더를 찾는 기능은 macOS의 Drive for Desktop에서만 됨 — Drive 커넥터를 쓰거나 폴더 경로를 알려 주십시오(Windows: doctor.py가 보여 주는 Drive 위치에서 경로 복사)")
        return 1
    target = drive_id(sys.argv[1])
    path = locate(target)
    if path is None:
        print(f"동기화된 폴더에서 {target}을 찾지 못함 — 그 폴더를 Drive for Desktop에서 '오프라인/스트리밍'으로 보이게 하거나 Drive 커넥터를 쓰십시오")
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
