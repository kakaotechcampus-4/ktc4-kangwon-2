"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { getMe } from "@/lib/api/auth";
import { getClasses } from "@/lib/api/classes";
import { isUnauthenticated } from "@/lib/api/client";
import { classServerId } from "@/lib/api/onboarding";
import {
  createRoutine,
  deleteRoutine,
  listRoutines,
  routineTime,
  routineTimeValue,
  trackRoutineMutation,
  updateRoutine,
  waitForRoutineScope,
  type ApiRoutine,
  type RoutineInput,
  type RoutineReviewImpact,
} from "@/lib/api/routines";
import type { ApiClass } from "@/lib/api/types";
import { useClientState } from "@/lib/hooks/use-client-state";
import { chosenClassFor, loadClassSettings } from "@/lib/onboarding/settings";
import { today, validDate } from "@/lib/workspace/model";
import { routinesQuery, routinesScope } from "@/lib/workspace/routines-route";
import { WorkspacePage, Empty, Message, ws } from "./WorkspaceUI";
import { WorkspaceViewState, type ViewStatus } from "./WorkspaceViewState";

const CLASSES_FAILED = "반 목록을 불러오지 못했어요. 잠시 뒤 다시 열어주세요.";
// 서버 routine_records.name 이 50자다. 더 보내면 422 다 (§10-1).
const NAME_MAX = 50;
/** 그날 적은 게 하나도 없을 때 깔아 두는 줄 수 (S-J1). */
const BLANK_ROWS = 5;
const NAME_REQUIRED = "일과 이름을 적어 주세요.";
const TIME_BACKWARDS = "끝나는 시간이 시작보다 빨라요.";
const HAS_PROBLEM = "적다 만 줄이 있어요. 표시된 줄을 확인해주세요.";
const SAVED = "저장했어요.";
const NO_YESTERDAY = "어제 적은 일과가 없어요.";
const UNKNOWN_CLASS = "주소에 적힌 반을 찾을 수 없어요. 반을 골라주세요.";

function messageFor(error: unknown) {
  if (isUnauthenticated(error)) return "로그인이 필요해요. 다시 로그인한 뒤 이용해주세요.";
  return error instanceof Error ? error.message : "요청을 처리하지 못했어요.";
}

/** 화면 한 줄. 전부 문자열이다 — `<input>` 이 주는 모양 그대로 들고 있는다. */
interface Row {
  key: string;
  /** 서버에 있는 줄이면 그 id. 아직 없는 줄은 `null` 이다. */
  id: number | null;
  start: string;
  end: string;
  name: string;
  plan: string;
  execution: string;
}

type Field = Exclude<keyof Row, "key" | "id">;

/**
 * 이 화면의 초안 전체 (FR-402).
 *
 * **저장을 누르기 전에는 서버에 아무것도 보내지 않는다.** 줄을 더하고 지우고 끌어서
 * 옮기는 것은 전부 여기서만 일어난다. `saved` 는 마지막으로 읽은 서버 모습이라
 * 저장할 때 무엇이 바뀌었는지 이것과 비교해서 안다.
 */
interface Draft {
  key: string;
  rows: Row[];
  /** 지우기로 표시한 **서버 줄**. 저장할 때 한꺼번에 `DELETE` 한다. */
  removed: number[];
  saved: Record<number, ApiRoutine>;
  /** 부분 성공 뒤 재시도해도 이번 저장에서 발생한 영향을 잃지 않는다. */
  reviewImpact?: RoutineReviewImpact;
}

/** 한 번의 조회 결과. `key` 가 화면 조건과 다르면 지금 조건으로 받은 값이 아니다. */
interface Loaded {
  key: string;
  rows: ApiRoutine[];
  error: string;
}

// 화면 안에서만 쓰는 줄 번호. 같은 렌더 안에서 겹치지만 않으면 된다.
let nextRowKey = 0;
const blankRow = (): Row => ({
  key: `new:${(nextRowKey += 1)}`,
  id: null,
  start: "",
  end: "",
  name: "",
  plan: "",
  execution: "",
});
const serverRow = (row: ApiRoutine): Row => ({
  key: `server:${row.id}`,
  id: row.id,
  start: routineTime(row.start),
  end: routineTime(row.end),
  name: row.name,
  plan: row.plan,
  execution: row.execution,
});

const draftFrom = (key: string, rows: ApiRoutine[]): Draft => ({
  key,
  // 그날 적은 게 없으면 빈 줄 다섯. **있으면 거기에 빈 줄을 더하지 않는다** (S-J1).
  rows: rows.length ? rows.map(serverRow) : Array.from({ length: BLANK_ROWS }, blankRow),
  removed: [],
  saved: Object.fromEntries(rows.map((row) => [row.id, row])),
});

/** 한 칸이라도 적혀 있으면 「쓰던 줄」이다. 통째로 빈 줄만 보내지 않는다 (FR-402 예외). */
const filled = (row: Row) =>
  Boolean(row.start || row.end || row.name.trim() || row.plan.trim() || row.execution.trim());

/** 서버가 막는 것과 같은 것만 미리 본다 — 나머지는 서버 문구를 그대로 보여준다. */
function problemWith(row: Row): string {
  if (!row.name.trim()) return NAME_REQUIRED;
  if (row.name.trim().length > NAME_MAX) return `일과 이름은 ${NAME_MAX}자까지예요.`;
  if (row.start && row.end && row.start >= row.end) return TIME_BACKWARDS;
  return "";
}

/** 분 단위 입력을 건드리지 않았다면 서버의 초도 보존한다 — 같은 position의 정렬 근거다. */
const timeInput = (value: string, saved?: string | null) =>
  saved && routineTime(saved) === value && saved !== `${value}:00`
    ? saved
    : routineTimeValue(value);

/** `position` 은 화면 순서 그대로다 — 끌어서 옮기면 그 줄이 `PUT` 대상이 된다. */
const inputOf = (row: Row, position: number, date: string, saved?: ApiRoutine): RoutineInput => ({
  date,
  position,
  start: timeInput(row.start, saved?.start),
  end: timeInput(row.end, saved?.end),
  name: row.name.trim(),
  plan: row.plan,
  execution: row.execution,
});

const sameInput = (a: RoutineInput, b: RoutineInput) =>
  (Object.keys(a) as (keyof RoutineInput)[]).every((key) => a[key] === b[key]);

const savedInput = (row: ApiRoutine) => inputOf(serverRow(row), row.position, row.date, row);

/** 끌어 놓은 자리로 한 줄을 옮긴다. */
function moved(rows: Row[], from: number, to: number) {
  if (from === to || from < 0 || to < 0 || from >= rows.length || to >= rows.length) return rows;
  const next = [...rows];
  next.splice(to, 0, next.splice(from, 1)[0]);
  return next;
}

const without = (saved: Draft["saved"], id: number) => {
  const next = { ...saved };
  delete next[id];
  return next;
};

/** 어제. `date` 는 시간대가 없는 `YYYY-MM-DD` 라 UTC 로 더해도 하루가 밀리지 않는다. */
function previousDay(date: string) {
  const at = new Date(`${date}T00:00:00Z`);
  at.setUTCDate(at.getUTCDate() - 1);
  return at.toISOString().slice(0, 10);
}

const NO_QUERY = { date: "", classId: null };
/** canonical route 의 `?date=&class_id=` (screen-spec S-J1). */
const fromQuery = () =>
  typeof window === "undefined" ? NO_QUERY : routinesScope(window.location.search);

/** 서버가 하루 안에서 쓰는 순서 그대로다 — `position` · 시작 시간(없으면 뒤) · `id` (§10-1). */
function byServerOrder(a: ApiRoutine, b: ApiRoutine) {
  if (a.position !== b.position) return a.position - b.position;
  if (a.start !== b.start) {
    if (a.start === null) return 1;
    if (b.start === null) return -1;
    return a.start < b.start ? -1 : 1;
  }
  return a.id - b.id;
}

/**
 * 보낼 `position`.
 *
 * **번호 자체로 판단하지 않는다.** 서버 번호는 `0,0,0` 처럼 겹칠 수 있고(지난 데이터가 그렇다),
 * 그걸 `0,1,2` 로 고쳐 쓰면 교사가 건드리지도 않은 줄이 전부 `PUT` 대상이 된다. 판단은
 * **줄의 앞뒤**로 한다 — 서버가 준 순서와 화면 순서가 같으면 번호를 그대로 둔다.
 *
 * 맨 뒤에 새 줄만 붙었으면 기존 줄은 그대로 두고 마지막 번호 뒤로 이어 붙인다.
 * 중간 삽입·끌기에서는 그대로 둘 수 있는 서버 줄을 최대한 남기고 그 사이만 채운다.
 * 새 줄끼리 시작 시간이 같으면 서로 다른 번호를 예약한다 — 앞 POST만 실패해도,
 * 나중에 생긴 더 큰 id 때문에 재시도한 줄이 성공한 줄 뒤로 밀리지 않아야 한다.
 */
function positionsFor(rows: Row[], saved: Draft["saved"]): number[] {
  const known = rows.map((row) => (row.id === null ? null : (saved[row.id] ?? null)));
  const servers = known.filter((row): row is ApiRoutine => row !== null);
  const inOrder = [...servers].sort(byServerOrder);
  const kept =
    servers.every((row, i) => row.id === inOrder[i].id) &&
    known.every((row, i) => row !== null || i >= servers.length);
  const last = servers.length ? inOrder[servers.length - 1].position : -1;
  if (kept && Number.isSafeInteger(last + rows.length - servers.length)) {
    let next = last;
    return known.map((row) => (row ? row.position : (next += 1)));
  }

  // 같은 position에 둘 수 있는지는 start(NULLS LAST) → id로 정한다.
  // 새 id는 기존 id보다 크다. 같은 시간의 새 줄끼리는 실패 순서와 무관한 번호를 예약한다.
  const starts = rows.map((row, i) => {
    const value = timeInput(row.start, known[i]?.start);
    return value?.length === 5 ? `${value}:00` : value;
  });
  const gaps = [0];
  for (let i = 1; i < rows.length; i++) {
    const before = rows[i - 1];
    const after = rows[i];
    const a = starts[i - 1];
    const b = starts[i];
    const tieFits =
      a !== b
        ? b === null || (a !== null && a < b)
        : before.id !== null && (after.id === null || before.id < after.id);
    gaps[i] = gaps[i - 1] + (tieFits ? 0 : 1);
  }

  // position - gaps가 줄 순서대로 줄어들지 않으면 Backend 정렬을 만족한다.
  // 그대로 둘 수 있는 baseline을 최대한 유지한다. 이미 글자를 고쳐 PUT이 필요한 줄보다
  // 아무것도 고치지 않은 줄을 우선 남기고, 그 사이의 번호만 조정한다.
  const ceiling = Number.MAX_SAFE_INTEGER - (gaps.at(-1) ?? 0);
  const levels = known.map((row, i) => (row ? row.position - gaps[i] : -1));
  const scores = rows.map(() => 0);
  const previous = rows.map(() => -1);
  let best = -1;
  for (let i = 0; i < rows.length; i++) {
    const was = known[i];
    if (!was || levels[i] < 0 || levels[i] > ceiling) continue;
    const unchanged = sameInput(inputOf(rows[i], was.position, was.date, was), savedInput(was));
    const weight = (unchanged ? rows.length + 1 : 0) + 1;
    scores[i] = weight;
    for (let j = 0; j < i; j++) {
      if (scores[j] && levels[j] <= levels[i] && scores[j] + weight > scores[i]) {
        scores[i] = scores[j] + weight;
        previous[i] = j;
      }
    }
    if (best === -1 || scores[i] > scores[best]) best = i;
  }
  const anchors: number[] = [];
  for (let i = best; i !== -1; i = previous[i]) anchors.unshift(i);

  let anchor = 0;
  let level = 0;
  const positions: number[] = [];
  for (let i = 0; i < rows.length; i++) {
    const limit = anchor < anchors.length ? levels[anchors[anchor]] : ceiling;
    if (i === anchors[anchor]) {
      level = levels[i];
      anchor += 1;
    } else {
      // 빈 번호가 있으면 쓰고, 없으면 start/id로 안전하게 정렬되는 같은 번호를 쓴다.
      const preferred = known[i]?.position ?? (i ? positions[i - 1] + 1 : 0);
      level = Math.min(limit, Math.max(level, preferred - gaps[i]));
    }
    positions.push(level + gaps[i]);
  }
  return positions;
}

/**
 * 일과 기록 — 반 하루의 일과를 한 줄씩 적는다 (screen-spec S-J1 · FR-402 · ADR-025).
 *
 * **AI 가 쓰지 않는다.** 활동실행은 있었던 일이라 모델이 채우면 위조다 (CLAUDE.md 문서 5분류).
 * 여기 적은 줄이 §11 일일 보육일지의 근거(`source_ids`)가 된다 — 관찰 기록이 아니다.
 *
 * **저장은 교사가 누를 때만 한다.** 줄을 더하고 지우고 끌어서 옮기는 동안 서버는 아무것도
 * 모른다. 저장을 누르면 마지막으로 읽은 서버 모습과 비교해 `POST` · `PUT` · `DELETE` 를
 * 한 번에 보낸다.
 */
export default function RoutinesPage() {
  const router = useRouter();
  // hydration 전에는 주소를 읽지 않는다 — 서버 HTML 과 어긋나지 않게 한다.
  const [query] = useClientState(fromQuery, NO_QUERY);
  // **교사가 고른 반만** 쓴다. 고른 적이 없으면 첫 반을 대신 고르지 않는다 (FR-402 · FR-405).
  const [primaryClass] = useClientState(
    () => classServerId(chosenClassFor(loadClassSettings())?.id ?? ""),
    null,
  );
  // null = 아직 안 왔다. 상태를 따로 들지 않고 값에서 읽는다 (react-hooks/set-state-in-effect).
  const [classList, setClassList] = useState<{ items: ApiClass[]; error: string } | null>(null);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [pickedClass, setPickedClass] = useState<number | null>(null);
  const [pickedDate, setPickedDate] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  const [busy, setBusy] = useState("");
  /**
   * 지금 요청이 도는 중인가. `busy` 는 **다시 그려져야** 버튼이 잠기므로, 그 사이에 한 번 더
   * 눌리면 같은 저장이 두 번 간다. 렌더를 기다리지 않는 자물쇠가 따로 필요하다.
   */
  const running = useRef(false);
  // 문구에 「어느 화면에서 났나」를 붙여 둔다. 지난 날짜의 실패가 지금 날짜에 뜨면 안 된다.
  const [message, setMessage] = useState<{ at: string; text: string; error?: boolean } | null>(
    null,
  );
  /**
   * 이 화면에 몇 번째로 들어왔나. 반 · 날짜를 바꾸거나 다시 읽을 때마다 올린다.
   *
   * **반·날짜 문자열만으로는 부족하다.** A → B → A 로 돌아오면 열쇠가 같아져서, 첫 A 에서
   * 보낸 느린 저장의 응답이 두 번째 A 화면에 들어온다. 방문 번호는 되돌아가지 않는다.
   */
  const [visit, setVisit] = useState(0);
  const revisit = () => setVisit((n) => n + 1);

  const classes = classList?.items;
  const known = (id: number | null) =>
    id !== null && classes?.some((c) => c.id === id) ? id : null;
  // 주소가 모르는 반을 가리켰다. **첫 반으로 조용히 바꾸지 않는다** — 고르라고 한다.
  const unknownClass = query.classId !== null && !!classes && known(query.classId) === null;
  /**
   * 이 화면이 보는 반. 교사가 고른 반 → 주소 → 주 반 순이고, **반 목록에 있는 번호만** 쓴다.
   * 셋 다 없으면 `null` 이다 — 첫 반을 대신 고르지 않는다 (FR-405).
   */
  const classId =
    known(pickedClass) ?? (unknownClass ? null : (known(query.classId) ?? known(primaryClass)));
  // 주소에 날짜가 없으면 오늘이다 (S-J1).
  const date = pickedDate ?? (query.date || today());

  /** 이 반·이 날짜. 방문이 달라도 **같은 자료**를 가리킨다 — 저장 대기줄의 칸이다. */
  const scope = `${classId}|${date}`;
  // 조회 하나를 가리키는 열쇠. 화면 조건과 다르면 지금 조건으로 받은 값이 아니다.
  const key = `${scope}|${visit}`;

  // Update at commit, before an old promise can change the newly displayed visit's state.
  const active = useRef<{ key: string; mounted: boolean }>({ key, mounted: false });
  useLayoutEffect(() => {
    active.current = { key, mounted: true };
    return () => {
      active.current.mounted = false;
    };
  }, [key]);

  useEffect(() => {
    let stale = false;
    getMe()
      .then((me) => (me.center_id ? getClasses(me.center_id) : { items: [] }))
      .then(({ items }) => !stale && setClassList({ items, error: "" }))
      .catch(() => !stale && setClassList({ items: [], error: CLASSES_FAILED }));
    return () => {
      stale = true;
    };
  }, []);

  useEffect(() => {
    if (classId === null || !validDate(date)) return;
    let stale = false;
    // **이 반·날짜의 저장이 끝난 뒤에 읽는다.** 먼저 읽으면 커밋 전 값을 받아, 방금 저장한
    // 값이 사라진 화면이 된다. 하루치다 — from 과 to 가 같은 날이다.
    void (async () => {
      try {
        await waitForRoutineScope(scope);
        if (stale) return;
        const items = await listRoutines({ class_id: classId, from: date, to: date });
        if (!stale) setLoaded({ key, rows: items, error: "" });
      } catch (e) {
        if (!stale) setLoaded({ key, rows: [], error: messageFor(e) });
      }
    })();
    return () => {
      stale = true;
    };
  }, [classId, date, scope, key]);

  /**
   * 보고 있는 반 · 날짜를 주소에 적어 둔다 (P1-3). 적어 두지 않으면 반을 바꿔 저장한 뒤
   * 새로고침했을 때 주소에 남은 **옛 반**으로 되돌아간다 — 저장은 됐는데 안 된 것처럼 보인다.
   *
   * `replaceState` 다. 거르기는 다른 화면으로 가는 것이 아니라서 history 를 늘리면
   * 뒤로가기가 반 고른 횟수만큼 걸린다. 늘리지 않으므로 주소와 화면이 어긋날 칸도 없다.
   *
   * **반을 못 정했으면 손대지 않는다.** 목록이 오기 전과 주소의 반을 못 찾은 때가 둘 다
   * `null` 인데, 그때 `class_id` 를 지우면 「반을 골라주세요」가 새로고침에 사라지고
   * 주 반이 조용히 열린다 (FR-405).
   */
  useEffect(() => {
    if (classId === null || !validDate(date)) return;
    const want = routinesQuery(classId, date);
    if (window.location.search !== want) window.history.replaceState(null, "", want);
  }, [classId, date]);

  // 지금 반·날짜로 받은 값만 쓴다. 날짜를 바꾸는 동안 어제 일과가 남지 않는다.
  const current = loaded?.key === key ? loaded : null;
  // 새로 읽어 온 하루가 있으면 그 위에 초안을 세운다. **같은 열쇠면 손대지 않는다** —
  // 다시 그릴 때마다 세우면 교사가 적던 글이 날아간다.
  if (current && !current.error && draft?.key !== key) {
    setDraft(draftFrom(key, current.rows));
    // 새 서버 snapshot 이다 — 지난 반·날짜에서 띄운 안내는 이 줄들과 상관이 없다.
    // (같은 화면에서 저장이 실패한 경우는 여기로 오지 않는다. 그때 안내는 그대로 남는다.)
    setErrors({});
  }
  const now = draft?.key === key ? draft : null;
  const rows = now?.rows ?? [];

  /** 저장을 시작한 화면(`at`)이 아직 그 화면일 때만 초안을 고친다. */
  const patch = (at: string, change: (draft: Draft) => Draft) =>
    setDraft((prev) => (prev && prev.key === at ? change(prev) : prev));

  const editRow = (rowKey: string, field: Field, value: string) =>
    patch(key, (d) => ({
      ...d,
      rows: d.rows.map((row) => (row.key === rowKey ? { ...row, [field]: value } : row)),
    }));

  /** 「+ 줄 추가」는 화면에만 더한다. 서버는 저장할 때 안다 (S-J1 동작표). */
  const addRow = () => patch(key, (d) => ({ ...d, rows: [...d.rows, blankRow()] }));

  /** 지우기도 화면에서만 한다. **저장을 누르기 전에는 `DELETE` 를 보내지 않는다.** */
  const removeRow = (rowKey: string) =>
    patch(key, (d) => {
      const row = d.rows.find((r) => r.key === rowKey);
      return {
        ...d,
        rows: d.rows.filter((r) => r.key !== rowKey),
        removed: row?.id == null ? d.removed : [...d.removed, row.id],
      };
    });

  /** 그 줄만 마지막으로 읽은 서버 모습으로 되돌린다. 서버에 없던 줄은 비운다 (OLD TASK 2). */
  const revertRow = (rowKey: string) => {
    patch(key, (d) => ({
      ...d,
      rows: d.rows.map((row) => {
        if (row.key !== rowKey) return row;
        const was = row.id === null ? null : d.saved[row.id];
        return { ...(was ? serverRow(was) : blankRow()), key: row.key, id: row.id };
      }),
    }));
    setErrors((prev) => ({ ...prev, [rowKey]: "" }));
  };

  /** 서버에 적힌 것과 다른가. 자리(`position`)는 보지 않는다 — 그건 줄 단위 되돌리기가 아니다. */
  const dirtyRow = (row: Row) => {
    const was = row.id === null ? null : now?.saved[row.id];
    return was
      ? !sameInput(inputOf(row, 0, date, was), inputOf(serverRow(was), 0, date, was))
      : filled(row);
  };

  const reorder = (from: number | null, to: number) => {
    if (from === null) return;
    patch(key, (d) => ({ ...d, rows: moved(d.rows, from, to) }));
  };

  /**
   * 초안과 마지막 서버 모습을 비교해 한 번에 보낸다 (FR-402 처리 3).
   *
   * 돌려주는 값은 「보내야 할 요청이 전부 성공했나」다. 일부가 실패하면 **초안을 비우지
   * 않는다** — 성공한 것만 초안에 반영해 두어, 다시 눌러도 같은 줄을 두 번 만들지 않는다.
   */
  async function commit(): Promise<RoutineReviewImpact | null> {
    const at = key;
    if (classId === null || !now) return null;

    // 쓰던 줄인데 이름이 없으면 **아무것도 보내지 않고** 그 줄에 안내를 띄운다 (FR-402 예외).
    const problems: Record<string, string> = {};
    for (const row of now.rows) {
      if (!filled(row)) continue;
      const problem = problemWith(row);
      if (problem) problems[row.key] = problem;
    }
    setErrors(problems);
    if (Object.keys(problems).length) {
      setMessage({ at, text: HAS_PROBLEM, error: true });
      return null;
    }
    setMessage(null);

    let ok = true;
    const affected = new Set(now.reviewImpact?.affected_document_ids);
    const newlyStale = new Set(now.reviewImpact?.newly_stale_document_ids);
    const impact = (): RoutineReviewImpact => ({
      affected_document_ids: [...affected],
      newly_stale_document_ids: [...newlyStale],
    });
    const rememberImpact = (value?: RoutineReviewImpact) => {
      value?.affected_document_ids.forEach((id) => affected.add(id));
      value?.newly_stale_document_ids.forEach((id) => newlyStale.add(id));
      patch(at, (d) => ({ ...d, reviewImpact: impact() }));
    };
    const fail = (e: unknown) => {
      ok = false;
      setMessage({ at, text: messageFor(e), error: true });
    };

    for (const id of now.removed) {
      try {
        const result = await trackRoutineMutation(
          scope,
          deleteRoutine(id, { includeImpact: true }),
        );
        rememberImpact(result?.review_impact);
        patch(at, (d) => ({
          ...d,
          removed: d.removed.filter((x) => x !== id),
          saved: without(d.saved, id),
        }));
      } catch (e) {
        fail(e);
      }
    }
    // 통째로 빈 줄은 보내지 않는다. 기존 기록 삭제도 명시적인 「줄 지우기」로만 보낸다.
    const sending = now.rows.filter(filled);
    const positions = positionsFor(sending, now.saved);
    for (const [index, row] of sending.entries()) {
      const was = row.id === null ? undefined : now.saved[row.id];
      const body = inputOf(row, positions[index], date, was);
      try {
        if (row.id === null) {
          const made = await trackRoutineMutation(scope, createRoutine(classId, body));
          // **다시 눌렀을 때 또 만들지 않게** 이 줄에 서버 번호를 붙여 둔다.
          patch(at, (d) => ({
            ...d,
            rows: d.rows.map((r) => (r.key === row.key ? { ...r, id: made.id } : r)),
            saved: { ...d.saved, [made.id]: made },
          }));
          continue;
        }
        if (was && sameInput(body, savedInput(was))) continue;
        const next = await trackRoutineMutation(
          scope,
          updateRoutine(row.id, body, { includeImpact: true }),
        );
        rememberImpact(next.review_impact);
        patch(at, (d) => ({ ...d, saved: { ...d.saved, [next.id]: next } }));
      } catch (e) {
        fail(e);
      }
    }
    return ok ? impact() : null;
  }

  /**
   * 저장을 시작한 그 화면이 아직 그대로인가. **저장은 끝까지 가되 화면은 건드리지 않는다** —
   * A 반을 저장하는 사이 B 반으로 옮기면, 늦게 끝난 A 저장이 B 화면에 문구를 띄우거나
   * A 반 일지로 넘겨 버린다. 떠난 화면(`mounted === false`)도 마찬가지다.
   */
  const stillHere = (at: string) => active.current.mounted && active.current.key === at;

  /** 한 번에 하나만. 다시 그려지기 전에 또 눌려도 두 번 보내지 않는다. */
  async function run(what: string, job: () => Promise<void>) {
    if (running.current) return;
    running.current = true;
    setBusy(what);
    try {
      await job();
    } finally {
      running.current = false;
      setBusy("");
    }
  }

  /** 서버가 반환한 직접 영향 문서 ID를 합집합으로 센다. 기존 stale은 별도로 안내한다. */
  const save = () => {
    const at = key;
    const next = `${scope}|${visit + 1}`;
    return run("save", async () => {
      const impact = await commit();
      if (!impact || !stillHere(at)) return;
      // 서버가 정한 순서와 다듬은 값을 다시 읽는다. 문구는 **다음 방문**에 붙인다.
      const count = impact.newly_stale_document_ids.length;
      const already = impact.affected_document_ids.filter(
        (id) => !impact.newly_stale_document_ids.includes(id),
      ).length;
      const changed = count ? ` 이 일과를 쓴 보육일지 ${count}건이 다시 검토 대상이 되었어요.` : "";
      const previous = already
        ? ` 이미 재검토 대상인 보육일지 ${already}건도 이 변경의 영향을 받았어요.`
        : "";
      setMessage({ at: next, text: SAVED + changed + previous });
      revisit();
    });
  };

  /**
   * 「오늘 일지 만들기」 — **저장을 먼저 하고** S-J2 로 간다 (S-J1 수락 기준 3-1).
   * 저장이 실패하면 가지 않는다. 적은 글자는 그대로 남는다.
   */
  const openDailyLog = () => {
    const at = key;
    const to = `/documents?kind=dailyLog&class_id=${classId}&date=${date}`;
    return run("open", async () => {
      if (classId === null || !(await commit()) || !stillHere(at)) return;
      router.push(to);
    });
  };

  /**
   * 어제 일과 불러오기 (FR-403). **시간과 이름만** 가져온다 — 활동계획 · 활동실행을
   * 옮기면 어제 한 일이 오늘 한 일로 적힌다. 조회일 뿐이라 아무것도 저장하지 않는다.
   */
  function importYesterday() {
    if (running.current || classId === null || !validDate(date)) return;
    if (rows.some(filled) && !window.confirm("지금 적은 줄을 지우고 어제 일과를 불러올까요?"))
      return;
    const at = key;
    const from = previousDay(date);
    void run("import", async () => {
      setMessage(null);
      try {
        const items = await listRoutines({ class_id: classId, from, to: from });
        if (!items.length) {
          setMessage({ at, text: NO_YESTERDAY });
          return;
        }
        patch(at, (d) => ({
          ...d,
          rows: items.map((row) => ({
            ...blankRow(),
            start: routineTime(row.start),
            end: routineTime(row.end),
            name: row.name,
          })),
        }));
        setErrors({});
      } catch (e) {
        setMessage({ at, text: messageFor(e), error: true });
      }
    });
  }

  const classStatus: ViewStatus = classList ? (classList.error ? "error" : "ready") : "loading";
  const noClasses = classStatus === "ready" && !classes?.length;
  const dateOk = validDate(date);
  const needClass = classStatus === "ready" && !noClasses && classId === null;
  // 날짜나 반이 없으면 조회를 보내지 않는다 — 그걸 「불러오는 중」으로 두면 영영 안 끝난다.
  const listStatus: ViewStatus =
    !dateOk || needClass ? "ready" : current ? (current.error ? "error" : "ready") : "loading";
  const ready = listStatus === "ready" && dateOk && !needClass;
  // 활동실행을 적은 줄 수 (FR-402 출력). **화면에 적힌 것으로 센다** — 저장 전이어도 센다.
  const doneCount = rows.filter((row) => row.execution.trim()).length;
  // 그날 서버에 이미 있는 줄이 없을 때만 어제를 덮어쓸 수 있다 — 저장된 줄을 잃지 않는다.
  const canImport = ready && !Object.keys(now?.saved ?? {}).length;

  return (
    <WorkspacePage
      title="일과 기록"
      description="반 하루의 일과를 적어요. 일일 보육일지가 이 기록을 근거로 써요."
    >
      <WorkspaceViewState
        status={classStatus}
        loading="반 목록을 불러오는 중이에요…"
        error={classList?.error}
        empty={
          noClasses && (
            <Empty title="먼저 우리 반을 등록해주세요">
              <Link href="/onboarding">반 등록하기 →</Link>
            </Empty>
          )
        }
      >
        <section className={ws.stack}>
          <div className={`${ws.card} ${ws.row}`}>
            <label className={ws.field}>
              반
              <select
                value={classId ?? ""}
                onChange={(e) => {
                  setPickedClass(e.target.value ? Number(e.target.value) : null);
                  revisit();
                }}
              >
                <option value="">반 선택</option>
                {classes?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label className={ws.field}>
              날짜
              <input
                type="date"
                value={date}
                onChange={(e) => {
                  setPickedDate(e.target.value);
                  revisit();
                }}
              />
            </label>
          </div>
          {/* 그 화면에서 난 일만 보여준다 — 날짜를 옮기면 따라가지 않는다. */}
          <Message error={message?.error}>{message?.at === key ? message.text : ""}</Message>
          <WorkspaceViewState
            status={listStatus}
            loading="이 날짜의 일과를 불러오는 중이에요…"
            error={current?.error}
            empty={
              (!dateOk || needClass) && <ListEmpty dateOk={dateOk} unknownClass={unknownClass} />
            }
          >
            <div className={ws.list} aria-label="일과 목록">
              {rows.map((row, index) => (
                <RowCard
                  key={row.key}
                  row={row}
                  index={index}
                  total={rows.length}
                  error={errors[row.key] ?? ""}
                  busy={!!busy}
                  dirty={dirtyRow(row)}
                  onEdit={editRow}
                  onRevert={revertRow}
                  onRemove={removeRow}
                  onMove={reorder}
                  onGrab={setDragFrom}
                  dragFrom={dragFrom}
                />
              ))}
            </div>
          </WorkspaceViewState>
          {listStatus === "error" && (
            <button type="button" className={ws.secondary} onClick={revisit}>
              다시 시도
            </button>
          )}
          {ready && (
            <div className={ws.stack}>
              <p className={ws.hint}>
                {rows.length}줄 중 활동실행을 적은 줄 {doneCount}개
                {!doneCount && " · 활동실행을 적으면 오늘 일지를 만들 수 있어요."}
              </p>
              <div className={ws.actions}>
                <button type="button" className={ws.secondary} disabled={!!busy} onClick={addRow}>
                  + 줄 추가
                </button>
                {canImport && (
                  <button
                    type="button"
                    className={ws.secondary}
                    disabled={!!busy}
                    onClick={importYesterday}
                  >
                    어제 일과 불러오기
                  </button>
                )}
                <button type="button" className={ws.primary} disabled={!!busy} onClick={save}>
                  {busy === "save" ? "저장 중…" : "저장"}
                </button>
                {/*
                  적은 줄이 하나라도 있으면 켠다 — **저장 여부로 판단하지 않는다** (수락 기준 3).
                  누르면 먼저 저장하고, 성공해야 S-J2 로 간다.
                */}
                <button
                  type="button"
                  className={ws.primary}
                  disabled={!!busy || !doneCount}
                  onClick={openDailyLog}
                >
                  {busy === "open" ? "저장하는 중…" : "오늘 일지 만들기 →"}
                </button>
              </div>
            </div>
          )}
        </section>
      </WorkspaceViewState>
    </WorkspacePage>
  );
}

/**
 * 목록이 비어 보이는 두 가지. **「기록이 없다」와 「아직 무엇을 볼지 모른다」는 다르다.**
 * 줄이 없을 때는 빈 줄 다섯이 이미 깔려 있어 여기로 오지 않는다 (S-J1 4상태).
 */
function ListEmpty({ dateOk, unknownClass }: { dateOk: boolean; unknownClass: boolean }) {
  if (!dateOk) return <Empty title="날짜를 선택해주세요" />;
  return (
    <Empty title="반을 골라주세요">
      {unknownClass ? UNKNOWN_CLASS : "어느 반의 하루를 적을지 골라주세요."}
    </Empty>
  );
}

/**
 * 한 줄. 계약의 다섯 칸 그대로다 — 시작 · 종료 · 일과 이름 · 활동계획 · 활동실행 (§10-1).
 *
 * 순서는 끌어서 바꾸고, 키보드만 쓰는 교사를 위해 ↑ ↓ 도 같이 둔다.
 */
function RowCard({
  row,
  index,
  total,
  error,
  busy,
  dirty,
  onEdit,
  onRevert,
  onRemove,
  onMove,
  onGrab,
  dragFrom,
}: {
  row: Row;
  index: number;
  total: number;
  error: string;
  busy: boolean;
  dirty: boolean;
  onEdit: (rowKey: string, field: Field, value: string) => void;
  onRevert: (rowKey: string) => void;
  onRemove: (rowKey: string) => void;
  onMove: (from: number | null, to: number) => void;
  onGrab: (from: number | null) => void;
  dragFrom: number | null;
}) {
  const set = (field: Field) => (value: string) => onEdit(row.key, field, value);
  return (
    <article
      className={ws.item}
      onDragOver={(e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
      }}
      onDrop={(e) => {
        e.preventDefault();
        // 브라우저 네이티브 드래그 중 React 상태 갱신이 늦어도 전송한 원래 줄을 찾는다.
        const raw = e.dataTransfer.getData("text/plain");
        const from = /^\d+$/.test(raw) ? Number(raw) : dragFrom;
        onMove(from, index);
        onGrab(null);
      }}
    >
      <div className={ws.row}>
        <span
          className={ws.badge}
          role="button"
          draggable={!busy}
          aria-label={`${index + 1}번째 줄 끌어서 옮기기`}
          onDragStart={(e) => {
            // Firefox 는 dragstart 에서 데이터를 담지 않으면 끌기를 아예 시작하지 않는다.
            e.dataTransfer.setData("text/plain", String(index));
            e.dataTransfer.effectAllowed = "move";
            onGrab(index);
          }}
          onDragEnd={() => onGrab(null)}
        >
          ⠿
        </span>
        <button
          type="button"
          className={ws.secondary}
          aria-label={`${index + 1}번째 줄 위로`}
          disabled={busy || index === 0}
          onClick={() => onMove(index, index - 1)}
        >
          ↑
        </button>
        <button
          type="button"
          className={ws.secondary}
          aria-label={`${index + 1}번째 줄 아래로`}
          disabled={busy || index === total - 1}
          onClick={() => onMove(index, index + 1)}
        >
          ↓
        </button>
        <label className={ws.field}>
          시작
          <input
            type="time"
            disabled={busy}
            value={row.start}
            onChange={(e) => set("start")(e.target.value)}
          />
        </label>
        <label className={ws.field}>
          종료
          <input
            type="time"
            disabled={busy}
            value={row.end}
            onChange={(e) => set("end")(e.target.value)}
          />
        </label>
        <label className={ws.field}>
          일과 이름
          <input
            maxLength={NAME_MAX}
            placeholder="오전 실내놀이"
            disabled={busy}
            value={row.name}
            onChange={(e) => set("name")(e.target.value)}
          />
        </label>
      </div>
      <div className={ws.row}>
        <label className={ws.field}>
          활동계획
          <textarea
            disabled={busy}
            value={row.plan}
            onChange={(e) => set("plan")(e.target.value)}
          />
        </label>
        <label className={ws.field}>
          활동실행
          <small>있었던 일을 그대로 적어주세요. 일일 보육일지의 근거가 돼요.</small>
          <textarea
            disabled={busy}
            value={row.execution}
            onChange={(e) => set("execution")(e.target.value)}
          />
        </label>
      </div>
      <Message error>{error}</Message>
      <div className={ws.actions}>
        <button
          type="button"
          className={ws.secondary}
          disabled={busy || !dirty}
          onClick={() => onRevert(row.key)}
        >
          되돌리기
        </button>
        <button
          type="button"
          className={ws.secondary}
          disabled={busy}
          onClick={() => onRemove(row.key)}
        >
          줄 지우기
        </button>
      </div>
    </article>
  );
}
