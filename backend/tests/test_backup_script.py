"""DB 백업 스크립트 (scripts/backup.sh · #185 3번).

백업이 실패했는데 백업 파일이 남으면 「백업이 있다」고 믿게 된다 — 복구하려는 순간에야 안다.
그래서 **성공했을 때만 `ssuksak_*.sql.gz` 가 남는지**를 본다.

진짜 docker 대신 가짜 `docker` 를 PATH 앞에 둔다. `pg_dump` 가 무엇을 내놓을지는
`FAKE_DUMP` 로 고른다.
"""

import gzip
import os
import stat
import subprocess
import time
from pathlib import Path

import pytest

BACKUP_SH = Path(__file__).resolve().parents[2] / "scripts" / "backup.sh"

HEADER = "--\n-- PostgreSQL database dump\n--\n\n"
# 파이프 버퍼(64KB)보다 크게 — 머리글만 읽고 끊는 쪽이 SIGPIPE 로 죽지 않는지도 같이 본다.
BODY = "COPY public.t (id) FROM stdin;\n" + "".join(f"{i}\n" for i in range(50_000)) + "\\.\n"
# 요즘 pg_dump 는 끝 표시 뒤에도 줄을 붙인다.
FOOTER = "\n--\n-- PostgreSQL database dump complete\n--\n\n\\unrestrict abc\n"

FAKE_DOCKER = """#!/bin/sh
case "$*" in
  "compose ps") exit 0 ;;
  *pg_dump*)
    case "$FAKE_DUMP" in
      ok)    cat "$FAKE_DIR/ok.sql" ;;
      fail)  echo "service db is not running" >&2; exit 1 ;;
      empty) ;;
      cut)   cat "$FAKE_DIR/cut.sql" ;;
    esac ;;
esac
"""


@pytest.fixture
def run_backup(tmp_path):
    """가짜 docker 로 backup.sh 를 돌리고 (종료 코드, stderr, 백업 폴더) 를 준다."""
    fake = tmp_path / "bin"
    fake.mkdir()
    docker = fake / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "ok.sql").write_text(HEADER + BODY + FOOTER)
    (tmp_path / "cut.sql").write_text(HEADER + BODY[: len(BODY) // 2])

    deploy = tmp_path / "deploy"  # .env 가 없다 — S3 설정을 읽어 오지 않는다
    deploy.mkdir()
    backup_dir = tmp_path / "backup"

    def run(dump: str):
        env = {
            **os.environ,
            "PATH": f"{fake}{os.pathsep}{os.environ['PATH']}",
            "DEPLOY_PATH": str(deploy),
            "BACKUP_DIR": str(backup_dir),
            # 비워 둬야 한다. 물려받으면 테스트가 진짜 S3 로 올린다.
            "BACKUP_S3_URI": "",
            "FAKE_DUMP": dump,
            "FAKE_DIR": str(tmp_path),
        }
        done = subprocess.run(
            ["bash", str(BACKUP_SH)], env=env, capture_output=True, text=True, timeout=60
        )
        return done.returncode, done.stderr, backup_dir

    return run


def test_정상_덤프는_백업으로_남는다(run_backup):
    code, stderr, backup_dir = run_backup("ok")

    assert code == 0, stderr
    files = list(backup_dir.iterdir())
    assert len(files) == 1
    assert files[0].name.startswith("ssuksak_") and files[0].name.endswith(".sql.gz")
    assert gzip.decompress(files[0].read_bytes()).decode().endswith(FOOTER)


def test_강제_종료로_남은_임시_파일은_정리된다(run_backup, tmp_path):
    # trap 이 못 도는 강제 종료 · 재부팅이면 임시 파일이 남는다
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    stale = backup_dir / ".ssuksak_20261001_031500.sql.gz.part"
    stale.write_bytes(b"x")
    two_hours_ago = time.time() - 2 * 3600
    os.utime(stale, (two_hours_ago, two_hours_ago))
    running = backup_dir / ".ssuksak_20261021_031500.sql.gz.part"  # 지금 도는 다른 백업
    running.write_bytes(b"x")

    code, stderr, _ = run_backup("ok")

    assert code == 0, stderr
    assert not stale.exists()
    assert running.exists()


@pytest.mark.parametrize(
    ("dump", "why"),
    [
        ("fail", "덤프나 압축 저장이 실패했다"),  # db 컨테이너가 멈춘 날
        ("empty", "덤프가 비었거나 깨졌다"),  # 명령은 0 으로 끝났는데 아무것도 안 나왔다
        ("cut", "덤프가 끝까지 안 쓰였다"),  # 명령은 0 으로 끝났는데 도중에 끊겼다
    ],
)
def test_실패한_덤프는_파일을_남기지_않는다(run_backup, dump, why):
    code, stderr, backup_dir = run_backup(dump)

    assert code == 1
    assert "backup failed" in stderr and why in stderr
    # 임시 파일(.part)까지 — 숨김 파일도 남으면 안 된다
    assert list(backup_dir.iterdir()) == []
