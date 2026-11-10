"""서버에서 손으로 돌리는 스크립트 — HTTPS 첫 발급 · 백업 복구 확인.

`scripts/https-setup.sh` · `scripts/restore-check.sh`.

진짜 docker · sudo 대신 가짜를 PATH 앞에 둔다. 가짜 docker 는 받은 인자를 한 줄씩 적고,
그 앞에 sudo 로 불렸는지(`sudo`) 아닌지(`-`)를 붙인다.
"""

import gzip
import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

FAKE_DOCKER = """#!/bin/sh
echo "${VIA_SUDO:--} $*" >> "$FAKE_LOG"
# sudo 없이는 데몬에 닿지 못하는 계정을 흉내 낸다 (NEED_SUDO=1).
if [ "$NEED_SUDO" = 1 ] && [ -z "$VIA_SUDO" ]; then exit 1; fi
# 컨테이너 안 test -f 는 FILES_IN_VOLUME 이 1 이면 「있다」.
case "$*" in *"test -f"*) [ "$FILES_IN_VOLUME" = 1 ]; exit $? ;; esac
# psql 로 붓는 줄은 표준 입력을 다 읽는다.
case "$*" in *ON_ERROR_STOP*) cat > /dev/null ;; esac
exit 0
"""
FAKE_SUDO = '#!/bin/sh\n[ "$1" = -n ] && shift\nVIA_SUDO=sudo exec "$@"\n'
QUIET = "#!/bin/sh\nexit 0\n"


@pytest.fixture
def run(tmp_path):
    fake = tmp_path / "bin"
    fake.mkdir()
    for name, body in {
        "docker": FAKE_DOCKER,
        "sudo": FAKE_SUDO,
        "getent": QUIET,
        "curl": QUIET,
        "sleep": QUIET,
    }.items():
        p = fake / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "docker.log"

    def go(script: str, *args: str, **env: str):
        result = subprocess.run(
            ["bash", str(ROOT / "scripts" / script), *args],
            env={
                **os.environ,
                "PATH": f"{fake}{os.pathsep}{os.environ['PATH']}",
                "FAKE_LOG": str(log),
                "DEPLOY_PATH": str(tmp_path),
                **env,
            },
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result, log.read_text() if log.exists() else ""

    return go


def test_https_진짜_인증서가_볼륨에_있으면_임시_인증서로_덮지_않는다(run):
    """인증서는 도커 볼륨 안에만 있다. 호스트에서 보면 늘 「없다」라 진짜를 1일짜리로 덮었다."""
    result, log = run("https-setup.sh", EMAIL="ops@example.com", FILES_IN_VOLUME="1")

    assert result.returncode == 0, result.stderr
    assert "openssl" not in log
    assert "--force-renewal" in log  # certbot 이 관리하는 인증서로 판정했다


def test_https_볼륨에_인증서가_없으면_임시_인증서를_먼저_깐다(run):
    result, log = run("https-setup.sh", EMAIL="ops@example.com", FILES_IN_VOLUME="0")

    assert result.returncode == 0, result.stderr
    assert "openssl" in log


def test_restore_check_는_sudo_가_필요한_계정이면_붓는_줄도_sudo_로_간다(run, tmp_path):
    """dc 를 sudo 로 골라 두고 붓는 줄만 그냥 docker 를 써서, 멀쩡한 백업이 「복구 중 오류」였다."""
    dump = tmp_path / "ssuksak_x.sql.gz"
    dump.write_bytes(gzip.compress(b"SELECT 1;\n"))

    result, log = run("restore-check.sh", str(dump), NEED_SUDO="1")

    assert "복구 중 오류" not in result.stderr
    pour = [line for line in log.splitlines() if "ON_ERROR_STOP" in line]
    assert pour, log
    assert all(line.startswith("sudo ") for line in pour), pour
