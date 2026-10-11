# ADR-023: 모델은 `gpt-6-luna` 로 고정하고, 온도를 보내지 않는다

- 2026-10-06
- 상태 — 채택
- 관련 — ADR-004(아동 실명) · ADR-014(규칙은 검사한다) · api-spec §4 · §11

## 맥락

8주차까지 `LLM_MODE=mock` 으로만 돌았다. 처음으로 엘리스 MLAPI 에 실제로 붙여보니
코드가 가정하던 것 셋이 틀려 있었다.

```
모델 이름      "openai/gpt-4.1-mini"   →  model_not_found
온도 0         temperature: 0          →  Unsupported value
주소           base/chat/completions   →  404 (경로에 /v1 이 빠졌다)
```

엘리스는 **모델마다 주소가 다르다**(`https://mlapi.run/<uuid>/v1`). `GET /v1/models` 가
그 주소에서 쓸 수 있는 이름을 준다.

## 결정

1. **모델은 `openai/gpt-6-luna` 다.** 코드 두 곳(`shared/llm/client.py` ·
   `planner/contracts.py`)에 상수로 박는다. 둘이 달라지면 같은 계획안 안에서 연간과
   월간의 문체가 갈린다.
2. **온도를 보내지 않는다.** 이 모델은 기본값(1)만 받고 0 을 거부한다.
   `response_format` 만으로 형식을 잡는다.
3. **`MONTHLY_LLM_MODEL` 같은 환경변수 교체 경로를 두지 않는다.** 모델을 바꾸는 것은
   코드 변경이다 — 프롬프트 · golden 파일 · 주소가 한 모델에 묶여 있다.
4. **`ELICE_MLAPI_BASE_URL` 은 `/v1` 까지 적는다.** 코드가 뒤에 `/chat/completions`
   를 붙인다.

## 근거

- **[실측]** 모델마다 주소가 달라 각각 쏴봤다.

  ```
                                 gpt-5.6-luna   gpt-6-luna
  일반 호출                           ✅            ✅
  response_format: json_object       ✅            —    단 messages 에 「json」 낱말 필요
  json_schema + strict: true         ✅            ✅   {"pick":"가"} — enum 밖을 못 뱉는다
  temperature: 0                     ❌            ❌   Only the default (1) value is supported
  max_tokens                         ❌            —    max_completion_tokens 를 쓰라고 한다
  ```

  `—` 는 `gpt-6-luna` 에서 다시 안 해본 것이다. 둘이 같은 공급자·같은 게이트웨이라
  같을 것으로 보지만 확인은 아니다.

- **⚠️ `strict` 확인은 작은 스키마로만 했다.** `{"pick": {"enum": ["가"]}}` 는
  「엘리스가 `strict` 파라미터를 받는다」까지만 보여준다. 실제 월간 스키마
  (`monthly_response_schema`)로는 아직 보내본 적이 없다 — backend 에 월간이 연결돼
  있지 않고, live 스모크는 대상 칸이 없어 `items: {"anyOf": []}` 로 만들어진다.
  **월간을 연결할 때 실제 스키마로 ① 400 없이 받는지 ② 응답 시간(타임아웃 30초)
  ③ 응답의 `model` 이름을 남긴다.**

- **`strict` 가 되는 것이 모델 선택의 기준이었다.** 월간 칸은 `reference_id` 와
  활동명을 schema 가지로 묶어 고정한다(#90). 공급자가 그 스키마를 강제하지 못하면
  그 설계가 통째로 무의미해진다. Claude 계열은 `/v1/messages` 가 따로 있어 `strict`
  처리가 어떻게 되는지 확인하지 못했다 — 파일럿 2주 전에 시험할 것이 아니다.
- **`gpt-6-luna` 로 간다.** 처음에는 `gpt-5.6-luna` 를 골랐다 — 바꾸기 전이
  `gpt-4.1-mini` 였고 급이 같아야 성공률 전/후 비교에서 모델 덕인지 설계 덕인지
  가려서다. 그 뒤 `gpt-6-luna` 가 열려서 그 주소에서 `/v1/models` 로 model id 를
  확인하고 `strict` · 온도를 다시 실측한 뒤 올렸다. 둘 다 같은 「저단가 대량 처리」
  급이라 비교 기준은 유지된다. **P0 는 연간·월간 모두 `gpt-6-luna` 로 통일한다.**

## 결과

- **같은 입력에 같은 답이 온다고 가정할 수 없다.** 온도 0 이 깨졌다.
  - 교사가 겪는 일은 거의 없다. 연간은 반당 하나라 다시 만들 수 없고(api-spec §4),
    만든 뒤에는 `plans.body` JSONB 에 그대로 남는다. 달라지는 것은 새로 만들 때뿐이다.
  - 월간 칸 재생성은 원래 「다시 만들어달라」는 뜻이라 달라지는 것이 맞다.
  - **측정에는 오히려 낫다.** 멘토 리뷰(PR #82)에서 「temperature 0 이면 같은 입력
    4번이 사실상 1번」이라는 지적을 받았다. 이제 반복이 의미를 갖는다.
  - golden 테스트는 영향이 없다 — CI 는 가짜 LLM 으로 돈다.
- **형식을 지키는 책임이 `response_format` 으로 옮겨갔다 — 다만 칸 안까지다.**

  ```
  칸 안의 값    칸 종류 · 활동명과 reference_id 짝 · grounding_refs   strict 가 잠근다
  칸 목록       필수 칸이 다 있나 · 중복 · 주차 구조                   사후 검증이 잡는다
  ```

  `monthly_response_schema`(`parser.py`)는 `month_sections` · `weeks` · `sections`
  를 그냥 배열로 둔다. **필수 칸 누락 · 같은 칸 중복 · 없는 주차는 strict 를 통과한다** —
  호출 비용을 낸 뒤 `REQUIRED_SECTION_MISSING` · `WEEK_STRUCTURE_MISMATCH` 로 잡힌다.
  이 코드들은 `REPAIRABLE_CODES` 에 없어 **재시도 없이 월간 전체가 실패한다.**
  필수 칸 목록을 스키마에도 넣을지는 #90 설계 쪽 질문이다.
- 모델을 바꾸려면 엘리스에서 그 모델의 주소를 새로 받아야 한다. 주소와 상수가
  어긋나면 `model_not_found` 가 난다 — 키 문제로 오인하기 쉽다.
