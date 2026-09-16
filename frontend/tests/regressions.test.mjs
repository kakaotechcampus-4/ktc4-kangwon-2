import assert from "node:assert/strict";
import { test } from "node:test";
import { registerHooks } from "node:module";
import { fixtureSession, fixtureKey, fixtureAccount } from "./auth-fixture.mjs";

// Resolve the extensionless local import used by the Next.js TypeScript source.
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === "../auth/demo-session")
      return nextResolve("../auth/demo-session.ts", context);
    if (specifier === "./types" && context.parentURL?.endsWith("/onboarding/settings.ts")) {
      return nextResolve("./types.ts", context);
    }
    if (specifier === "./account-store") return nextResolve("./account-store.ts", context);
    return nextResolve(specifier, context);
  },
});
const { loadClassSettings, saveClassSettings, totalChildrenFor, CLASS_SETTINGS_CHANGED } =
  await import("../lib/onboarding/settings.ts");
const { EMPTY_CLASS_SETTINGS, DEFAULT_CHARACTER_MESSAGES } =
  await import("../lib/onboarding/types.ts");
const { formatDateLabel, isValidDate } = await import("../lib/plan-generator/date.ts");

function storage(value) {
  globalThis.window = Object.assign(new EventTarget(), {
    sessionStorage: fixtureSession(),
    localStorage: {
      getItem: (key) => (key === fixtureKey ? fixtureAccount : value),
      setItem: (_key, next) => {
        value = next;
      },
    },
  });
}

test("dashboard count persists and follows saved classroom changes, including zero", () => {
  storage(null);
  assert.equal(totalChildrenFor(loadClassSettings()), 0);
  let changes = 0;
  window.addEventListener(CLASS_SETTINGS_CHANGED, () => {
    changes++;
  });
  const settings = {
    ...EMPTY_CLASS_SETTINGS,
    classes: [
      { ...EMPTY_CLASS_SETTINGS.classes[0], currentChildCount: 25 },
      {
        ...EMPTY_CLASS_SETTINGS.classes[0],
        id: "class-2",
        currentChildCount: "",
        children: [{ id: "a", name: "하늘" }],
      },
    ],
  };
  assert.equal(saveClassSettings(settings), true);
  assert.equal(totalChildrenFor(loadClassSettings()), 26);
  assert.equal(totalChildrenFor(loadClassSettings()), 26);
  settings.classes[0].currentChildCount = 12;
  assert.equal(saveClassSettings(settings), true);
  assert.equal(totalChildrenFor(loadClassSettings()), 13);
  settings.classes[1].currentChildCount = 0;
  assert.equal(saveClassSettings(settings), true);
  assert.equal(totalChildrenFor(loadClassSettings()), 13); // 등록 명단이 1명이므로 참고 인원 0보다 우선
  assert.equal(changes, 3);
});

test("invalid JSON and non-object settings are rejected", () => {
  for (const raw of ["{", "null", "[]", "42", '"text"']) {
    storage(raw);
    assert.equal(loadClassSettings(), null);
  }
});

test("malformed nested values cannot crash classroom and child rendering", () => {
  storage(
    JSON.stringify({
      classes: [
        null,
        {
          className: 1,
          teacherName: null,
          ageGroup: "invalid",
          currentChildCount: -2,
          guardianConsent: "false",
          children: [null, {}, { name: 42 }, { name: " 하늘 " }],
        },
      ],
      characterMessages: { 3: {}, 4: "", 5: "사용자 문구" },
    }),
  );
  const result = loadClassSettings();
  const classroom = result.classes[1];
  assert.equal(classroom.className.trim(), "");
  assert.equal(classroom.teacherName.trim(), "");
  assert.equal(classroom.ageGroup, "");
  assert.equal(classroom.currentChildCount, "");
  assert.equal(classroom.guardianConsent, false);
  assert.deepEqual(
    classroom.children.map((child) => child.name.slice(-2)),
    ["하늘"],
  );
  assert.equal(result.characterMessages[3], DEFAULT_CHARACTER_MESSAGES[3]);
  assert.equal(result.characterMessages[4], "");
  assert.equal(result.characterMessages[5], "사용자 문구");
});

test("legacy settings migrate and valid settings round-trip", () => {
  storage(
    JSON.stringify({ className: "햇살반", ageGroup: "4", children: [{ id: "a", name: "하늘" }] }),
  );
  const migrated = loadClassSettings();
  assert.equal(migrated.classes[0].className, "햇살반");
  assert.equal(migrated.classes[0].ageGroup, "4");
  assert.equal(saveClassSettings(migrated), true);
  assert.deepEqual(loadClassSettings(), migrated);
});

test("duplicate IDs are repaired so editing or deleting targets one entry", () => {
  storage(
    JSON.stringify({
      classes: [
        {
          id: "a",
          children: [
            { id: "x", name: "가" },
            { id: "x", name: "나" },
          ],
        },
        { id: "a" },
      ],
    }),
  );
  const { classes } = loadClassSettings();
  assert.equal(new Set(classes.map((entry) => entry.id)).size, 2);
  assert.equal(new Set(classes[0].children.map((entry) => entry.id)).size, 2);
});

test("storage errors are reported and server rendering needs no window", () => {
  globalThis.window = {
    get localStorage() {
      throw new Error("denied");
    },
  };
  assert.equal(loadClassSettings(), null);
  assert.equal(saveClassSettings(EMPTY_CLASS_SETTINGS), false);
  delete globalThis.window;
  assert.equal(loadClassSettings(), null);
  assert.equal(saveClassSettings(EMPTY_CLASS_SETTINGS), false);
});

test("date-only labels stay the same across timezones and invalid dates are rejected", () => {
  const previous = process.env.TZ;
  try {
    for (const zone of ["America/Los_Angeles", "Asia/Seoul", "UTC"]) {
      process.env.TZ = zone;
      assert.equal(formatDateLabel("2026-09-15"), "9월 15일");
    }
    for (const date of ["", "2026-02-29", "2026-13-01", "bad"]) {
      assert.equal(isValidDate(date), false);
      assert.equal(formatDateLabel(date), "날짜 미선택");
    }
    assert.equal(isValidDate("2028-02-29"), true);
  } finally {
    if (previous === undefined) delete process.env.TZ;
    else process.env.TZ = previous;
  }
});

test("selected ages round-trip independently, including non-contiguous ages and legacy migration", async () => {
  const { selectedAgesFor, ageSelectionLabel } = await import("../lib/onboarding/types.ts");
  for (const ages of [[3], [3, 4], [4, 5], [3, 5], [3, 4, 5]]) {
    storage(null);
    assert.equal(
      saveClassSettings({
        ...EMPTY_CLASS_SETTINGS,
        classes: [{ ...EMPTY_CLASS_SETTINGS.classes[0], selectedAges: ages, ageGroup: "" }],
      }),
      true,
    );
    const c = loadClassSettings().classes[0];
    assert.deepEqual(c.selectedAges, ages);
    assert.equal(ageSelectionLabel(selectedAgesFor(c)), "만 " + ages.join("·") + "세반");
  }
  assert.deepEqual(selectedAgesFor({ ageGroup: "mixed" }), [3, 4, 5]);
  assert.deepEqual(selectedAgesFor({ selectedAges: [], ageGroup: "mixed" }), []);
  storage(JSON.stringify({ classes: [{ ageGroup: "mixed" }] }));
  assert.deepEqual(loadClassSettings().classes[0].selectedAges, [3, 4, 5]);
});
test("registered roster wins over reference count while empty roster falls back", () => {
  for (const [size, expected] of [
    [0, 11],
    [10, 10],
    [12, 12],
  ]) {
    const c = {
      ...EMPTY_CLASS_SETTINGS.classes[0],
      currentChildCount: 11,
      children: Array.from({ length: size }, (_, i) => ({ id: String(i), name: "아동" + i })),
    };
    assert.equal(totalChildrenFor({ ...EMPTY_CLASS_SETTINGS, classes: [c] }), expected);
  }
});
