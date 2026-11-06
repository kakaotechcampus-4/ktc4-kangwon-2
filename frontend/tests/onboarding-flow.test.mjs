/**
 * 온보딩 흐름의 규칙: 어디로 돌려보내나, 반 수정은 무엇을 보내나.
 * 화면 컴포넌트가 아니라 화면이 부르는 순수 함수와 저장 규칙을 본다.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { registerHooks } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

registerHooks({
  resolve(spec, ctx, next) {
    const url = spec.startsWith("@/")
      ? new URL(`../${spec.slice(2)}.ts`, import.meta.url)
      : spec.startsWith(".") && ctx.parentURL
        ? new URL(spec + ".ts", ctx.parentURL)
        : null;
    if (url && existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true };
    return next(spec, ctx);
  },
});

const flow = await import("../lib/onboarding/flow.ts");
const edit = await import("../lib/onboarding/classEdit.ts");
const { ApiError } = await import("../lib/api/client.ts");

// ── 돌려보내기 ─────────────────────────────────────────────────────────────

test("앞 단계가 비어 있으면 그 단계로 간다", () => {
  assert.equal(flow.startupRedirect("classes", "/onboarding/center"), "/onboarding/center");
  assert.equal(flow.startupRedirect("review", "/onboarding/classes"), "/onboarding/classes");
  assert.equal(flow.startupRedirect("children", "/onboarding/center"), "/onboarding/center");
});

test("앞 단계가 다 찼으면 돌려보내지 않는다", () => {
  assert.equal(flow.startupRedirect("center", "/onboarding/children"), null);
  assert.equal(flow.startupRedirect("review", "/onboarding/children"), null);
});

test("반을 등록하면 그 반의 아이 명단으로 간다", () => {
  assert.equal(
    flow.childrenPathAfterAdd("class-1"),
    "/onboarding/children?class=class-1&back=review",
  );
});

// ── 반 수정 ────────────────────────────────────────────────────────────────

const ENTRY = {
  id: "class-1",
  className: "국화반",
  ageGroup: "4",
  currentChildCount: "",
  teacherName: "박미소",
  selectedAges: [4],
  guardianConsent: true,
  childrenSkipped: false,
  children: [],
};
const WITH_CHILD = { ...ENTRY, children: [{ id: "child-1", name: "가나다" }] };
const apiError = (status, code) =>
  new ApiError(status, { error: { code, message: code, fields: [] } });

function fakeApi({ plan = false, fail } = {}) {
  const calls = { saved: [], plan: 0 };
  return {
    calls,
    api: {
      saveClassEdit: async (entry, patch) => {
        calls.saved.push(patch);
        if (fail) throw fail;
        return {
          ...entry,
          ...patch,
          ageGroup: patch.selectedAges?.length === 1 ? String(patch.selectedAges[0]) : "",
        };
      },
      hasAnnualPlan: async () => {
        calls.plan += 1;
        return plan;
      },
    },
  };
}

test("바뀐 칸만 보낸다", async () => {
  const { api, calls } = fakeApi();
  const result = await edit.submitClassEdit(
    ENTRY,
    { ...edit.draftOf(ENTRY), className: " 해님반 " },
    api,
  );
  assert.equal(result.ok, true);
  assert.deepEqual(calls.saved, [{ className: "해님반" }]);
  assert.equal(calls.plan, 0, "연령이 그대로면 계획안을 묻지 않는다");
});

test("바뀐 것이 없으면 아무것도 보내지 않는다", async () => {
  const { api, calls } = fakeApi();
  const result = await edit.submitClassEdit(ENTRY, edit.draftOf(ENTRY), api);
  assert.equal(result.ok, true);
  assert.deepEqual(calls.saved, []);
});

test("아이가 있는 반의 동의 끄기는 보내기 전에 막는다", async () => {
  const { api, calls } = fakeApi();
  assert.equal(edit.consentOffBlocked(WITH_CHILD, false), true);
  assert.equal(edit.consentOffBlocked(ENTRY, false), false, "아이가 없으면 끌 수 있다");
  const result = await edit.submitClassEdit(
    WITH_CHILD,
    { ...edit.draftOf(WITH_CHILD), guardianConsent: false },
    api,
  );
  assert.deepEqual(result, { ok: false, notice: "아이 명단이 있어 동의를 끌 수 없어요" });
  assert.deepEqual(calls.saved, []);
});

test("서버가 GATE_BLOCKED 로 거절해도 같은 안내를 준다", async () => {
  const { api } = fakeApi({ fail: apiError(409, "GATE_BLOCKED") });
  const result = await edit.submitClassEdit(
    ENTRY,
    { ...edit.draftOf(ENTRY), guardianConsent: false },
    api,
  );
  assert.equal(result.ok, false);
  assert.equal(result.notice, edit.NOTICE_CONSENT_BLOCKED);
});

test("같은 이름의 반이 있으면 이름 칸 아래 말을 준다", async () => {
  const { api } = fakeApi({ fail: apiError(409, "ALREADY_EXISTS") });
  const result = await edit.submitClassEdit(
    ENTRY,
    { ...edit.draftOf(ENTRY), className: "난초반" },
    api,
  );
  assert.deepEqual(result, { ok: false, nameError: "같은 이름의 반이 이미 있어요" });
});

test("연령을 바꿨는데 연간계획안이 있으면 안내한다", async () => {
  const withPlan = fakeApi({ plan: true });
  const draft = { ...edit.draftOf(ENTRY), selectedAges: [4, 5] };
  const result = await edit.submitClassEdit(ENTRY, draft, withPlan.api);
  assert.deepEqual(withPlan.calls.saved, [{ selectedAges: [4, 5] }]);
  assert.equal(result.notice, "연령을 바꿨어요. 이미 만든 계획안의 연령은 바뀌지 않아요");

  const noPlan = fakeApi({ plan: false });
  assert.equal((await edit.submitClassEdit(ENTRY, draft, noPlan.api)).notice, undefined);
});
