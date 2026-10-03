/**
 * 화면 4상태 공용 처리 (components/workspace/WorkspaceViewState.tsx).
 *
 * 컴포넌트는 hook 을 쓰지 않아서, 실제 소스를 babel 로 옮긴 뒤 함수로 직접 부른다.
 * React 와 CSS module 은 스텁이다 — 여기서 보는 것은 "어떤 상태에 무엇을 그리나" 다.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire, registerHooks } from "node:module";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

registerHooks({
  resolve(spec, ctx, next) {
    if (spec.startsWith(".") && ctx.parentURL) {
      const u = new URL(spec + ".ts", ctx.parentURL);
      if (existsSync(fileURLToPath(u))) return { url: u.href, shortCircuit: true };
    }
    return next(spec, ctx);
  },
});

const { ApiError, invalidFields } = await import("../lib/api/client.ts");
const require = createRequire(import.meta.url);
const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8").replace(/\r\n/g, "\n");

const compiled = require("next/dist/compiled/babel/core").transformSync(
  read("../components/workspace/WorkspaceViewState.tsx"),
  {
    filename: "WorkspaceViewState.tsx",
    babelrc: false,
    configFile: false,
    presets: [
      [require("next/dist/compiled/babel/preset-env"), { targets: { node: "current" } }],
      [require("next/dist/compiled/babel/preset-react"), { runtime: "automatic" }],
      require("next/dist/compiled/babel/preset-typescript"),
    ],
  },
).code;

const jsx = (type, props) => ({ type, props });
const modules = {
  "react/jsx-runtime": { jsx, jsxs: jsx, Fragment: "fragment" },
  // Message 는 실제 공용 컴포넌트다. 여기서는 "무엇이 그려졌나" 만 보면 된다.
  "./WorkspaceUI": { Message: "message", ws: { loading: "loading", fieldError: "fieldError" } },
};
const module_ = { exports: {} };
new Function("require", "module", "exports", compiled)(
  (name) => {
    assert.ok(name in modules, `unhandled import: ${name}`);
    return modules[name];
  },
  module_,
  module_.exports,
);
const { WorkspaceViewState, FieldError, fieldErrorProps, fieldErrorId } = module_.exports;

/** 렌더 결과를 평평하게 편다. 문자열과 노드가 섞여 나온다. */
function flatten(node) {
  if (node === null || node === undefined || node === false || node === true) return [];
  if (Array.isArray(node)) return node.flatMap(flatten);
  if (typeof node === "object") return [node, ...flatten(node.props?.children)];
  return [node];
}
const texts = (node) => flatten(node).filter((part) => typeof part === "string");
const nodes = (node) => flatten(node).filter((part) => typeof part === "object");

const SUCCESS = jsx("ok", { children: "성공 본문" });
const EMPTY = jsx("empty", { children: "비었음 본문" });
const view = (over) =>
  WorkspaceViewState({ status: "ready", loading: "불러오고 있어요.", children: SUCCESS, ...over });

test("loading 은 aria-busy 와 화면이 준 문구를 보여주고 본문을 그리지 않는다", () => {
  const tree = view({ status: "loading", empty: EMPTY });
  assert.equal(tree.props["aria-busy"], "true");
  assert.ok(texts(tree).includes("불러오고 있어요."));
  assert.equal(nodes(tree).includes(SUCCESS), false);
  assert.equal(nodes(tree).includes(EMPTY), false);
});

test("error 는 서버 문구를 그대로 alert 로 넘긴다", () => {
  const tree = view({ status: "error", error: "요청을 처리하지 못했어요.", empty: EMPTY });
  assert.equal(tree.type, "message");
  assert.equal(tree.props.error, true);
  assert.equal(tree.props.children, "요청을 처리하지 못했어요.");
  assert.equal(nodes(tree).includes(SUCCESS), false);
});

test("empty 는 화면이 준 그대로 그리고 본문을 대신한다", () => {
  const tree = view({ empty: EMPTY });
  assert.ok(nodes(tree).includes(EMPTY));
  assert.equal(nodes(tree).includes(SUCCESS), false);
});

test("success 는 children 을 그린다. empty 가 false 면 비어 있지 않다", () => {
  for (const empty of [false, undefined]) {
    const tree = view({ empty });
    assert.ok(nodes(tree).includes(SUCCESS), String(empty));
  }
});

test("ApiError 의 서버 message 가 그대로 error 로 전달된다", () => {
  const body = {
    error: { code: "VALIDATION_FAILED", message: "입력값을 확인해주세요.", fields: [] },
  };
  const error = new ApiError(422, body);
  assert.equal(error.message, "입력값을 확인해주세요.");
  // 화면은 이 문장을 다시 쓰지 않는다.
  assert.equal(view({ status: "error", error: error.message }).props.children, error.message);
});

const FIELDS = (fields) =>
  new ApiError(422, { error: { code: "VALIDATION_FAILED", message: "확인해주세요.", fields } });
const MAP = { class_id: "classId", fact: "fact", sources: "sources", source_ids: "sources" };

test("VALIDATION_FAILED 의 fields 만 화면 입력 이름으로 바꾼다", () => {
  assert.deepEqual(invalidFields(FIELDS(["class_id", "fact"]), MAP), ["classId", "fact"]);
  // 점 표기는 앞부분을 본다. 같은 묶음이 여러 번 와도 한 번만 남는다.
  assert.deepEqual(invalidFields(FIELDS(["sources.3", "sources.7", "source_ids"]), MAP), [
    "sources",
  ]);
  // 화면에 없는 칸은 버린다. 서버 이름을 그대로 보여주면 어디를 고칠지 모른다.
  assert.deepEqual(invalidFields(FIELDS(["school_year"]), MAP), []);
});

test("VALIDATION_FAILED 가 아니거나 모양이 다르면 아무 칸도 짚지 않는다", () => {
  const other = new ApiError(409, {
    error: { code: "STALE_WRITE", message: "", fields: ["fact"] },
  });
  assert.deepEqual(invalidFields(other, MAP), []);
  assert.deepEqual(invalidFields(FIELDS("fact"), MAP), []);
  assert.deepEqual(invalidFields(FIELDS([1, null, "fact"]), MAP), ["fact"]);
  assert.deepEqual(invalidFields(new ApiError(422, "그냥 문자열"), MAP), []);
  assert.deepEqual(invalidFields(new Error("네트워크"), MAP), []);
});

test("짚힌 칸만 alert 와 aria 연결을 받는다", () => {
  const marker = FieldError({ name: "fact", invalid: ["fact"] });
  assert.equal(marker.props.role, "alert");
  assert.equal(marker.props.id, fieldErrorId("fact"));
  assert.equal(fieldErrorProps("fact", ["fact"])["aria-describedby"], marker.props.id);
  assert.equal(fieldErrorProps("fact", ["fact"])["aria-invalid"], true);

  assert.equal(FieldError({ name: "fact", invalid: ["context"] }), null);
  const clean = fieldErrorProps("fact", ["context"]);
  assert.equal(clean["aria-invalid"], undefined);
  assert.equal(clean["aria-describedby"], undefined);
});

// 화면은 JSX 라 이 환경에서 렌더할 수 없다. 아래는 소스로 확인한다.
const records = () => read("../components/workspace/RecordsPage.tsx");
const documents = () => read("../components/workspace/DocumentsPage.tsx");
const between = (source, from, to) => {
  const start = source.indexOf(from);
  assert.ok(start > -1, from);
  const end = source.indexOf(to, start);
  assert.ok(end > start, to);
  return source.slice(start, end);
};

test("관찰 기록 빈 상태 제목은 계약 문구 그대로다", () => {
  assert.ok(records().includes('<Empty title="아직 남긴 기록이 없어요">'));
});

test("두 화면이 로딩·빈 상태·오류를 직접 분기하지 않는다", () => {
  for (const [name, source] of [
    ["RecordsPage", records()],
    ["DocumentsPage", documents()],
  ]) {
    assert.ok(source.includes("<WorkspaceViewState"), name);
    assert.equal(source.includes('aria-busy="true"'), false, `${name}: 로딩 분기가 남아 있다`);
    assert.equal(source.includes("ws.loading"), false, `${name}: 로딩 분기가 남아 있다`);
  }
});

test("저장이 실패해도 관찰 기록 입력값을 지우지 않는다", () => {
  const submit = between(records(), "async function submit(", "async function remove(");
  const caught = between(submit, "} catch (e) {", "} finally {");
  for (const setter of [
    "setFact(",
    "setContext(",
    "setClassId(",
    "setChildId(",
    "setDate(",
    "setDomain(",
    "setEditId(",
  ])
    assert.equal(caught.includes(setter), false, setter);
  // 성공했을 때만 비운다.
  assert.ok(submit.includes('setFact("")'));
});

test("생성이 실패해도 문서 작성 조건과 근거 선택을 지우지 않는다", () => {
  const generate = between(documents(), "async function generate(", "const serverActions");
  const caught = between(generate, "} catch (e) {", "} finally {");
  for (const setter of [
    "setSelected(",
    "setClassId(",
    "setChildId(",
    "setStart(",
    "setEnd(",
    "setKind(",
    "setMode(",
  ])
    assert.equal(caught.includes(setter), false, setter);
  assert.ok(generate.includes("setSelected([])"));
});

test("짚을 수 있는 칸은 모두 서버 계약의 칸 이름에서 온다", () => {
  for (const [name, source] of [
    ["RecordsPage", records()],
    ["DocumentsPage", documents()],
  ]) {
    const map = between(source, "const FIELD_INPUT: Record<string, string> = {", "};");
    const inputs = new Set([...map.matchAll(/:\s*"([^"]+)"/g)].map((m) => m[1]));
    const marked = [...source.matchAll(/<FieldError name="([^"]+)"/g)].map((m) => m[1]);
    const linked = [...source.matchAll(/fieldErrorProps\("([^"]+)"/g)].map((m) => m[1]);
    assert.ok(marked.length > 0, name);
    assert.deepEqual(new Set(marked), new Set(linked), `${name}: 표시와 aria 연결이 어긋난다`);
    for (const field of marked) assert.ok(inputs.has(field), `${name}: ${field}`);
  }
});
