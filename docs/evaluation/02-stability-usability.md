# 02 · 안정성과 사용성

**멘토 심사 기준(기술·개발 중심) ② 완성도·안정성·사용성 — 10점**

> 오류·끊김 없이 안정적으로 동작하고, 화면 흐름·속도·편의까지 다듬어 완성도 있게 쓸 수 있는가

---

## 안 죽는가

- 살았는지와 **쓸 수 있는지**를 가른다 — `/health`(프로세스) · `/health/ready`(DB까지).
  배포 판정은 `ready` 쪽이다 — [CLAUDE.md](../../CLAUDE.md) §명령어 · `.github/workflows/deploy.yml` Health check
- **부가 기능이 죽어도 본 기능은 돈다.** 트렌드봇 · 외부 API 를 필수 의존으로 넣지 않았다 — [CLAUDE.md](../../CLAUDE.md) §생성
- 선택 입력(트렌드 · 날씨)이 실패해 기본 자료로 만들었으면 생성 기록에 남는다 — 같은 곳
- 두 사람이 같은 문서를 동시에 고칠 때 — ADR-035 `035-concurrent-writes-and-confirm-retry.md`
- 확정이 중간에 끊기지 않게 — ADR-040 `040-atomic-document-reconfirmation.md`
- 생성이 길어질 때 구간마다 120초 감시 타이머 · nginx 510초 — PR #229
- 확정한 계획안은 반을 고쳐도 확정할 때의 반 이름으로 내려받는다 — DB 검사 `ck_plans_confirmed_has_class_snapshot` · `backend/tests/test_plan_class_snapshot.py` · ADR-062

## 교사가 쓸 수 있는가

- 누르는 것은 44px 이상, 작은 글자를 걷어냈다 — 커밋 `c46b866` · `ab0f6b6`
- 색만으로 상태를 구분하지 않는다(색 + 왼쪽 굵은 선) — 커밋 `c46b866`
- 색 대비는 전부 기준(WCAG AA 4.5:1) 위다 — `frontend/styles/plan-generator-tokens.css`

  | | 크림 배경 | 흰 카드 |
  |---|---|---|
  | 본문 `#34312f` | 11.17:1 | 12.92:1 |
  | 보조 `#5c5243` | **6.62:1** | 7.66:1 |

  보조 글자를 옛 갈색(`#705d47` · 5.43:1)에서 한 단계 진하게 바꿨다. **문제는 대비가 아니라 크기였다** —
  9~11px 글자가 60군데 있었고 그걸 걷어냈다
- 메뉴를 「기록 · 문서」로 갈라 이름을 고쳤다 — 커밋 `3ba17a7`
- 말로 적기(받아쓰기) — `frontend/lib/hooks/use-dictation.ts`
- 홈에서 아이를 드롭다운으로 찾지 않는다 — 반 전체가 격자로 깔리고 칸마다 마지막 기록·이번 주 횟수가 보인다 — 커밋 `ea67852` · `frontend/components/app/ChildPicker.tsx`
- 한 주 넘게 기록이 빈 아이는 칸 색이 다르다 — 기록이 한 건도 없는 반에서는 칠하지 않는다 — 커밋 `80ed98a` · `frontend/tests/child-mark.test.mjs`
- 연간계획안을 만들고 다듬는 동안 사이드바가 72px 아이콘 줄로 접혀 문서 폭을 넓히고, 확정본에서는 다시 펼친다 — `frontend/components/app/compact-shell.ts` · `frontend/components/plan-generator/AnnualResult.tsx`
- 주간 실내자유놀이는 영역 표기와 활동을 구분하고, 5일·6일 HWPX에서 9pt·줄간격 140%·항목 뒤 1pt 여백을 사용한다 — `backend/app/features/plans/export.py` · `backend/app/features/plans/templates/weekly_v1_mon_fri.hwpx` · `weekly_v1_mon_sat.hwpx`
- 주간 자유놀이 후보에서 여러 활동을 선택하고 개별 수정·빼기·순서 변경할 수 있으며, 복사한 원 후보와 변경 이력을 서버가 보존한다 — `p0-planning/src/ssuksak/planning/application/weekly_activities.py` · `backend/tests/test_weekly_plans_api.py` · `frontend/components/workspace/WeeklyIndoorPlayPanel.tsx`
- 주간 연결 프롬프트 v5는 기관 근거로 쓰는 바깥놀이에 설명을 요청하고 Catalog 이름·부모 그대로 잇기 예외를 유지한다. 생성·수리·재생성의 지침 전달은 관련 테스트로 확인하며 실제 문장 품질은 별도 실측 대상이다 — `p0-planning/src/ssuksak/planning/planner/weekly.py` · `p0-planning/tests/adapters/test_weekly_composition.py`
- 설정을 우리 원 · 기록 · 계획안 · 내 계정 세 탭으로 나눴다. 칸마다 쪽지로 붙이고, 원 · 반 · 아동 명단 쪽지는 떼어 열면 첫 설정 화면과 같은 저장 길로 고친다. 비밀번호는 떼어 열 때만 입력칸을 그려 들어올 때마다 브라우저가 채우지 않는다 — 커밋 `e4e4bdb` · `frontend/components/auth/SettingsPage.tsx` · `frontend/components/auth/SettingsNoteEditors.tsx`
- 월간 v2 특별활동 시간표를 칸 나누기 · 빼기 · 크기 조절하고, 글뿐 아니라 그 변경도 되돌리기 · 다시 하기 한다. 되살리다 멈추면 글이 다 안 돌아왔을 수 있다고 알린다 — PR #379 · `frontend/lib/hooks/use-play-monthly-save.ts` · `frontend/tests/play-monthly-save-hook.test.mjs`
- 동의 없이 등록한 반을 다시 체크할 수 없던 흐름을 반 수정 계약으로 먼저 열었다 — ADR-062 · `docs/api-spec.md` §2 「반 수정」
- 등록한 반의 이름 · 연령 · 담임 · 동의를 서버에서 고칠 수 있고 아이가 있는 반은 동의를 끌 수 없다 — `PATCH /api/classes/{class_id}` · `backend/tests/test_class_edit.py`

## 고친 실제 사고

| 증상 | 원인 | 고친 곳 |
|---|---|---|
| 한 번 말했는데 네댓 번 적힘 | Web Speech API `results` 가 누적인데 매번 전체를 더했다 | 커밋 `d12f872` · `frontend/tests/dictation.test.mjs` |
| 기기 바꾼 교사가 온보딩 1단계에서 막힘 | 409 처리 | 커밋 `f607c54` |
| 다른 브라우저로 로그인하면 첫 설정을 마친 교사도 첫 설정으로 가고 반이 빈 칸 | 첫 설정을 마쳤는지를 브라우저 기록으로만 봤다 | 이슈 #291 · `frontend/lib/api/onboarding.ts` `restoreFromServer` |
| 서버 시각이 9시간 틀림 | `created_at` 이 UTC 인데 문자열을 잘랐다 | [CLAUDE.md](../../CLAUDE.md) §날짜·시각 |
| 목업이 PATCH 를 받아줘 통과, 진짜 서버는 PUT | 코드를 보고 짐작하고 값을 안 봤다 | [CLAUDE.md](../../CLAUDE.md) §서버 값은 타입 말고 실제 응답을 본다 |
| 휴대폰(390px) 보관함에서 반 목록 아래 빈 칸 · 종류 카드 아이콘이 점으로 보임 | 넓은 화면의 최소 높이 360px 와 아이콘 안 여백 13px 을 그대로 물려받았다 | `frontend/components/workspace/DocumentArchive.module.css` |
| 휴대폰에서 두 자리 날짜(「11.18」)가 보육일지 주간 칸을 넘침 | 칸 최소 폭 52px 이 글자 46px 에 여백을 못 담았다 | `frontend/components/workspace/DocumentArchive.module.css` · `frontend/e2e/document-archive-layout.spec.ts` |

세 번 같은 실수를 하고 **규칙으로 굳혔다** — 「한 번 찍어보고 쓴다」.

## 아직 아닌 것

- 휴대폰 하단 메뉴가 데스크톱 값에 덮여 글자가 두 줄로 꺾인다 — 이슈 #237
- 부하 시험을 한 적이 없다
- 반 수정 화면은 아직 없다(서버 API 는 있다) — ADR-062 「결과」

## 더 모을 근거

- [ ] 생성 1회 응답 시간 실측 (mock · real 각각)
- [ ] 운영에서 `ready` 가 떨어진 적이 있는지 기록

- 2026-11-03 계획안 표현 지침 정리: 연간 주제 범위 유지, 허용 근거를 통한 월간→주간 실내대체 계승, v1·v2 안전 문장 및 놀이 표현 기준을 정리했다. 관련 Core 172건·backend 30건 통과; 프롬프트 계약 확인이며 실제 생성 품질 향상은 아직 실측하지 않았다.
- 2026-11-04 연간 문서 디자인: HWPX 서식만 월간 v2의 하늘색 제목 띠·머리칸·표 선으로 통일하고, 웹 문서 미리보기에도 같은 색을 적용했다. 표 구조·내용은 유지했으며 한글 예시 출력은 전후 v1 1쪽/v2 2쪽·PDF 글자 수 동일, 관련 backend 20건 통과로 확인했다. 임의의 긴 입력까지 쪽 수를 보장하지는 않는다.
- 2026-11-04 연간 v2 하단 안내: 월간 v2의 안내 두 줄을 양쪽 쪽에 공통 꼬리말로 넣었다. 한글 예시 출력 2쪽 유지와 각 쪽 문구 출력, 내보내기 검사 12건 통과로 확인했으며 본문 표 위치는 변경하지 않았다.
- 2026-11-04 연간 문서 최종 조정: v1에도 같은 꼬리말을 추가하고, 두 양식의 표 선을 검정으로 변경했다. v1 아래 여백만 조정해 표 위치는 유지하면서 꼬리말 기준선을 맞췄다. 한글 예시 출력 v1 1쪽/v2 2쪽, 하단 위치 차이 0.1pt 이내와 관련 내보내기 검사를 확인했다.
- 2026-11-04 여백 후속 조정: 사용자 요청으로 공통 하단 기준선 대신 각 문서의 제목 띠 위 여백과 안내 띠 아래 여백을 대칭으로 맞췄다. PDF 144dpi 측정에서 v1 위·아래 47pt, v2 위·아래 16pt이며 본문 글자 좌표와 1/2쪽 구성은 그대로다. 연간 내보내기 관련 21건 통과.
- 2026-11-04 v2 간격 기준 정정: 사용자 확인에 따라 v2 안내는 종이 끝이 아니라 표 바로 아래에 배치했다. 한글 예시의 제목 띠↔표 및 표↔안내 띠 간격은 각각 약 6pt이며 본문 위치와 2쪽은 유지된다. v1은 변경하지 않았다.
