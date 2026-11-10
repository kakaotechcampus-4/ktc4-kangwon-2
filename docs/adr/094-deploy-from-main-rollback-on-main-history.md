# ADR-094: 배포는 main 머지로만 하고, 마이그레이션을 건너는 되감기는 main 이력에서도 찾는다

- 날짜: 2026-11-10
- 상태 — 채택 (073 보충)

## 맥락

[실측] `deploy.yml` 이 `push: [main, develop]` 에 돌았다. develop 에 머지되면 곧바로 운영에 나갔다.
2026-11-10 배포를 main 머지로만 하기로 했다.

[실측] ADR-073 「한계」: 「배포 브랜치가 develop 인 동안의 설계다. CI 의 B 와 deploy.sh 의 M 찾기가 둘 다 develop 의
first-parent 이력을 본다. `main` 에서 `main^1` 로 마이그레이션을 건너는 롤백은 거절된다.」
배포를 main 으로만 옮기면 직전 성공 배포는 develop→main 머지 커밋이다. develop 쪽 B(PR 머지 직전 develop 커밋)가 아니라서,
마이그레이션이 든 main 배포가 교체 뒤 실패하면 자동 롤백(ADR-078)이 판정에서 거절되고 종료 4(못 되돌림)로 끝난다.
develop 은 PR 을 하나씩 내보냈지만 main 은 여러 PR 을 한 번에 싣는다 — 마이그레이션이 끼는 배포가 대부분이 된다.

[실측] main 의 first-parent 이력은 develop 을 머지한 커밋이다(최근 #380 · #283 · #210 · #119 · #82 · #52 모두).
저장소는 merge commit 만 허용한다.

## 결정

1. **push 배포는 `main` 에서만 돈다**(`deploy.yml`). develop 머지는 운영에 나가지 않는다.
   손 배포(`workflow_dispatch`)는 그대로다 — 기본 `ref` 는 main.
2. **CI `backend (rollback compat)` 를 main 으로 가는 PR 에서도 돌린다.** 코드는 base(지금 main 끝 = 운영 코드),
   마이그레이션은 PR 머지 커밋의 것이다. develop 으로 가는 PR 은 그대로다.
3. **`deploy.sh` 의 `migration_step` 이 R 을 들여온 머지를 `origin/main` · `origin/develop` 두 first-parent 이력에서 찾는다.**

   | 상황 | 답 |
   |---|---|
   | 올릴 커밋이 R 을 선언한 파일을 가진다 | `upgrade` (그대로) |
   | 올릴 커밋이 main 쪽 B(R 을 들여온 develop→main 머지의 직전 main 커밋)다 | `skip` |
   | 올릴 커밋이 develop 쪽 B(R 을 들여온 PR 머지의 직전 develop 커밋)다 | `skip` (그대로) |
   | 둘 다 아니다 | `reject` — 이유에 main · develop 쪽 B 를 둘 다 적는다 |
   | main 도 develop 도 R 을 모른다 · 어느 한 이력이라도 읽지 못했다 | `reject` |

   읽지 못한 이력을 「모른다」로 넘기지 않는다. 넘기면 main 쪽이 깨진 채 develop 판정만으로 건너뛴다.
4. **GitHub 규칙은 바꾸지 않는다.** main 규칙(`main-protection`)은 운영진이 전 팀에 같은 내용으로 맞춘 것이다.

## 근거

- [판단] ADR-073 의 원칙(CI 가 시험한 코드로만 건너뛴다)을 그대로 지킨다. main 으로 가는 PR 의 base 는 머지 뒤 `M^1` 이고,
  main 배포가 성공해 왔으면 그것이 직전 성공 커밋(되돌릴 곳)이다. CI 가 시험한 B · deploy.sh 가 찾는 B · 되돌릴 곳이 한 커밋이다.
- [실측] `backend/tests/test_deploy_script.py` 의 임시 저장소에 main(P0 → N0 → N1, N1 이 리비전 b 를 들여온다)을 더했다.
  `migration_step N0 b` 는 `skip`, a0 · p0 · x 는 두 쪽 B 를 적고 거절, 둘 다 모르는 리비전은 거절, `origin/main` 이 없으면 거절.
  가짜 서버에서 N1 → N0 되감기는 `alembic` 없이 끝난다. 이 7개는 바꾸기 전 deploy.sh 에서 실패하고 바꾼 뒤 통과한다(73 passed).
- [실측] 2026-11-10 실제 이력에서 바꾼 `migration_step` 을 불렀다(origin/main `09c180a2` · origin/develop `eb361115`,
  DB 는 `6cf1f5e3ba44` 라고 치고). 지금 손 배포를 `ref: main` 으로 돌리면 `reject`(develop 쪽 B `e6ef8244` 로만 된다) —
  서버를 안 바꾸고 멈춘다. `e17dcaa2` 는 `upgrade`. develop→main 머지 N1 을 흉내 내 origin/main 을 옮기면
  옛 main `09c180a2` 는 `skip`(M = N1), N1 과 `e17dcaa2` 는 `upgrade`.
- [실측] main 에 있는 마이그레이션 파일 중 develop 이 고치거나 지운 것은 없다
  (`git diff --diff-filter=MDR origin/main origin/develop -- backend/alembic/versions` 빈 출력, 2026-11-10).
  첫 develop→main PR 에서 compat job 이 첫 단계(「이미 있는 마이그레이션을 고쳤다」)에서 멈추지 않는다.

## 대안

- **판정은 그대로 두고 한계만 적는다** — 마이그레이션이 든 main 배포마다 교체 뒤 실패가 사람 일이 된다(위 맥락).
- **main 이력만 본다** — 손 배포로 develop 커밋을 올릴 때 쓰던 develop 쪽 판정이 사라진다. 그 조합도 CI 가 시험했다.
- **main 에 필수 검사 규칙을 하나 더 만든다** — main 쪽 compat 이 막는 검사가 된다. 운영진이 맞춘 main 보호 위에 팀 규칙을 얹는 일이라 하지 않는다.
- **CI 결과를 배포에 넘긴다** — ADR-073 「대안」과 같은 이유로 하지 않는다.

## 결과

- develop 머지는 운영에 안 나간다. 운영은 develop→main 머지 때만 바뀐다. push 배포는 push 된 커밋의 `deploy.yml` 을 따르므로
  **이 결정의 PR 머지부터** 그렇다. main 쪽 파일은 다음 develop→main 머지 때 같이 바뀐다.
- 마이그레이션이 든 main 배포가 교체 뒤 실패해도 직전 main 으로 되돌린다(종료 3).
- develop→main PR 에도 compat job 이 돈다(마이그레이션이 바뀐 때만).
- `docs/deploy.md` 「되감을 때 (롤백)」 판정표를 이 결정에 맞췄다.

## 한계

- **main 쪽 compat 은 경고등이다.** main 규칙에 필수 검사가 없어 빨개도 머지된다. 머지하는 사람이 PR 에서 본다.
  빨간 채 머지되면 deploy.sh 는 CI 결과를 모른 채 그 조합으로 건너뛰기를 허용한다(ADR-073 의 develop 쪽과 같은 한계).
- **전환 직후 첫 main 배포는 직전 성공이 develop 커밋이다.** main 쪽 B(옛 main 끝)가 아니고, 되돌리기를 판정하는 것도
  그 커밋의 옛 deploy.sh 다(ADR-078 — 직전 성공 커밋 자신의 스크립트가 돈다). 이 결정의 PR 머지부터 첫 develop→main 머지까지
  마이그레이션이 든 PR 이 develop 에 안 들어오면, DB 리비전을 그 커밋이 알아서 평소대로 `upgrade` 로 되돌아간다.
  들어오면 그 배포의 자동 롤백은 거절될 수 있다.
- **첫 develop→main PR 의 compat 결과는 참고다.** base 가 2026-11-08 의 main(#380)이라 실제 되돌릴 곳(develop 커밋)과 다르다.
- **develop→main PR 둘이 겹치면 B 가 어긋날 수 있다.** main 규칙에 「브랜치를 최신으로」(strict)가 없다.
  CI 가 시험한 base 와 머지 때 main 끝이 다르면 deploy.sh 는 시험하지 않은 커밋을 B 로 찾는다.
- **main 쪽은 묶음 단위다.** N1 이 들여온 리비전이면 그중 어느 것에 DB 가 서 있어도 N0 로 건너뛴다. CI 는 N0 를 묶음 끝 스키마에서만
  시험했다. 중간 리비전에 닿으려면 develop 을 손으로 미리 올려 DB 가 묶음 중간에 서 있고, 그 뒤 N0 를 다시 올려야 한다 [판단: 드물다].
- **merge commit 전제**는 ADR-073 과 같다.
