# Activity Reference v0.2.1 — Setting Provenance Targeted Audit

- 작성일: 2026-09-13
- 대상: `data/activities/activity_reference_v0_2_1_draft.json`
  (`activity-reference-v0.2.1`, `PENDING_HUMAN_REVIEW`, 196 items,
  SHA-256 `a64af4331cd850031fbb99f8ae3f283e609b3623da68b8ea118afb94e92faa63`)
- 성격: **감사 보고서.** 이번 단계에서 Reference / Production / Rule을 **수정하지 않았다.**
- 재현 도구: `analysis/tools/audit_setting_provenance.py` (분석 전용, 프로젝트 dependency 아님)
- 재현 산출물: `analysis/tmp/setting_audit.json` (근거 288건 전수 판정 기록)

---

## 1. `팽이 놀이` Source 추적

### 1.1 결론

```text
판정: OUTDOOR_CORRECT
```

### 1.2 근거 (원문 그대로)

| 항목 | 값 |
|---|---|
| `activity_id` | `act_outdoor_v2_35b98e9723` |
| `label` | `팽이 놀이` |
| `setting` | `OUTDOOR` |
| Evidence | `sample.monthly.keunbit.2026.09`, page 1 |
| 파일 | `references/samples/monthly/2026_민간_큰빛어린이집_만3세,만4-5세_월간계획안(9월)pdf.pdf` |
| 행 | `흥미 예상 놀이` (row band y≈407–464) |
| 기록된 provenance | `observed_section = outdoor_play`, `observed_source_label = 바깥놀이 계열` |

해당 셀의 원문은 다음과 같다. 셀 안에서 `<실내놀이>`와 `<바깥놀이>`가 **다시 나뉜다.**

```text
<실내놀이> 팽이가도는원리/ 다양한팽이관찰/ 실팽이놀이/ 블록으로팽이만들기/ 팽이로만드는다
양한도형/ 팽이시합장만들기
<바깥놀이> 팽이놀이(대체활동: 팽이가움직여요.) <활동> 다양한도형이있어요.
```

`팽이 놀이`는 `<바깥놀이>` 뒤에 있고, 괄호 안의 `팽이가움직여요.`가 그 대체활동이다.
따라서 `OUTDOOR`는 **원문과 일치한다.**

### 1.3 Patch 1에서 우려가 제기된 이유 — 자기 도구의 오탐

Monthly Quality Patch 1 검토 중 `팽이 놀이`가 `<실내놀이>` 구간에서 관찰된 것처럼 보인 것은
**부분 문자열 오탐**이었다. `팽이 놀이`가 `실팽이 놀이` **안에서** 매칭되었다.

이번 감사 도구는 낱말 경계를 요구해 같은 오탐을 막는다.

```python
# analysis/tools/audit_setting_provenance.py
return re.compile(r"(?<![가-힣])" + body + r"(?![가-힣])")
```

경계를 넣은 뒤 `팽이 놀이`의 `<실내놀이>` 매칭은 사라졌고, `<바깥놀이>` 매칭만 남는다.

---

## 2. `OUTDOOR`가 어떻게 부여되었는가 (재현 가능한 Artifact 기준)

### 2.1 먼저 확인한 사실 — Rule도 heuristic도 아니다

저장소에서 `setting` 값을 **계산**하는 코드는 없다. 확인 방법과 결과:

```bash
grep -rln '"setting"' --include=*.py analysis src
#  analysis/tools/audit_setting_provenance.py        ← 이번 감사 도구(읽기)
#  src/ssuksak/adapters/activity_reference_schema.py ← 스키마 검증(읽기)
```

`src/ssuksak/adapters/activity_reference_schema.py`의 `setting`은 **검증만** 한다.

```python
@field_validator("setting")
@classmethod
def _known_setting(cls, v: str) -> str:
    allowed = {s.value for s in ActivitySetting}
    if v not in allowed:
        raise ValueError(f"알 수 없는 setting '{v}'. 허용: {sorted(allowed)}")
    return v
```

`analysis/tools/build_v0_2_1_draft.py`도 v0.2.0을 그대로 복사할 뿐 `setting`을 만들지 않는다.

즉 **v0.2.0 seed를 만든 전사 작업 자체가 저장소에 스크립트로 남아 있지 않다.**
이 사실을 숨기지 않고 보고한다. 재현 가능한 근거는 아래 §2.2의 **Artifact 자체의 기록**이다.

### 2.2 Artifact가 기록하고 있는 부여 방식

`activity_reference_v0_2_1_draft.json`의 `setting_semantics` 블록이 부여 규칙을 명시한다.

```json
"setting_semantics": {
  "values": ["OUTDOOR", "INDOOR", "EITHER"],
  "statement": "... 이 seed는 전부 바깥놀이 행에서 관찰된 OUTDOOR다.",
  "indoor_alternative_exclusion":
    "[실내대체] · [대체] · (대체활동: …) inline 태그가 붙은 항목은 indoor_alternative
     Section 소속이므로 outdoor 후보로 전사하지 않았다. 같은 놀이가 다른 기관에서 직접
     바깥놀이 항목으로 관찰된 경우에만 그 근거로 후보가 됐다."
}
```

따라서 `OUTDOOR`는 **활동별로 판정된 속성이 아니라 Catalog 수집 범위의 상수**다.
수집 대상이 "월간계획안의 바깥놀이/실외놀이 행"이었고, 그 행에서 전사된 항목만 들어왔다.
196개 활동 전부 `setting = OUTDOOR`이고 288개 근거 전부 `observed_section = outdoor_play`인
것이 그 결과다.

각 근거는 자기가 나온 행 label을 원문 그대로 남긴다 (`observed_source_label`).

| `observed_source_label` | 근거 수 |
|---|---:|
| `바깥놀이 계열` | 214 |
| `바깥놀이` | 21 |
| `실외 자유 놀이` | 15 |
| `실외놀이` | 9 |
| `바깥놀이(접두 태그)` | 8 |
| `바깥 놀이` | 7 |
| `바깥` | 5 |
| `실외놀이 대체(신체)활동` | 5 |
| `바깥놀이 (대체활동)` | 3 |
| `바깥놀이 / 대체활동` | 1 |
| **합계** | **288** |

전부 바깥놀이/실외놀이 계열이다. 실내 계열 label로 기록된 근거는 **0건**이다.

추출 방법도 Artifact에 기록되어 있다.

```json
"evidence_semantics": {
  "extraction_method": "pdftotext -layout / -raw 교차 확인과 pdfplumber 셀 기하 재구성을
                        함께 사용해 바깥놀이 행 귀속을 확정했다. ...",
  "retranscription_note": "... LLM 복원·의미 보정·추측·유사 이름 치환은 사용하지 않았다."
}
```

그리고 대체활동 항목은 **명시적으로 제외 집계**되어 있다.

```json
"exclusion_policy": { "v0_2_summary": {
  "INSTITUTION_SPECIFIC_EXCLUDE": 16,
  "INDOOR_ALTERNATIVE_EXCLUDE": 162,
  "COMMUNITY_LINKAGE_EXCLUDE": 15,
  "AMBIGUOUS_REVIEW_REQUIRED": 8,
  "SAFETY_BOUNDARY_EXCLUDE": 0
}}
```

`INDOOR_ALTERNATIVE_EXCLUDE: 162` — 실내대체 항목 162건을 후보에서 뺐다는 기록이다.

### 2.3 §2 결론

- `OUTDOOR`는 추론된 값이 아니라 **수집 범위 선언에서 나온 상수**다.
- 그 선언의 재현 가능한 근거는 (a) `setting_semantics`, (b) `exclusion_policy`,
  (c) 근거 288건의 `observed_section` / `observed_source_label`이다.
- 전사 스크립트는 저장소에 없다. **본 감사는 그 선언을 믿지 않고 원문 PDF로 재검증했다**(§3).

---

## 3. 전수 감사 (196 Activity / 288 Evidence)

### 3.1 방법

각 근거의 `origin_id` → `origins[].path` → PDF page로 되돌아가, 표 선(vector) 기하로 셀을
복원한 뒤 **원문에 적힌 글자만**으로 판정했다. 의미 추론은 쓰지 않았다.

판정 신호는 다섯 가지이고 구체적인 쪽이 이긴다.

| 우선 | 신호 | 예 |
|---|---|---|
| 1 | 항목 자신이 대체 표시로 시작 (`leading-alt`) | `[실내대체] 몸으로 자음 모음표현하기` |
| 2 | 대체 괄호 **안** (`inside-alt-bracket`) | `⦁무궁화 꽃이… 【대체활동 : 강강술래를 해요】` |
| 2 | 대체 **구분자 태그 뒤** (`after-alt-separator`) | `가을 하늘 보며 산책하기 [실내대체] 스카프로…` |
| 2 | 대체 표기 밖 (`outside-alt-bracket`) | `<바깥놀이> 팽이놀이(대체활동: …)` |
| 3 | 괄호 없는 접두 표기 (`prefix<…>`) | `♥바깥놀이-비석치기` |
| 4 | 셀 안 인라인 태그 (`inline<…>`) | `<바깥놀이> …` / `[바깥] …` |
| 5 | 행 label (`row[…]`) | 첫 열 + 그 셀 왼쪽의 모든 열 |

셀을 읽는 방식은 표 모양에 따라 세 가지이고, **더 구체적인 모드가 이긴다.**

| 모드 | 대상 레이아웃 | 채택된 근거 수 |
|---|---|---:|
| `tagband` | `[바깥]` / `[대체]`가 **별도 왼쪽 열**에 있는 표 (예일·괴산) | 48 |
| `raw` | `A [실내대체] B`처럼 **한 줄이 그 자체로 완결**되는 표 | 142 |
| `rejoin` | 셀 안 줄바꿈(wrap)된 label을 복원해야 하는 표 | 62 |

원문에서 label을 못 찾으면 **추측하지 않고** `SETTING_NOT_RECOVERABLE`로 남긴다.

### 3.2 결과

**Activity 단위 (196건)**

| 판정 | 건수 |
|---|---:|
| `SOURCE_CONFIRMED_OUTDOOR` | **180** |
| `MIXED_SETTING_EVIDENCE` | **5** |
| `SOURCE_CONFIRMED_NON_OUTDOOR` | **0** |
| `SETTING_NOT_RECOVERABLE` | **11** |

**Evidence 단위 (288건)**

| 판정 | 건수 |
|---|---:|
| `OUTDOOR` | **245** |
| `BOTH_IN_SOURCE` | 6 |
| `NON_OUTDOOR` | **1** |
| `SETTING_NOT_RECOVERABLE` | 36 |

### 3.3 핵심 사실

- **원문에서 실내 전용으로 확인된 Activity는 0건이다.**
- 실내 쪽 근거는 단 1건(`흙공 만들기`)이고, 그마저 같은 기관이 실외놀이 행에도 올린 항목이다.
- 따라서 **체계적 setting 추출 결함은 존재하지 않는다.**

### 3.4 감사 도구를 만들면서 잡은 오탐 (기록)

이 감사도 처음에는 34건의 가짜 `NON_OUTDOOR`를 냈다. 전부 도구 결함이었다.
같은 함정이 Patch 1의 `팽이 놀이` 우려를 만들었으므로 남긴다.

| # | 오탐 원인 | 수정 |
|---|---|---|
| 1 | `바깥놀이 [대체활동]` 병합 행 label을 실내로 읽음 | 행 label에서는 바깥놀이가 이긴다 |
| 2 | `실외 자유 놀이`가 `실외놀이`의 부분문자열이 아님 | `실외`를 어휘에 추가 |
| 3 | `팽이 놀이`가 `실팽이 놀이` 안에서 매칭 | 좌우 낱말 경계 `(?<![가-힣]) … (?![가-힣])` |
| 4 | `겨울 음식`이 `겨울 음식에는 무엇이 있을까?` 안에서 매칭 | 오른쪽 경계 추가 |
| 5 | `실내외 놀이` 행을 실내로 읽음 | 실내·실외 동시 지시어는 **판정하지 않음** |
| 6 | 대체 태그의 앞/뒤로만 갈라 한 줄에 태그가 여러 개면 뒤집힘 | 괄호 **안/밖**으로 판정 |
| 7 | `[실내대체]` 구분자형과 `【대체활동 : X】` 내용포함형을 같게 취급 | 두 형태를 분리 (지배 범위가 반대다) |
| 8 | 세로쓰기 병합 label(`바/깥/놀/이` + `실외놀이`)에서 첫 열만 봄 | 같은 행 **왼쪽 셀 전부**를 label context로 |
| 9 | `[바깥]`/`[대체]`가 별도 열인 표에서 태그가 wrap된 label 사이에 끼어듦 | y 근접도로 태그–줄 배정 (`tagband`) |
| 10 | 그 배정이 괴산처럼 태그가 항목 첫 줄에 오는 표를 뒤집음 | 태그가 자기 줄에 혼자일 때만 위 줄을 지배 |

---

## 4. `MIXED_SETTING_EVIDENCE` 5건 — Evidence 단위 판정과 Contract 판단

§4 원칙대로 **Activity를 통째로 제거하지 않았고**, 근거 하나하나를 원문에서 확인했다.

### 4.1 자기 자신이 자기 대체안인 경우 — 4건

큰빛·엄지·괴산하나는 바깥놀이 항목의 실내 대체안으로 **같은 이름을 다시 적는다.**
그래서 같은 label이 대체 괄호 밖(바깥놀이)과 안(대체안)에 동시에 나타난다.

| Activity | 원문 | 기관 |
|---|---|---|
| `동대문 놀이` | `<자랑스런우리나라> 동대문놀이(대체활동: 동대문놀이)` | 큰빛 2026-09 |
| `꼭꼭 숨어라` | `- 꼭꼭숨어라` / `(대체활동-꼭꼭숨어라)` (행 label `바깥놀이 (대체활동)`) | 엄지 2026-09 |
| `사방치기` | `<우리나라사람들의생활과문화> 사방치기(대체활동: 사방치기)` | 큰빛 2026-09 |
| `전통놀이` | 같은 셀에 `- 전통놀이`(바깥)와 `-[실내대체] … 전통놀이` | 괴산하나 2026-09 |

네 건 모두 **다른 기관에서 독립적으로 바깥놀이 항목으로 확인**된다.

- `동대문 놀이` — 시립새봄 `실외 자유 놀이` 행
- `사방치기` — 아이사랑 만5세 `♥바깥놀이-사방치기`, 우리어린이집 2025-02 `바깥놀이` 행
- `전통놀이` — 해찬솔 `실외놀이` 행, 서진 2025-10 / 2026-09 `바깥놀이` 행
- `꼭꼭 숨어라` — 근거 2건 모두 엄지 `바깥놀이` 행 소속이고, 실내 쪽은 자기 대체안뿐

**판단: 실내 전용 근거가 아니다.** "비가 오면 실내에서 같은 놀이를 한다"는 기관 메모이지,
그 놀이가 실내 활동이라는 뜻이 아니다.

### 4.2 같은 기관이 실외·실내 양쪽 행에 올린 경우 — 1건

`흙공 만들기` (아이들세상 2026-09, 같은 파일 안)

```text
실외놀이   텃밭 돌보기. 곤충 탐색, 모래놀이, 물길 놀이, 줄넘기, 흙공 만들기 등
실내놀이   달 관련 옛이야기 · 동화 · 역할놀이 · 미술놀이 등 / 씨름 / 흙공 만들기 / 제철음식 만들기
```

이것은 **진짜 이중 배치**다. 다만 Catalog가 실제로 쓰는 근거 2건은 둘 다 실외 행이다.

| 근거 | `observed_source_label` |
|---|---|
| p1 | `실외놀이` |
| p2 | `실외놀이 대체(신체)활동` |

즉 v0.2.1이 기록한 근거는 실외 쪽이고, 실내 쪽 출현은 **Catalog가 근거로 삼지 않은 별개 행**이다.

### 4.3 기존 Contract 기준 판단 — 5건 모두 outdoor 후보로 사용 가능

Activity Hard Filter의 setting 조건은 `ActivityCatalog.eligible_candidates()`의 ④뿐이다.

```text
outdoor_play  ⇒  setting ∈ { OUTDOOR, EITHER }
```

5건 모두 `setting = OUTDOOR`이므로 조건을 만족한다. 그리고

- §4.1의 4건은 **실내 전용 근거가 없다** → `OUTDOOR` 유지가 원문과 맞다.
- §4.2의 1건은 실내에서도 가능하지만, `EITHER`로 바꿔도 `outdoor_play` 필터 통과 여부는
  **똑같다**. 지금 바꿔야 할 기능적 이유가 없다.

**따라서 5건 모두 변경하지 않는다.** `EITHER` 도입은 사람 승인이 필요한 의미 변경이며
이번 감사 범위 밖이다 → §7 후속 항목으로만 기록한다.

---

## 5. `SETTING_NOT_RECOVERABLE` 11건 — 수기 검증

도구가 못 찾은 이유는 전부 **canonical label과 원문 줄 나눔이 다르기 때문**이고,
setting 근거가 없어서가 아니다. 11건 전부 원문을 직접 열어 확인했다.

| Activity | 파일 | 원문에서 확인한 자리 |
|---|---|---|
| `‘초가집에 왜 왔니?’ 놀이` | 시립새봄 p4 | 행 label `실외 자유 놀이` / `⦁‘초가집에 왜 왔니?’놀이를 해요. 【대체활동 : 한복 찾아 돌아와요】` — 괄호 밖 |
| `가을바람에 풍선날리기` | 아이사랑 만4세 2026-09 | `♥바깥놀이-가을바람에` + `풍선날리기` (두 줄 wrap) |
| `전통 음식을 배달해요` | 예일 2026-09 | `전통` / `[바깥] 음식을 배달해요` (대체는 `[대체] 우리나라 문화유산 찾기`) |
| `가꾼 식물들을 …, 물주기, 벌레잡기` | 아이들세상 2026-09 | 행 label `텃밭` |
| `산책길에 만난 이웃에게 인사해요` | 예일 2026-06 | `[바깥] 이웃에게 인사해요` |
| `비온 뒤 놀이터 탐험` | 예일 2026-07 | `[바깥] 놀이터 탐험` |
| `그림자로 물고기를 만들어요` | 예일 2026-08 | `그림자로` / `[바깥] 물고기를 만들어요` (대체 `[대체] 물고기를 잡아요`) |
| `자연 속 작은 생명체 찾기` | 예일 2026-07 | `[바깥] 작은 생명체 찾기` |
| `우리 나라 상징을 찾아요` | 예일 2026-09 | `[바깥] 상징을 찾아요` |
| `누워서 소리를 들어요` | 예일 2026-04 | `누워서` / `[바깥] 소리를 들어요` (대체 `[대체] 그림자를 보고 찾아요`) |
| `맑고 푸른 가을 하늘` | 아이사랑 만5세 2026-09 | `♥바깥놀이-맑고 푸른 가을 하늘` |

**11건 전부 바깥놀이 쪽이다. 실내 쪽에 있는 것은 하나도 없다.**

도구에 이 11건을 억지로 맞추는 보정을 넣지 않았다. 그 보정을 시도했을 때
서진·괴산의 바깥놀이 항목 13건이 대체안으로 뒤집혔기 때문이다(§3.4의 #10과 같은 부류).
**추측으로 판정 수를 늘리는 것보다 미복원으로 남기고 사람이 확인하는 쪽을 택했다.**

---

## 6. 수정 여부 결정과 Freeze 확인

### 6.1 결정: **v0.2.1 Draft를 수정하지 않는다**

근거:

1. 원문 확인 결과 실내 전용 Activity가 **0건**이다.
2. `MIXED` 5건은 §4.3대로 기존 Contract에서 그대로 outdoor 후보다.
3. `NOT_RECOVERABLE` 11건은 §5에서 전부 바깥놀이로 수기 확인됐다.
4. `팽이 놀이`는 §1대로 원문과 일치한다. Patch 1의 우려는 자기 도구의 오탐이었다.

**→ Setting repair 대상 항목 0건.**

### 6.2 변경하지 않은 것 (§5 금지 항목 확인)

| 항목 | 상태 |
|---|---|
| `data/activities/activity_reference_v0_2.json` | 무수정 (SHA 불변) |
| `data/activities/activity_reference_v0_2_1_draft.json` | 무수정 (SHA 불변) |
| Production / Demo default catalog | `activity_reference_v0_2.json` 그대로 |
| `monthly_activity_selection.py` Rule v2 | 무수정 |
| Week Experience Reference | 착수하지 않음 |
| v0.2.1 승인 상태 | `PENDING_HUMAN_REVIEW` 그대로 |

이번 단계에서 **추가·변경된 파일은 분석 도구와 이 보고서뿐이다.**

- `analysis/tools/audit_setting_provenance.py` (감사 도구)
- `analysis/tmp/setting_audit.json` (감사 산출물)
- `docs/analysis/activity-v0-2-1-setting-audit.md` (이 문서)

### 6.3 Artifact SHA-256 (freeze 확인)

```text
theme_reference_v0.json              c12999fa141d5c5fdecf39110adfb2227fc0ab98725991e8bdbca098b3ff4197
activity_reference_v0.json           b565254f6668aeea04ef4ddce235ef51fd7af80d258d568e2f4d31fae6648b0d
activity_reference_v0_2.json         e27ebca3342a84327c6624c5ba258b9bc98aef37ba5362b61f283c47ece0bde6
activity_reference_v0_2_draft.json   c9c0e9da7e82bc73a6120551210983d786b4d6218fd6492c0727102cb6d29c5b
activity_reference_v0_2_1_draft.json a64af4331cd850031fbb99f8ae3f283e609b3623da68b8ea118afb94e92faa63
monthly_template_a.json              1f35322dd52f832bffc3057953ecbd64d52c2d855ada964af68472ebba1a7c34
safety_education_legal_v1.json       5831809b19a28505844cf10363c95eeb09ec4641d5fe54a26afdb1891c3ddba5
tests/golden/monthly_cases.json      c605641232d91abd1d6d2babb52a45b81ff8ea9de4c9bb3190cd68b5c62c85a7
tests/golden/yearly_cases.json       7918e9f9cbe23580e7621e2f7c7ce40825a073afb8b0dc2038640a1291a6b384
CLAUDE.md                            a723a7ee488eacdb9b8a95efd07e2516bf247a16fb9f4cc51dfb054867ef78f2
```

전부 Patch 1 승인 시점과 동일하다.

### 6.4 회귀 확인

```text
python -m pytest
1520 passed, 4 deselected in 11.10s
```

여기에는 v0.2.1 Draft 검증 98건(`tests/adapters/test_activity_v0_2_1_draft.py`)이 포함되고,
그 안에 12개월 × 6개 연령집합 = 72조합 후보 coverage 회귀가 들어 있다.
Draft를 수정하지 않았으므로 Generate / Regenerate / catalog pinning / 결정론적 정렬도
Patch 1 승인 시점 결과와 동일하다.

---

## 7. 남는 항목 (이번 범위 밖 · 사람 결정 필요)

1. **`흙공 만들기`의 `EITHER` 승격 여부.** 같은 기관이 실외·실내 양쪽에 올린 유일한 항목이다.
   현재 `outdoor_play` 선택 결과는 `OUTDOOR`와 `EITHER`가 동일하므로 급하지 않다.
2. **자기 자신을 대체안으로 적는 표기의 취급.** 4개 기관에서 관찰된다.
   `indoor_alternative` Section을 실제로 구현할 때 의미 규칙이 필요하다.
3. **미복원 11건의 Evidence label 정규화.** canonical label과 원문 줄 나눔 차이 때문이며
   setting과 무관하다. Activity v0.3에서 `observed_label`을 원문 줄 그대로 남길지 검토 대상이다.
4. **v0.2.1 → `HUMAN_APPROVED` 승격과 Production default 전환.** 사람 승인 사안이다.

---

```text
SETTING AUDIT
  audited_catalog          : activity-reference-v0.2.1 (PENDING_HUMAN_REVIEW)
  audited_file             : data/activities/activity_reference_v0_2_1_draft.json
  audited_sha256           : a64af4331cd850031fbb99f8ae3f283e609b3623da68b8ea118afb94e92faa63
  activity_count           : 196
  evidence_count           : 288

  paengi_nori_verdict      : OUTDOOR_CORRECT
  paengi_nori_source       : 큰빛어린이집 2026-09 p1 · 흥미 예상 놀이 행 · <바깥놀이> 팽이놀이
  paengi_nori_note         : Patch 1의 우려는 '실팽이 놀이' 부분문자열 오탐이었다

  setting_assignment_basis : Catalog 수집 범위 상수 (setting_semantics / exclusion_policy)
  setting_assignment_code  : 없음 — 저장소에 setting을 계산하는 코드가 존재하지 않는다

  activity_SOURCE_CONFIRMED_OUTDOOR      : 180
  activity_MIXED_SETTING_EVIDENCE        : 5
  activity_SOURCE_CONFIRMED_NON_OUTDOOR  : 0
  activity_SETTING_NOT_RECOVERABLE       : 11

  evidence_OUTDOOR                       : 245
  evidence_BOTH_IN_SOURCE                : 6
  evidence_NON_OUTDOOR                   : 1
  evidence_SETTING_NOT_RECOVERABLE       : 36

  mixed_self_referential_alternative     : 4  (동대문 놀이 · 꼭꼭 숨어라 · 사방치기 · 전통놀이)
  mixed_genuine_dual_placement           : 1  (흙공 만들기)
  mixed_usable_as_outdoor_candidate      : 5  (setting ∈ {OUTDOOR, EITHER} 조건 충족)

  not_recoverable_manually_verified      : 11 / 11  → 전부 바깥놀이 쪽
  systematic_setting_defect              : NOT FOUND
  setting_repair_required                : 0 items

  v0_2_0_sha256_unchanged                : e27ebca3342a84327c6624c5ba258b9bc98aef37ba5362b61f283c47ece0bde6
  v0_2_1_sha256_unchanged                : a64af4331cd850031fbb99f8ae3f283e609b3623da68b8ea118afb94e92faa63
  production_default_unchanged           : activity_reference_v0_2.json
  rule_v2_unchanged                      : true
  week_experience_touched                : false
  pytest                                 : 1520 passed, 4 deselected

  verdict : ACTIVITY_REFERENCE_V0_2_1_READY_FOR_APPROVAL
```
