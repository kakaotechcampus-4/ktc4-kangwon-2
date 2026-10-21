"""운영 서버 점검 스크립트 (scripts/server-check.sh · #185 5번).

점검 결과를 이슈에 붙이는 일이 잦아서 **비밀 값이 안 찍히는지**가 제일 중요하다.
그러면서도 고장을 가리면 안 된다 — 2026-10-21 에 S3 백업이 한 번도 안 갔는데, 점검이
cron 줄의 `BACKUP_S3_URI` 와 로그의 `aws: command not found` 를 둘 다 숨겨서 못 봤다.

스크립트를 `SERVER_CHECK_LIB=1` 로 source 해서 함수 하나씩 부른다. 바깥 명령(git · timeout ·
curl · sudo)은 가짜 실행 파일을 PATH 앞에 둬서 바꾼다 — 셸 함수로 바꾸면 `timeout git …` 처럼
바깥 명령을 거치는 호출이 진짜 git 을 부른다.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

SERVER_CHECK_SH = Path(__file__).resolve().parents[2] / "scripts" / "server-check.sh"

FAKES = {
    # timeout <초> 명령… → 명령… (시간 제한 없이 그대로)
    "timeout": '#!/bin/sh\nshift\nexec "$@"\n',
    "git": """#!/bin/sh
case "$*" in
  *"rev-parse HEAD"*) echo "$FAKE_HEAD" ;;
  *ls-remote*)
    printf '%s\\trefs/heads/main\\n' "$FAKE_MAIN"
    printf '%s\\trefs/heads/develop\\n' "$FAKE_DEV" ;;
esac
""",
    "curl": """#!/bin/sh
case "$FAKE_HTTP" in
  down) printf 000; exit 7 ;;
  *) printf '%s' "$FAKE_HTTP" ;;
esac
""",
    # sudo -n tail … /var/log/ssuksak-backup.log → 가짜 로그의 끝
    "sudo": """#!/bin/sh
[ "$1" = -n ] && shift
[ "$1" = tail ] && exec tail -n 6 "$FAKE_LOG"
exec "$@"
""",
}


@pytest.fixture
def call(tmp_path):
    """server-check.sh 의 함수를 불러 stdout 을 준다."""
    fake = tmp_path / "bin"
    fake.mkdir()
    for name, body in FAKES.items():
        p = fake / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    deploy = tmp_path / "deploy"
    deploy.mkdir()

    def run(body: str, **env_extra: str) -> str:
        env = {
            **os.environ,
            "PATH": f"{fake}{os.pathsep}{os.environ['PATH']}",
            "SERVER_CHECK_LIB": "1",
            "DEPLOY_PATH": str(deploy),
            **env_extra,
        }
        proc = subprocess.run(
            ["bash", "-c", f'source "{SERVER_CHECK_SH}"\n{body}'],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        return proc.stdout

    run.deploy = deploy
    run.tmp = tmp_path
    return run


BACKUP = "/home/ubuntu/ktc4-kangwon-2/scripts/backup.sh"


def test_cron은_s3_주소만_보이고_다른_값은_숨긴다(call):
    (call.deploy / ".env").write_text(
        "POSTGRES_PASSWORD=pw-should-not-print\nBACKUP_S3_URI=s3://from-env/backup\n"
    )
    cron = "\n".join(
        [
            "root\tMAILTO=ops@example.com",
            # 값에 pg_dump 가 들어 있어도 · = 앞뒤에 공백이 있어도 변수 줄이다
            "root\tPGPASSWORD=pg_dump-secret",
            "root\t  DB_PASS = pg_dump-spaced-secret",
            "root\tWEIRD-NAME=weird-secret",
            "root\tBACKUP_S3_URI = s3://var-line/backup",
            # cron 은 숫자 · * 로 시작하는 이름도 받는다 — 작업 줄로 잘못 나뉘어도 값은 안 나온다
            "root\t1PASSWORD=pg_dump-digit-secret",
            "root\t*STAR=pg_dump-star-secret",
            f"root\t15 18 * * * BACKUP_S3_URI=s3://bucket-a/backup SECRET_TOKEN=tok-secret {BACKUP}"
            " >> /var/log/ssuksak-backup.log 2>&1",
            # 따옴표 안 공백 · ; 뒤에 붙은 다른 변수
            f'root\t0 0 * * * TOKEN="prefix BACKUP_S3_URI=quoted-secret" {BACKUP}',
            f"root\t0 1 * * * BACKUP_S3_URI=s3://bucket-c;PGPASSWORD=semicolon-secret {BACKUP}",
            "root\t0 * * * * /usr/bin/true",
        ]
    )
    out = call('show_cron "$CRON"', CRON=cron)

    assert "root  15 18 * * *  → scripts/backup.sh  · BACKUP_S3_URI=s3://bucket-a/backup" in out
    assert "root  0 1 * * *  → scripts/backup.sh  · BACKUP_S3_URI=s3://bucket-c\n" in out
    assert "root: 변수 줄 BACKUP_S3_URI=s3://var-line/backup" in out
    assert "BACKUP_S3_URI=s3://from-env/backup" in out
    for name in ("MAILTO", "PGPASSWORD", "DB_PASS"):
        assert f"root: 변수 줄 {name}\n" in out
    assert "이름 꼴이 아니다" in out
    for secret in (
        "tok-secret",
        "ops@example.com",
        "pg_dump-secret",
        "pg_dump-spaced-secret",
        "weird-secret",
        "pg_dump-digit-secret",
        "pg_dump-star-secret",
        "quoted-secret",
        "semicolon-secret",
        "pw-should-not-print",
    ):
        assert secret not in out
    assert "root: 그 밖의 줄 1개" in out


def test_작업_줄로_잘못_나뉜_변수_줄은_통째로_가린다(call):
    # 숫자로 시작하는 이름 + 따옴표 안 공백 — 시스템 crontab 이면 여섯째 낱말이 사용자 자리에 온다
    cron = '/etc/crontab\t1PASSWORD="pg_dump alpha beta gamma delta very-secret-token tail"'
    out = call('show_cron "$CRON"', CRON=cron)

    assert "very-secret-token" not in out
    assert "alpha" not in out
    assert "/etc/crontab  ? (cron 작업 줄 꼴이 아니다" in out


def test_s3_꼴이_아닌_값은_찍지_않는다(call):
    (call.deploy / ".env").write_text("BACKUP_S3_URI=not-s3-env-secret\n")
    out = call('show_cron "$CRON"', CRON="root\tBACKUP_S3_URI=not-s3-var-secret")

    assert "not-s3-env-secret" not in out
    assert "not-s3-var-secret" not in out
    assert out.count("s3:// 꼴이 아니다") == 2


def test_시스템_crontab_은_사용자_칸을_건너뛰고_변수를_읽는다(call):
    cron = (
        "/etc/cron.d/backup\t  15 18 * * * root BACKUP_S3_URI=s3://bucket-b/backup "
        "/home/ubuntu/ktc4-kangwon-2/scripts/backup.sh"
    )
    out = call('show_cron "$CRON"', CRON=cron)

    assert "/etc/cron.d/backup  15 18 * * *  (root)  → scripts/backup.sh" in out
    assert "BACKUP_S3_URI=s3://bucket-b/backup" in out


def test_백업_로그는_고르지_않고_끝_줄을_160자까지_보여준다(call):
    log = call.tmp / "backup.log"
    long_line = "x" * 200
    log.write_text(
        "2026-10-21T03:15:02+00:00 backup ok /home/ubuntu/backup/a.sql.gz (28K)\n"
        "/home/ubuntu/ktc4-kangwon-2/scripts/backup.sh: line 72: aws: command not found\n"
        f"{long_line}\n"
    )
    out = call("show_backup_log", FAKE_LOG=str(log))

    assert "aws: command not found" in out
    assert "x" * 160 in out
    assert "x" * 161 not in out


@pytest.mark.parametrize(
    ("head", "expect"),
    [
        ("aaaaaaa1", "OK    서버 소스 aaaaaaa = GitHub main"),
        ("bbbbbbb2", "OK    서버 소스 bbbbbbb = GitHub develop"),
        ("ccccccc3", "--    서버 소스 ccccccc — main aaaaaaa · develop bbbbbbb 어느 끝과도 다르다"),
    ],
)
def test_서버_소스는_main_이나_develop_끝이면_통과다(call, head, expect):
    out = call(
        'check_commit; echo "fails=$fails"',
        FAKE_HEAD=head,
        FAKE_MAIN="aaaaaaa1",
        FAKE_DEV="bbbbbbb2",
    )

    assert expect in out
    assert "fails=0" in out


@pytest.mark.parametrize(
    ("http", "expect"),
    [
        ("200", "OK    앱 준비됨 — /health/ready 200"),
        ("503", "FAIL  앱 준비 안 됨 — /health/ready 503"),
        ("down", "FAIL  앱 준비 안 됨 — /health/ready 연결 안 됨"),
    ],
)
def test_앱이_준비_안_되면_실패다(call, http, expect):
    out = call("check_ready", FAKE_HTTP=http)

    assert expect in out
