/* Demo 자체 점검 (선택적 도구).
 *
 * 브라우저 없이 app.js 의 렌더링 결과를 확인한다. 외부 패키지를 쓰지 않고
 * 필요한 만큼만 DOM을 흉내 낸다. 프로젝트 테스트(tests/)와 무관하며
 * pytest가 수집하지 않는다.
 *
 *   node demo-frontend/tools/check_render.js
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const DEMO = path.resolve(__dirname, "..");

/* ------------------------------------------------------------ 최소 DOM 흉내 */

class Node {
  constructor(tag) {
    this.tagName = (tag || "").toUpperCase();
    this.childNodes = [];
    this.attributes = {};
    this._class = "";
    this._text = "";
    this.classList = {
      add: (c) => {
        if (!this._class.split(/\s+/).includes(c)) {
          this._class = (this._class + " " + c).trim();
        }
      },
    };
    this.listeners = {};
  }
  get className() {
    return this._class;
  }
  set className(v) {
    this._class = v || "";
  }
  get textContent() {
    if (this._text) return this._text;
    return this.childNodes.map((c) => c.textContent).join("");
  }
  set textContent(v) {
    this._text = String(v);
    this.childNodes = [];
  }
  get firstChild() {
    return this.childNodes[0] || null;
  }
  appendChild(child) {
    const at = this.childNodes.indexOf(child);
    if (at !== -1) this.childNodes.splice(at, 1);
    this.childNodes.push(child);
    return child;
  }
  removeChild(child) {
    const at = this.childNodes.indexOf(child);
    if (at !== -1) this.childNodes.splice(at, 1);
    return child;
  }
  setAttribute(k, v) {
    this.attributes[k] = String(v);
  }
  getAttribute(k) {
    return this.attributes[k];
  }
  addEventListener(type, fn) {
    (this.listeners[type] = this.listeners[type] || []).push(fn);
  }
  /** 편의: 하위 트리에서 조건에 맞는 노드 수집 */
  find(pred, out = []) {
    for (const c of this.childNodes) {
      if (pred(c)) out.push(c);
      c.find && c.find(pred, out);
    }
    return out;
  }
}

class SelectNode extends Node {
  constructor() {
    super("select");
    this.options = [];
    this.value = "";
  }
  appendChild(opt) {
    this.options.push(opt);
    if (this.options.length === 1) this.value = opt.value;
    return opt;
  }
}

const registry = {};
function register(id, node) {
  node.id = id;
  registry[id] = node;
  return node;
}

const ids = [
  "fixtureBanner",
  "metaMonth",
  "metaStatus",
  "metaClassroom",
  "metaAge",
  "metaTheme",
  "docSubtitle",
  "planHead",
  "planBody",
  "colCount",
  "docFooter",
  "printButton",
];
ids.forEach((id) => register(id, new Node("div")));
register("fixtureSelect", new SelectNode());
const toggle = register("provenanceToggle", new Node("input"));
toggle.checked = false;

const document = {
  readyState: "complete",
  title: "",
  getElementById: (id) => registry[id] || null,
  createElement: (tag) => new Node(tag),
  createTextNode: (t) => {
    const n = new Node("#text");
    n.textContent = t;
    return n;
  },
  addEventListener: () => {},
};

function Option(label, value) {
  const n = new Node("option");
  n.textContent = label;
  n.value = value;
  return n;
}

const sandbox = { window: {}, document, Option, console };
sandbox.window.print = () => {};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

/* ------------------------------------------------------------------ 실행 */

const fixtureFiles = fs
  .readdirSync(path.join(DEMO, "fixtures"))
  .filter((f) => f.endsWith(".js"))
  .sort();

for (const f of fixtureFiles) {
  vm.runInContext(
    fs.readFileSync(path.join(DEMO, "fixtures", f), "utf8"),
    sandbox,
    { filename: f }
  );
}
vm.runInContext(fs.readFileSync(path.join(DEMO, "app.js"), "utf8"), sandbox, {
  filename: "app.js",
});

const FIXTURES = sandbox.window.SSUKSAK_DEMO_FIXTURES;
const select = registry.fixtureSelect;

let failures = 0;
function check(label, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (!ok) failures += 1;
  console.log(
    `  ${ok ? "OK  " : "FAIL"} ${label}: ${JSON.stringify(actual)}` +
      (ok ? "" : ` (기대: ${JSON.stringify(expected)})`)
  );
}

function draw(key, showProvenance) {
  select.value = key;
  toggle.checked = !!showProvenance;
  (select.listeners.change || []).forEach((fn) => fn());
  (toggle.listeners.change || []).forEach((fn) => fn());
}

function stateCounts() {
  const cells = registry.planBody.find(
    (n) => n.tagName === "TD" && n.getAttribute("data-cell-state")
  );
  return cells.reduce((acc, c) => {
    const s = c.getAttribute("data-cell-state");
    acc[s] = (acc[s] || 0) + 1;
    return acc;
  }, {});
}

function columnCount() {
  const headRow = registry.planHead.childNodes[0];
  return headRow ? headRow.childNodes.length - 1 : 0; // 첫 칸은 "구분"
}

function rowLabels() {
  return registry.planBody.childNodes.map((tr) => tr.childNodes[0].textContent);
}

function rowValues(label) {
  const tr = registry.planBody.childNodes.find(
    (r) => r.childNodes[0].textContent === label
  );
  if (!tr) return [];
  return tr.childNodes
    .slice(1)
    .map((td) => (td.childNodes[0] ? td.childNodes[0].textContent : ""));
}

console.log("fixture 로드:", Object.keys(FIXTURES).join(", "));
console.log();

console.log("[1] 2026-09 / 만4세 / DRAFT");
draw("2026-09-draft", false);
check("열 수", columnCount(), 5);
check("행", rowLabels(), ["바깥놀이", "안전교육"]);
check("Cell 상태", stateCounts(), { FILLED: 5, EMPTY_UNRESOLVED: 5 });
check("주제", FIXTURES["2026-09-draft"].theme.value, "우리나라와 세계 여러 나라");
check("바깥놀이", rowValues("바깥놀이"), [
  "무궁화 꽃이 피었습니다",
  "전통놀이",
  "가을 나들이",
  "사방치기",
  "모래 위에 옛 그림을 그려요",
]);
check("안전교육", rowValues("안전교육"), ["", "", "", "", ""]);
check("Badge", registry.metaStatus.childNodes[0].textContent, "초안 DRAFT");
check("열 표시", registry.colCount.textContent, "5열");
console.log();

console.log("[2] 2026-09 / CONFIRMED");
draw("2026-09-confirmed", false);
check("Badge", registry.metaStatus.childNodes[0].textContent, "확정 CONFIRMED");
check("Cell 상태 유지", stateCounts(), { FILLED: 5, EMPTY_UNRESOLVED: 5 });
console.log();

console.log("[3] 2026-09 / Activity Reference 미연결");
draw("2026-09-no-activity", false);
check("Cell 상태", stateCounts(), { EMPTY_VALID: 5, EMPTY_UNRESOLVED: 5 });
check("바깥놀이 비어 있음", rowValues("바깥놀이"), ["", "", "", "", ""]);
console.log();

console.log("[4] 2026-03 / 4주");
draw("2026-03-draft", false);
check("열 수", columnCount(), 4);
check("Cell 상태", stateCounts(), { FILLED: 4, EMPTY_UNRESOLVED: 4 });
check("열 표시", registry.colCount.textContent, "4열");
console.log();

console.log("[5] Activity 근거 토글");
draw("2026-09-draft", true);
const shown = registry.planBody
  .find((n) => n.className && n.className.indexOf("cell__provenance") !== -1)
  .filter((n) => n.className.indexOf("is-hidden") === -1);
check("근거 표시 칸 수", shown.length, 5);
check(
  "첫 칸 근거에 activity_id 포함",
  shown[0].textContent.indexOf("act_outdoor_mugunghwa_flower_game") !== -1,
  true
);
check(
  "첫 칸 근거에 catalog version 포함",
  shown[0].textContent.indexOf("activity-reference-v0.2.0") !== -1,
  true
);
draw("2026-09-draft", false);
const hidden = registry.planBody
  .find((n) => n.className && n.className.indexOf("cell__provenance") !== -1)
  .filter((n) => n.className.indexOf("is-hidden") !== -1);
check("토글 해제 시 숨김", hidden.length, 5);
console.log();

console.log(failures === 0 ? "모두 통과" : `${failures}건 실패`);
process.exit(failures === 0 ? 0 : 1);
