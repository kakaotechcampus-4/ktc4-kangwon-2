"""인증서·복원 회귀: sudo/docker/네트워크는 전부 스텁이며 실제 자원에 닿지 않는다."""

import gzip
import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture
def run_script(tmp_path):
    fake = tmp_path / "bin"
    fake.mkdir()
    stubs = {
        "docker": """#!/bin/sh
echo "RAW $*" >> "$TRACE"
[ "$DIRECT" = 1 ] || exit 1
exec "$FAKE_BIN/sudo" docker "$@"
""",
        "sudo": """#!/bin/sh
echo "SUDO $*" >> "$TRACE"
case "$*" in
  *"test -f /etc/letsencrypt/renewal/"*) exit "$MANAGED" ;;
  *"test -f /etc/letsencrypt/live/"*) exit "$CERT_PRESENT" ;;
  *--force-renewal*) exit 7 ;;
  *"string_agg(tablename"*) echo "centers users" ;;
  *"SELECT version_num"*) echo "fixture_head" ;;
  *"SELECT 'centers='"*) echo "centers=1 users=1 plans=0 documents=0" ;;
  *"-d fixture_restore_check -v ON_ERROR_STOP=1 -q") cat >/dev/null ;;
esac
exit 0
""",
        "getent": '#!/bin/sh\necho "192.0.2.1 fixture.invalid"\n',
        "curl": '#!/bin/sh\necho "192.0.2.1"\n',
        "sleep": "#!/bin/sh\nexit 0\n",
    }
    for name, content in stubs.items():
        path = fake / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)
    dump = tmp_path / "synthetic.sql.gz"
    dump.write_bytes(gzip.compress(b"-- synthetic test fixture\n"))
    trace = tmp_path / "trace.log"

    def run(script, *, managed=False, cert_present=False, direct=False):
        env = {
            **os.environ,
            "PATH": f"{fake}{os.pathsep}{os.environ['PATH']}",
            "FAKE_BIN": str(fake),
            "TRACE": str(trace),
            "DEPLOY_PATH": str(tmp_path),
            "DOMAIN": "fixture.invalid",
            "EMAIL": "fixture@example.invalid",
            "CHECK_DB": "fixture_restore_check",
            "LIVE_DB": "fixture_live",
            "MANAGED": "0" if managed else "1",
            "CERT_PRESENT": "0" if cert_present else "1",
            "DIRECT": "1" if direct else "0",
        }
        args = [str(dump)] if script == "restore-check.sh" else []
        result = subprocess.run(
            ["bash", str(SCRIPTS / script), *args],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result, trace.read_text()

    return run


def test_갱신_실패해도_관리중인_인증서를_임시본으로_덮거나_지우지_않는다(run_script):
    result, trace = run_script("https-setup.sh", managed=True, cert_present=True)
    assert result.returncode == 7, result.stderr
    assert "--force-renewal" in trace
    assert "openssl req" not in trace
    assert "rm -rf" not in trace


@pytest.mark.parametrize("cert_present", [False, True])
def test_최초_설정은_볼륨에_인증서가_없을_때만_임시본을_만든다(run_script, cert_present):
    result, trace = run_script("https-setup.sh", cert_present=cert_present)
    assert result.returncode == 0, result.stderr
    assert ("openssl req" in trace) is not cert_present


@pytest.mark.parametrize("direct", [False, True])
def test_복원_파이프도_선택한_docker_권한으로_끝까지_실행한다(run_script, direct):
    result, trace = run_script("restore-check.sh", direct=direct)
    assert result.returncode == 0, result.stderr
    assert "restore-check ok" in result.stdout
    restore = "compose exec -T db psql -U ssuksak -d fixture_restore_check -v ON_ERROR_STOP=1 -q"
    assert f"SUDO docker {restore}" in trace
    assert (f"RAW {restore}" in trace) is direct
