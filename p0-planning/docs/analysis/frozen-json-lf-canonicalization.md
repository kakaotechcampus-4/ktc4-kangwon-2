# Frozen JSON LF Canonicalization (Fix 1A · 1B)

- **작업일:** 2026-09-15
- **성격:** Byte Canonicalization Migration — **데이터 의미 변경 0**
- **Root Cause:** `CROSS_PLATFORM_LINE_ENDING_POLICY_MISSING`
- **범위:** 줄바꿈으로 깨진 Freeze 해시. `references/` 부재 2건은 **제외**(Fix 2)

---

## 1. 배경

팀 Repository에서 테스트 9건이 실패했다. PM은 전부 "동결 데이터 해시 불일치"로
보고했지만 조사 결과 원인이 둘로 갈렸다.

```text
7건   줄바꿈 정규화 (이 문서의 대상)
2건   references/ 원본 PDF 부재 (Fix 2에서 결정)
```

---

## 2. Root Cause

```text
core.autocrlf = true
.gitattributes = 없음
```

Git blob에는 JSON이 **LF**로 저장돼 있는데, Windows checkout이 이를 **CRLF**로
바꿔 놓았다. 기존 Freeze expected SHA는 그 **CRLF 워킹트리 bytes** 기준으로
만들어졌다.

```text
Windows(autocrlf=true)        CRLF   5831809b…   통과
Linux / CI / Docker / WSL     LF     bd5c0486…   실패
```

PM이 보고한 "실제 해시" `bd5c0486…`은 정확히 **git blob(LF)의 해시**다.
PM은 워킹트리가 아니라 저장소 원본을 해시한 것이고, 그 값이 맞다.

### 왜 데이터 변경이 아닌가

```text
줄바꿈 정규화 후 바이트 동일   7 / 7   True
JSON 의미 동일                7 / 7   True
데이터 내용이 바뀐 커밋        0 건
```

`p0-planning`의 데이터는 커밋 `2625b56`에 한 번 들어온 뒤 변경된 적이 없다.
blob 해시가 `2625b56` · `a6a96ac` · `HEAD`에서 모두 동일하다.

```text
DATA CORRUPTION      아님
STALE DATA           아님
COPY 변형            아님   (원본 P0 == 팀 워킹트리 9/9 바이트 동일)
```

---

## 3. 결정 — Canonical Line Ending = LF

`p0-planning/.gitattributes`를 새로 만들었다.

```gitattributes
*.json text eol=lf
```

P0 subtree에만 적용되므로 팀 Repository의 backend·frontend JSON에는 영향이 없다.
`eol=lf`는 `core.autocrlf`보다 우선하므로 Windows에서도 LF로 checkout된다.

`git check-attr` 확인 — 대상 7개 전부 `text: set`, `eol: lf`.

---

## 4. Old → New SHA Mapping

**모두 Semantic Equal = YES.** 바이트 표현만 CRLF → LF로 바뀌었다.

| Artifact | Old (CRLF) | New (LF, canonical) |
|---|---|---|
| `data/rules/safety_education_legal_v1.json` | `5831809b19a28505844cf10363c95eeb09ec4641d5fe54a26afdb1891c3ddba5` | `bd5c04864eb4eca66e51c24d58224723dbb401ead1b72f5e3b09d3a32057b3e9` |
| `data/templates/monthly_template_a.json` | `1f35322dd52f832bffc3057953ecbd64d52c2d855ada964af68472ebba1a7c34` | `a65b5f7355a4ac86f33d0973f1c94f8237434dc03fe593cad28aa0388cab2aaf` |
| `data/templates/monthly_template_a_v0_2_0.json` | `cb3fa9d15ea5ad55c961cc52588bc08e2bd31a720aa67a5dea0bb1fee644c3c5` | `fcde73aee479dfe020a966a5e69b06b4a6829f2d4f51217a39762eeabe707de9` |
| `data/themes/theme_reference_v0.json` | `c12999fa141d5c5fdecf39110adfb2227fc0ab98725991e8bdbca098b3ff4197` | `dae9f62db452c56b3b529aaa8e620411e9c11a2072163d6f9cc2a9d2ebc4d902` |
| `tests/golden/monthly_cases.json` | `c605641232d91abd1d6d2babb52a45b81ff8ea9de4c9bb3190cd68b5c62c85a7` | `cbe8571269480a80f4c13da14f64bd00fcee907c62d052ac4e2008e3ff263cc6` |
| `tests/golden/yearly_cases.json` | `7918e9f9cbe23580e7621e2f7c7ce40825a073afb8b0dc2038640a1291a6b384` | `94668b90613e798bd5015f0b770b0f763a021785b9c4ba61fb531ba75d200a60` |
| `data/activities/activity_reference_v0_2_1_draft.json` | `a64af4331cd850031fbb99f8ae3f283e609b3623da68b8ea118afb94e92faa63` | `a3ec9f7956bf84fb6a510605dfff6064627de5482b1e56dc584e2ceb734f608a` |

새 해시는 전부 **git blob 해시와 정확히 일치**한다. 즉 워킹트리가 저장소 원본과
같아진 것이지 새 바이트를 만들어 낸 것이 아니다.

```text
워킹트리 == git blob :  7 / 7  바이트 동일
데이터 JSON 실제 diff :  0 줄
```

---

## 5. Activity 승인 Provenance Migration (Fix 1B · 2026-09-15)

Fix 1A에서 남겨 두었던 1건이다. draft 해시가 테스트뿐 아니라 **승인 데이터 안에도**
기록돼 있었다.

```json
// data/activities/activity_reference_v0_2_1.json
"review": { "approved_from": {
  "draft_path":   "data/activities/activity_reference_v0_2_1_draft.json",
  "draft_sha256": "a64af433…"          // 승인 당시 CRLF 바이트
} }
```

정식 draft 바이트가 LF가 되었으므로 그 값이 가리키는 바이트는 더 이상 존재하지
않는다. 사람 결정(A안)에 따라 **이 한 필드만** 현재 canonical 값으로 옮겼다.

### 5.1 SHA 이동

| 대상 | Old (CRLF) | New (LF, canonical) |
|---|---|---|
| Draft | `a64af4331cd850031fbb99f8ae3f283e609b3623da68b8ea118afb94e92faa63` | `a3ec9f7956bf84fb6a510605dfff6064627de5482b1e56dc584e2ceb734f608a` |
| Approved | `ddbbe43f570cf64ef86db44e7de04e127aec4e663cdb41c26a8fe3c1002dc2ac` | `fa9f3215c3af212ea727835c5ab06ef903b0d7ee5c1f0c615d5eaf4bc156da1a` |

승인본 자체의 SHA가 바뀐 것은 **위 한 필드를 고쳤기 때문**이다. 활동 내용이
바뀐 것이 아니다.

### 5.2 바뀐 것과 바뀌지 않은 것

```text
변경된 JSON path      1개
  review.approved_from.draft_sha256

동일 확인
  activities · origins · coverage · schema_version · supersedes · draft
  catalog_id · catalog_version · normative_status · created_on
  review(approved_from 제외) — domain_owner_approval · approved_by
                               approved_at · review_document
```

Deep diff로 `changed paths = 1`을 확인한 뒤에만 기록했다. 파일은 JSON을 다시
직렬화하지 않고 **해당 해시 문자열만 치환**했다 — 재직렬화하면 들여쓰기·키
순서·이스케이프가 함께 바뀔 수 있기 때문이다. 바이트 길이도 변하지 않았다.

```text
Activity content change    NO
Activity IDs change        NO
Evidence change            NO
Approval decision change   NO
Reviewer change            NO
approved_at change         NO
catalog version bump       NO

Provenance metadata migration   YES
Canonical byte policy migration YES
```

### 5.3 갱신한 곳과 보존한 곳

**현재 계약 — 갱신했다.**

```text
tests/golden/test_monthly_llm_freeze.py          승인본 SHA
tests/adapters/test_activity_v0_2_1_approved.py  DRAFT_SHA
```

**역사 기록 — 옛 값을 그대로 뒀다.** 승인 당시의 사실이기 때문이다. 전역
Search/Replace를 하지 않았다.

```text
docs/analysis/activity-v0-2-1-activation-report.md      + migration note 병기
docs/analysis/activity-v0-2-1-setting-audit.md          보존
docs/analysis/monthly-quality-patch-1-review.md         보존
docs/analysis/monthly-llm-planner-l1-evidence-ingestion.md   보존
docs/analysis/monthly-llm-planner-vnext-design.md       보존
docs/analysis/monthly-v0-2-1-demo-quality-verification.md    보존
```

승인 보고서에는 "승인 당시 CRLF / 현재 canonical LF"를 나란히 적은 주석을
추가했다. 옛 값은 지우지 않았다.

---

## 6. 결과

```text
                  Fix 이전(LF 환경)   Fix 1A 후    Fix 1B 후
passed                    2389          2394        2396
failed                       9             4           2
skipped                      6             6           6
deselected                   4             4           4
```

남은 2건은 전부 `references/` 부재다. **줄바꿈과 무관하며 Fix 2에서 결정한다.**

```text
test_activity_adapters.py::test_real_catalog_origins_are_declared_and_hashes_match
test_activity_v0_2_draft.py::test_origin_sha256_matches_repository_files
→ references/ 369개 PDF 미커밋. `assert path.exists()`에서 실패한다
```

예상치 못한 새 실패는 **0건**이다.

---

## 7. 바꾸지 않은 것

```text
JSON 의미 내용 · key/value · 배열 순서 · 들여쓰기
version · approved_at · reviewer · approval status
Golden case 내용 · Activity · Theme · Template · Safety rule 내용
src/ 전체 · Planning Domain · Planner · Demo runtime
references/ 관련 일체
```

버전을 올리지 않았다. 이번 변경은 **version change가 아니라 byte
representation migration**이다.

```text
Old canonical environment   Windows CRLF checkout
New canonical representation  LF
Semantic JSON change          NONE
```

---

## 8. 경고 — 원본 `C:\MAIN\P0`에서 다시 복사하지 말 것

```text
DO NOT RECOPY FROM LEGACY C:\MAIN\P0
```

마이그레이션 원본은 아직 **CRLF 바이트와 옛 해시**를 그대로 갖고 있다. 그 환경
에서는 자체적으로 통과하므로 문제가 보이지 않는다. 그러나 거기서 다시 복사하면

```text
CRLF 데이터 파일          ← 이번에 LF로 맞춘 것을 되돌린다
옛 Freeze 해시            ← 이번에 갱신한 기대값을 되돌린다
옛 draft_sha256 provenance ← Fix 1B를 되돌린다
```

가 한꺼번에 재발한다. 이제부터 **`p0-planning`이 source of truth**다.

원본을 같은 정책으로 동기화할지는 별도 작업으로 결정한다. 이번 Fix에서는
건드리지 않았다.
