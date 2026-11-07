"use client";
import Link from "next/link";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { getMe } from "@/lib/api/auth";
import { getClasses, isMyClass } from "@/lib/api/classes";
import { isUnauthenticated } from "@/lib/api/client";
import { useUnsavedWarning } from "@/lib/hooks/use-unsaved-warning";
import { classServerId } from "@/lib/api/onboarding";
import {
  createRoutine,
  deleteRoutine,
  listRoutineDates,
  listRoutines,
  routineLocalId,
  routineTime,
  routineTimeValue,
  sortRoutinesByTime,
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
import { Posty } from "@/components/app/Posty";
import { WorkspacePage, Empty, Message, Notice, Tape, ws } from "./WorkspaceUI";
import { WorkspaceViewState, type ViewStatus } from "./WorkspaceViewState";
import RoutineCalendar, { koreanDay, monthRange } from "./RoutineCalendar";
import RoutineClock from "./RoutineClock";
import DailyJournalCard, { DailyJournalEditor, useDailyJournal } from "./DailyJournalCard";

const CLASSES_FAILED = "반 목록을 불러오지 못했어요. 잠시 뒤 다시 열어주세요.";
// 서버 routine_records.name 이 50자다. 더 보내면 422 다 (§10-1).
const NAME_MAX = 50;

/**
 * 그날 적은 게 하나도 없을 때 깔아 두는 하루 (S-J1).
 *
 * 빈 줄 다섯을 깔던 자리다. 어린이집 하루는 반마다 거의 같은데 교사가 매일 그 이름을
 * 열 번 다시 쳤다. 깔아 두고 **실제로 한 것만** 적게 한다 — 키즈노트 · 한그루가 그렇게 한다.
 * 어제 적은 하루가 있으면 이 표 대신 어제의 이름 · 시간을 깐다.
 *
 * 이름과 시간은 국가 공식 양식의 유아 10행형 그대로다
 * (`docs/references/보육일지-공식양식.md` — 중앙육아종합지원센터 배포, 무료 공개 자료).
 *
 * **깔아 둔 줄은 교사가 손대기 전까지 저장하지 않는다.** 손대지 않은 하루가 서버에 쌓이면
 * 일일 보육일지가 빈 일과를 근거로 삼는다.
 */
const DEFAULT_ROUTINES: [name: string, start: string, end: string][] = [
  ["등원 및 통합보육", "07:30", "09:00"],
  ["오전간식", "09:00", "09:20"],
  ["오전 실내놀이", "09:20", "10:40"],
  ["활동", "10:40", "11:00"],
  ["바깥놀이(대체)", "11:00", "12:20"],
  ["점심식사", "12:20", "13:20"],
  ["낮잠 및 휴식", "13:20", "14:20"],
  ["오후 놀이", "14:20", "15:40"],
  ["오후간식", "15:40", "16:00"],
  ["귀가 및 통합보육", "16:00", "17:00"],
];
const NAME_REQUIRED = "일과 이름을 적어 주세요.";
const TIME_BACKWARDS = "끝나는 시간이 시작보다 빨라요.";
const HAS_PROBLEM = "입력하지 않은 필수 항목이 있어요. 표시된 일과를 확인해 주세요.";

/** 교사가 고쳐야 할 줄 한 건. 번호로 세고, 눌러서 그 칸으로 간다. */
interface Problem {
  rowKey: string;
  /** 화면에서 몇 번째 줄인가 (1부터). */
  at: number;
  text: string;
}

/**
 * 「간식」과 · 「바깥놀이」와 — 받침에 따라 조사를 고른다.
 *
 * 전에는 이름 뒤에 늘 「와」를 붙여 「간식 와 시간이 겹쳐요」가 나왔다. 교사가 읽는 글이다.
 */
function withParticle(name: string) {
  const text = name.trim();
  const last = text.charCodeAt(text.length - 1);
  const hangul = last >= 0xac00 && last <= 0xd7a3;
  return `「${text}」${hangul && (last - 0xac00) % 28 !== 0 ? "과" : "와"}`;
}

/** 화면 맨 위로 끌어올리고 그 칸에 커서를 둔다. 테스트 harness 에는 DOM 이 없다. */
function focusField(id: string) {
  if (typeof document === "undefined") return;
  const field = document.getElementById(id);
  field?.scrollIntoView({ behavior: "smooth", block: "center" });
  (field as HTMLElement | null)?.focus();
}

/** 줄마다 고유한 입력 칸 id. 요약에서 바로 그 칸으로 보낸다. */
const nameFieldId = (rowKey: string) => `routine-name-${rowKey}`;
const SAVED = "저장했어요.";
const UNKNOWN_CLASS = "주소에 적힌 반을 찾을 수 없어요. 왼쪽 위 반 이름을 눌러 반을 골라주세요.";

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
  /** 교사가 이 줄을 건드렸나. 깔아 둔 기본 일과를 「적은 줄」로 세지 않으려고 둔다. */
  touched: boolean;
  /** 깔아 둔 처음 모습. 서버에 없는 줄의 「되돌리기」가 여기로 돌아간다. */
  base: { name: string; start: string; end: string } | null;
  /**
   * 쪽지 색 · 기울기 (0~3). **줄이 만들어질 때 정해지고 그 줄을 따라다닌다.**
   *
   * 자리(`index % 4`)로 정했더니 시간순으로 줄을 세울 때 글자만 바뀌고 색은 그 자리에
   * 남았다 — 쪽지 한 장이 통째로 움직이는 것으로 보이지 않는다.
   */
  tone: number;
}

type Field = Exclude<keyof Row, "key" | "id" | "tone">;

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
  /** 그날이 비었을 때 깔 어제 하루. 비어 있으면 기본 하루를 깐다. */
  preset: ApiRoutine[];
  error: string;
}

// 화면 안에서만 쓰는 줄 번호. 같은 렌더 안에서 겹치지만 않으면 된다.
let nextRowKey = 0;
const blankRow = (): Row => ({
  key: `new:${(nextRowKey += 1)}`,
  tone: nextRowKey % 4,
  id: null,
  start: "",
  end: "",
  name: "",
  plan: "",
  execution: "",
  touched: false,
  base: null,
});
/** 깔아 두는 줄. 이름 · 시간은 있지만 교사가 손대기 전까지 저장하지 않는다. */
const presetRow = (name: string, start: string, end: string): Row => ({
  ...blankRow(),
  name,
  start,
  end,
  base: { name, start, end },
});
const serverRow = (row: ApiRoutine): Row => ({
  ...blankRow(),
  key: `server:${row.id}`,
  id: row.id,
  start: routineTime(row.start),
  end: routineTime(row.end),
  name: row.name,
  plan: row.plan,
  execution: row.execution,
  touched: true,
  base: null,
});

const draftFrom = (key: string, rows: ApiRoutine[], preset?: ApiRoutine[]): Draft => ({
  key,
  // 그날 적은 게 없으면 어제 하루를, 어제도 없으면 기본 하루를 깐다 (S-J1 · FR-403).
  // 읽자마자 시간순으로 세운다 — 번호가 겹친 지난 데이터도 교사 눈에는 시간 순이어야 한다.
  rows: sortRoutinesByTime(
    rows.length
      ? rows.map(serverRow)
      : preset?.length
        ? preset.map((row) => presetRow(row.name, routineTime(row.start), routineTime(row.end)))
        : DEFAULT_ROUTINES.map(([name, start, end]) => presetRow(name, start, end)),
  ),
  removed: [],
  saved: Object.fromEntries(rows.map((row) => [row.id, row])),
});

/**
 * 한 칸이라도 적혀 있으면 「쓰던 줄」이다. 통째로 빈 줄만 보내지 않는다 (FR-402 예외).
 * 깔아 둔 기본 일과는 교사가 손대기 전까지 세지 않는다 — 손대지 않은 하루를 저장하지 않는다.
 */
const filled = (row: Row) =>
  (row.touched || row.id !== null) &&
  Boolean(row.start || row.end || row.name.trim() || row.plan.trim() || row.execution.trim());

/** 서버가 막는 것과 같은 것만 미리 본다 — 나머지는 서버 문구를 그대로 보여준다. */
function problemWith(row: Row): string {
  if (!row.name.trim()) return NAME_REQUIRED;
  if (row.name.trim().length > NAME_MAX) return `일과 이름은 ${NAME_MAX}자까지예요.`;
  if (row.start && row.end && row.start >= row.end) return TIME_BACKWARDS;
  return "";
}

/** 시작과 끝이 둘 다 있고 앞뒤가 맞는 줄. 겹침은 이런 줄끼리만 따질 수 있다. */
const spans = (row: Row) => Boolean(row.start && row.end) && row.start < row.end;

/** `09:20 ~ 10:40` */
const spanText = (row: Row) => `${row.start} ~ ${row.end}`;

/**
 * 이 줄과 같은 시간을 쓰고 있는 다른 일과. 없으면 `null`.
 *
 * 하루 일과는 줄을 서는 것이다 — 등원이 끝나야 실내놀이가 시작한다. 일일 보육일지도
 * 시간 순으로 한 줄씩 받으므로 겹친 두 칸을 넣을 자리가 없다.
 *
 * **저장될 줄끼리만 본다.** 깔아 둔 기본 하루는 손대기 전까지 서버로 가지 않는다 —
 * 그걸 겹침으로 세면, 교사가 고른 몇 줄이 아직 손대지 않은 줄과 부딪혀 저장이 막힌다.
 */
function clashWith(rows: Row[], row: Row): Row | null {
  if (!spans(row) || !filled(row)) return null;
  return (
    rows.find(
      (other) =>
        other.key !== row.key &&
        spans(other) &&
        filled(other) &&
        other.start < row.end &&
        row.start < other.end,
    ) ?? null
  );
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

/**
 * 보낼 `position`. 화면 순서가 곧 시간순이다.
 *
 * **번호를 되도록 고쳐 쓰지 않는다.** 서버 번호는 `0,0,0` 처럼 겹칠 수 있고(지난 데이터가
 * 그렇다), 그걸 `0,1,2` 로 다듬으면 교사가 건드리지도 않은 줄이 전부 `PUT` 대상이 된다.
 * 기존 줄의 번호는 그대로 두고 새 줄만 마지막 번호 뒤로 이어 붙인다.
 *
 * 그렇게 얻은 번호가 **화면 순서와 거꾸로 서면** 그때만 처음부터 다시 매긴다. 시간을
 * 고쳐 줄이 자리를 바꾼 경우다 — 안 그러면 다시 읽을 때 서버가 준 옛 순서로 돌아간다.
 */
function positionsFor(rows: Row[], saved: Draft["saved"]): number[] {
  const known = rows.map((row) => (row.id === null ? null : (saved[row.id] ?? null)));
  let next = known.reduce((max, row) => (row ? Math.max(max, row.position) : max), -1);
  const kept = known.map((row) => (row ? row.position : (next += 1)));
  const settled = kept.every((value, index) => index === 0 || kept[index - 1] <= value);
  return settled ? kept : rows.map((_, index) => index);
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
  const [pickedDate, setPickedDate] = useState<string | null>(null);
  /** 달력이 펴 놓은 달. `null` 이면 고른 날이 든 달이다 — 날짜를 바꾸면 따라간다. */
  const [pickedMonth, setPickedMonth] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  /** 화면 아래에 잠깐 떴다 사라지는 알림. 시간이 겹쳤다는 말을 적던 자리에서 본다. */
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  /**
   * 지금 요청이 도는 중인가. `busy` 는 **다시 그려져야** 버튼이 잠기므로, 그 사이에 한 번 더
   * 눌리면 같은 저장이 두 번 간다. 렌더를 기다리지 않는 자물쇠가 따로 필요하다.
   */
  const running = useRef(false);
  // 문구에 「어느 화면에서 났나」를 붙여 둔다. 지난 날짜의 실패가 지금 날짜에 뜨면 안 된다.
  const [message, setMessage] = useState<{
    at: string;
    text: string;
    error?: boolean;
    /** 고칠 줄 목록. 있으면 글 한 덩어리 대신 짚어 주는 칸으로 그린다. */
    problems?: Problem[];
  } | null>(null);
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
   * 이 화면이 보는 반. 주소 → 사이드바가 정한 반 순이고, **반 목록에 있는 번호만** 쓴다.
   * 둘 다 없으면 `null` 이다 — 첫 반을 대신 고르지 않는다 (FR-405).
   */
  const classId = unknownClass ? null : (known(query.classId) ?? known(primaryClass));
  // 주소에 날짜가 없으면 오늘이다 (S-J1).
  const date = pickedDate ?? (query.date || today());
  const todayDate = today();
  // 펴 놓은 달. 날짜를 직접 쳤으면 그 달로 따라가고, 달력에서 넘겼으면 그 달에 머문다.
  const month = pickedMonth ?? (validDate(date) ? date.slice(0, 7) : todayDate.slice(0, 7));
  const marked = useMonthMarks(classId, month, visit);
  const journal = useDailyJournal({ classId, date: validDate(date) ? date : "" });

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
      .then(({ items }) => !stale && setClassList({ items: items.filter(isMyClass), error: "" }))
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
        // 어제와 오늘을 한 번에 읽는다. 오늘이 비었으면 어제의 이름 · 시간을 깔아 준다
        // (FR-403). 「어제 일과 불러오기」 단추가 하던 일을 교사가 누르지 않아도 한다.
        const items = await listRoutines({
          class_id: classId,
          from: previousDay(date),
          to: date,
        });
        const rows = items.filter((row) => row.date === date);
        if (!stale)
          setLoaded({
            key,
            rows,
            preset: rows.length ? [] : items.filter((row) => row.date !== date),
            error: "",
          });
      } catch (e) {
        if (!stale) setLoaded({ key, rows: [], preset: [], error: messageFor(e) });
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
    setDraft(draftFrom(key, current.rows, current.preset));
    // 새 서버 snapshot 이다 — 지난 반·날짜에서 띄운 안내는 이 줄들과 상관이 없다.
    // (같은 화면에서 저장이 실패한 경우는 여기로 오지 않는다. 그때 안내는 그대로 남는다.)
    setErrors({});
  }
  const now = draft?.key === key ? draft : null;
  const rows = now?.rows ?? [];
  // 반은 사이드바에서 바꾼다. 바꾸면 화면을 다시 읽으므로 적어 둔 줄이 사라질 수 있다.
  useUnsavedWarning(unsavedRows());

  // 읽을 만큼만 두고 치운다. 교사가 닫을 단추를 찾게 만들 안내가 아니다.

  /** 저장을 시작한 화면(`at`)이 아직 그 화면일 때만 초안을 고친다. */
  const patch = (at: string, change: (draft: Draft) => Draft) =>
    setDraft((prev) => (prev && prev.key === at ? change(prev) : prev));

  const editRow = (rowKey: string, field: Field, value: string) =>
    patch(key, (d) => ({
      ...d,
      rows: d.rows.map((row) =>
        row.key === rowKey ? { ...row, [field]: value, touched: true } : row,
      ),
    }));

  /**
   * 시계를 닫았다 — 이 줄의 시간이 정해졌다.
   *
   * 다른 일과와 겹치면 **줄을 세우지 않고** 알린다. 겹친 채로 자리를 바꾸면 어느 줄이
   * 잘못됐는지 더 못 찾는다. 겹치지 않으면 그 자리에서 시간순으로 다시 세운다.
   */
  const timeSet = (rowKey: string) => {
    const row = rows.find((r) => r.key === rowKey);
    if (!row) return;
    const clash = clashWith(rows, row);
    if (clash) {
      setNotice(
        `${withParticle(clash.name.trim() || "다른 일과")} 시간이 겹쳐요. (${spanText(clash)})`,
      );
      return;
    }
    patch(key, (d) => ({ ...d, rows: sortRoutinesByTime(d.rows) }));
  };

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
        if (was) return { ...serverRow(was), key: row.key, id: row.id };
        // 깔아 둔 줄은 깔았을 때로, 교사가 더한 빈 줄은 빈 줄로 돌아간다.
        const base = row.base;
        return {
          ...blankRow(),
          key: row.key,
          id: null,
          base,
          ...(base ? { name: base.name, start: base.start, end: base.end } : {}),
        };
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

  /**
   * 보낼 수 있는 줄인가. 쓰던 줄인데 이름이 없으면 **아무것도 보내지 않고** 그 줄에
   * 안내를 띄운다 (FR-402 예외).
   *
   * **`run` 바깥에서 부른다.** 안에서 부르면 같은 렌더에 `busy` 가 켜지면서 입력칸이
   * `disabled` 가 되고, 방금 커서를 둔 칸이 포커스를 잃는다.
   */
  function checkRows(): boolean {
    const at = key;
    if (classId === null || !now) return false;
    const problems: Record<string, string> = {};
    const found: Problem[] = [];
    let first = "";
    now.rows.forEach((row, index) => {
      // 손대지 않은 빈 줄은 검사하지 않는다 — 기본 다섯 줄이 전부 오류가 되면 안 된다.
      if (!filled(row)) return;
      const problem = problemWith(row);
      if (!problem) return;
      problems[row.key] = problem;
      found.push({ rowKey: row.key, at: index + 1, text: problem });
      if (!first) first = row.key;
    });
    /**
     * 겹친 시간은 **이번에 시간을 바꾼 줄**에서만 막는다.
     *
     * 지난 데이터에는 겹친 날이 이미 있다 — 서버가 막은 적이 없다. 그런 날을 통째로
     * 저장 불가로 만들면 교사가 글자 하나 고치려고 남의 줄부터 손봐야 한다. 지금
     * 만들어진 겹침만 돌려보내고, 예전 것은 그대로 둔다.
     */
    now.rows.forEach((row, index) => {
      if (problems[row.key]) return;
      const was = row.id === null ? null : now.saved[row.id];
      const moved = was
        ? routineTime(was.start) !== row.start || routineTime(was.end) !== row.end
        : spans(row);
      if (!moved) return;
      const clash = clashWith(now.rows, row);
      if (!clash) return;
      const other = withParticle(clash.name.trim() || "다른 일과");
      problems[row.key] = `${other} 시간이 겹쳐요. (${spanText(clash)})`;
      found.push({ rowKey: row.key, at: index + 1, text: `${other} 시간이 겹쳐요` });
      if (!first) first = row.key;
    });
    setErrors(problems);
    if (!found.length) {
      setMessage(null);
      return true;
    }
    // 서버가 돌려준 문구가 아니라 **보내기 전에 화면이 잡은 것**이다 (§11 거절 처리와 구분).
    setMessage({ at, text: HAS_PROBLEM, error: true, problems: found });
    focusField(nameFieldId(first));
    return false;
  }

  /**
   * 초안과 마지막 서버 모습을 비교해 한 번에 보낸다 (FR-402 처리 3).
   * **`checkRows()` 가 통과한 뒤에만 부른다.**
   *
   * 돌려주는 값은 「보내야 할 요청이 전부 성공했나」다. 일부가 실패하면 **초안을 비우지
   * 않는다** — 성공한 것만 초안에 반영해 두어, 다시 눌러도 같은 줄을 두 번 만들지 않는다.
   *
   * 함께 돌려주는 `evidence` 는 **실제로 한 것을 적은 줄의 서버 번호**다. 바로 뒤에
   * 오늘 일지를 만들 때 근거(`source_ids`)가 된다 — 다시 조회해서 찾지 않는다.
   */
  async function commit(): Promise<{ impact: RoutineReviewImpact; evidence: string[] } | null> {
    const at = key;
    if (classId === null || !now) return null;
    const evidence: string[] = [];

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
          if (row.execution.trim()) evidence.push(routineLocalId(made.id));
          continue;
        }
        if (row.execution.trim()) evidence.push(routineLocalId(row.id));
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
    return ok ? { impact: impact(), evidence } : null;
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
    if (!checkRows()) return;
    return run("save", async () => {
      const done = await commit();
      if (!done || !stillHere(at)) return;
      const impact = done.impact;
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
   * 「오늘 일지 만들기」 — **저장을 먼저 하고 이 화면에서 연다** (S-J1 수락 기준 3-1).
   *
   * 전에는 문서 보관함으로 보냈다. 보관함은 다 쓴 문서가 쌓이는 곳이지 쓰는 곳이
   * 아니고, 교사는 방금 적은 일과를 눈앞에 두고 일지를 손봐야 한다.
   *
   * 저장이 실패하면 만들지 않는다. 적은 글자는 그대로 남는다.
   */
  const openDailyLog = () => {
    const at = key;
    if (!checkRows()) return;
    return run("open", async () => {
      if (classId === null) return;
      const done = await commit();
      if (!done || !stillHere(at)) return;
      await journal.make(done.evidence);
      revisit();
    });
  };

  /**
   * 반 · 날짜를 옮기기 전에 묻는다 (#180 수린님 리뷰).
   *
   * 옮기면 `revisit()` 이 서버 값을 다시 불러와 **적어 둔 줄을 덮어쓴다.** 전에는 경고가
   * 없어 저장 안 한 줄이 조용히 사라졌다.
   *
   * **「적혀 있나」가 아니라 「저장 안 됐나」를 본다.** 처음에 `rows.some(filled)` 로 했더니
   * 저장을 마친 뒤에도 물어서 e2e 가 막혔다(`routines.spec.ts` I J). 서버에서 읽은 모습
   * (`draft.saved`)과 지금 입력을 견줘, 새 줄이거나 달라진 줄이 있을 때만 묻는다.
   */
  function unsavedRows() {
    // 아직 못 읽었으면 적어 둔 것도 없다.
    if (!draft) return false;
    if (draft.removed.length) return true;
    const known = draft.saved;
    return rows.some((row) => {
      if (row.id === null) return filled(row);
      const was = known[row.id];
      return !was || !sameInput(inputOf(row, was.position, was.date, was), savedInput(was));
    });
  }

  function leaveRows() {
    return !unsavedRows() || window.confirm("저장하지 않은 줄이 사라져요. 옮길까요?");
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
  /** 날짜를 옮긴다. 적어 둔 줄이 있으면 먼저 묻는다. */
  const moveTo = (next: string, month: string | null) => {
    if (!leaveRows()) return;
    setPickedDate(next);
    setPickedMonth(month);
    revisit();
  };

  return (
    <WorkspacePage
      title="일과 기록"
      /* 「일일 보육일지가 이 기록을 근거로 쓴다」는 설명은 뺐다. 화면에 들어온 교사는
         이미 일과를 적으러 온 것이고, 제목 밑 한 줄은 매일 읽히지 않는다. */
      description=""
      /*
        저장과 「오늘 일지 만들기」는 화면 맨 아래에 있었다. 줄이 열 개라 적고 나면
        단추가 접힌 화면 밖으로 밀려 내려간다. 제목 옆으로 올려 둔다.
        「+ 줄 추가」는 목록 끝에 남긴다 — 새 줄이 생기는 자리가 거기다.
      */
      action={
        ready ? (
          <div className={ws.actions} data-tour="routines-actions">
            <button type="button" className={ws.secondary} disabled={!!busy} onClick={save}>
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
              title={doneCount ? undefined : "실제로 한 것을 한 줄이라도 적어 주세요."}
              onClick={openDailyLog}
            >
              {busy === "open" ? "저장하는 중…" : "오늘 일지 만들기 →"}
            </button>
          </div>
        ) : undefined
      }
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
        {/* 왼쪽에서 날을 고르고 오른쪽에 그날을 적는다 — 계획안 만들기와 같은 짜임이다. */}
        <div className={ws.grid}>
          <div className={ws.side}>
            <aside className={`${ws.card} ${ws.calendarCard}`} data-tour="routines-calendar">
              <Tape />
              <RoutineCalendar
                date={dateOk ? date : todayDate}
                month={month}
                today={todayDate}
                marked={marked}
                disabled={!!busy}
                onMonth={setPickedMonth}
                onPick={(next) => moveTo(next, null)}
              />
              {/* 먼 날짜로 한 번에 뛰는 길. 달력이 이미 날을 보여 주므로 칸은 작게 둔다. */}
              <label className={ws.calendarJump}>
                날짜
                <input
                  name="date"
                  type="date"
                  value={date}
                  disabled={!!busy}
                  onChange={(e) => moveTo(e.target.value, null)}
                />
              </label>
            </aside>
            {/* 「오늘 일지가 어디까지 됐나」는 날짜와 같이 본다 — 달력 바로 밑에 둔다.
                일지를 펴면 편집기는 오른쪽 칠판 밑으로 나온다. 좁은 칸에서 쓸 글이 아니다. */}
            {ready && <DailyJournalCard state={journal} day={koreanDay(date).day} />}
          </div>

          <section className={ws.stack}>
            {/* 그 화면에서 난 일만 보여준다 — 날짜를 옮기면 따라가지 않는다. */}
            {message?.at === key && message.problems?.length ? (
              <ProblemBoard items={message.problems} />
            ) : (
              <Message error={message?.error}>{message?.at === key ? message.text : ""}</Message>
            )}
            <WorkspaceViewState
              status={listStatus}
              loading="이 날짜의 일과를 불러오는 중이에요…"
              error={current?.error}
              empty={
                (!dateOk || needClass) && <ListEmpty dateOk={dateOk} unknownClass={unknownClass} />
              }
            >
              {/* 안내문을 지우고 그 자리에 날짜를 손글씨로 둔다. 「오늘 쓰고 있다」는
                  것만 알면 되고, 어느 날인지는 오른쪽을 볼 때마다 필요하다. */}
              <h2 className={ws.sheetDay}>
                {koreanDay(dateOk ? date : todayDate).day}
                <span>
                  {koreanDay(dateOk ? date : todayDate).dow}
                  <CircleMark />
                </span>
              </h2>
              {/* 교실 칠판에 일과 쪽지를 붙인 모습 (첫 화면 오른쪽 줄과 같은 판이다).
                  줄마다 종이 한 장이라 어디서 한 일과가 끝나는지 선을 안 그어도 보인다. */}
              <div
                className={`${ws.routineSheet} chalkboard`}
                aria-label="일과 목록"
                data-tour="routines-board"
              >
                {rows.map((row, index) => (
                  <RowCard
                    key={row.key}
                    row={row}
                    index={index}
                    error={errors[row.key] ?? ""}
                    busy={!!busy}
                    dirty={dirtyRow(row)}
                    onEdit={editRow}
                    onTimeSet={timeSet}
                    onRevert={revertRow}
                    onRemove={removeRow}
                  />
                ))}
                <div className={ws.rowTools}>
                  <button type="button" className={ws.rowTool} disabled={!!busy} onClick={addRow}>
                    + 줄 추가
                  </button>
                </div>
              </div>
            </WorkspaceViewState>
            {listStatus === "error" && (
              <button type="button" className={ws.secondary} onClick={revisit}>
                다시 시도
              </button>
            )}
            {/* 편집기는 칠판 바로 아래다 — 방금 적은 일과를 보며 손봐야 한다. */}
            {ready && <DailyJournalEditor state={journal} day={koreanDay(date).day} />}
          </section>
        </div>
      </WorkspaceViewState>
      <Notice onDone={() => setNotice("")}>{notice}</Notice>
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
      {unknownClass ? UNKNOWN_CLASS : "왼쪽 위 반 이름을 눌러 하루를 적을 반을 골라주세요."}
    </Empty>
  );
}

/**
 * 한 줄. 계약의 다섯 칸 그대로다 — 시작 · 종료 · 일과 이름 · 활동계획 · 활동실행 (§10-1).
 *
 * **교사가 매일 적는 것은 「실제로 한 것」 하나뿐이다.** 이름 · 시간은 깔려 있고, 「계획한 것」은
 * 접어 둔다 — 쓰는 원이 있고 안 쓰는 원이 있다. 순서는 시간이 정하므로 끌기 · ↑ ↓ 는 없다.
 */
function RowCard({
  row,
  index,
  error,
  busy,
  dirty,
  onEdit,
  onTimeSet,
  onRevert,
  onRemove,
}: {
  row: Row;
  index: number;
  error: string;
  busy: boolean;
  dirty: boolean;
  onEdit: (rowKey: string, field: Field, value: string) => void;
  onTimeSet: (rowKey: string) => void;
  onRevert: (rowKey: string) => void;
  onRemove: (rowKey: string) => void;
}) {
  const set = (field: Field) => (value: string) => onEdit(row.key, field, value);
  return (
    <article className={ws.routineRow} data-tone={row.tone} data-lean={row.tone % 2}>
      <div className={ws.routineHead}>
        <div className={ws.rowName}>
          <input
            id={nameFieldId(row.key)}
            aria-label="일과 이름 (필수)"
            required
            maxLength={NAME_MAX}
            placeholder="오전 실내놀이"
            disabled={busy}
            // 요약에서 이 칸으로 보낼 수 있어야 하고, 읽어 주는 도구도 오류를 알아야 한다.
            aria-invalid={error ? true : undefined}
            aria-errormessage={error ? `${nameFieldId(row.key)}-error` : undefined}
            value={row.name}
            onChange={(e) => set("name")(e.target.value)}
          />
        </div>
        <div className={ws.rowMeta}>
          {/* 시작 · 종료 칸 둘이던 자리다. 한 칸에 「오전 09:20 ~ 10:40」로 적고,
            누르면 시계판에서 구간을 끌어 고친다. */}
          <RoutineClock
            start={row.start}
            end={row.end}
            disabled={busy}
            onStart={set("start")}
            onEnd={set("end")}
            onDone={() => onTimeSet(row.key)}
          />
          <button
            type="button"
            className={ws.rowTool}
            aria-label={`${index + 1}번째 일과 지우기`}
            title="이 일과 지우기"
            disabled={busy}
            onClick={() => onRemove(row.key)}
          >
            ×
          </button>
        </div>
      </div>

      <textarea
        className={ws.rowDone}
        aria-label="실제로 한 것"
        placeholder="실제로 한 것"
        disabled={busy}
        value={row.execution}
        onChange={(e) => set("execution")(e.target.value)}
      />

      {/* 「계획한 것」은 안 쓰는 원이 많다. 적은 줄만 펴 두고 나머지는 접는다. */}
      {/* 이름은 안의 글칸 하나만 갖는다. 접는 칸에도 같은 이름을 달면 「계획한 것」을 찾는
          보조기기 · 테스트가 둘을 만나 어느 쪽인지 모른다. 접는 칸은 summary 글자로 읽힌다. */}
      <details className={ws.rowPlan} open={row.plan ? true : undefined}>
        <summary>{row.plan ? "계획한 것" : "계획한 것 적기"} ▾</summary>
        <textarea
          aria-label="계획한 것"
          placeholder="계획한 것"
          disabled={busy}
          value={row.plan}
          onChange={(e) => set("plan")(e.target.value)}
        />
      </details>

      <Message error id={`${nameFieldId(row.key)}-error`}>
        {error}
      </Message>
      {dirty && (
        <div className={ws.rowTools}>
          <button
            type="button"
            className={ws.revert}
            disabled={busy}
            onClick={() => onRevert(row.key)}
          >
            <UndoMark />
            되돌리기
          </button>
        </div>
      )}
    </article>
  );
}

/**
 * 고칠 곳을 포스티가 짚어 준다 (A 안).
 *
 * 전에는 베이지 띠 안에 줄바꿈으로 이어 붙인 글 한 덩어리였다. 크림 바탕에 갈색 글씨라
 * 떠오르지 않았고, 몇 군데인지도 세어 봐야 알았다. 포스티가 말을 거는 자리는 메인 ·
 * 주간 기록에서 이미 쓰는 짜임이라 교사가 「서비스가 하는 말」로 바로 읽는다.
 */
function ProblemBoard({ items }: { items: Problem[] }) {
  return (
    <section className={ws.problemBoard} role="alert">
      <Posty pose="point" face="fix" tone="caution" size={72} label={null} />
      <div className={ws.problemBody}>
        <p className={ws.problemHead}>고칠 곳이 {items.length}군데 있어요</p>
        <p className={ws.problemLead}>아래를 고치면 바로 저장돼요.</p>
        <ul className={ws.problemList}>
          {items.map((item) => (
            <li key={item.rowKey}>
              <span className={ws.problemNo}>{item.at}</span>
              <span className={ws.problemText}>
                {item.at}번째 일과 — {item.text}
              </span>
              <button
                type="button"
                className={ws.problemGo}
                onClick={() => focusField(nameFieldId(item.rowKey))}
              >
                가기 →
              </button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

const NO_MARKS: string[] = [];

/**
 * 달력에 찍을 점 — 그 달에 일과를 적어 둔 날.
 *
 * 달을 넘길 때와 저장한 뒤에만 묻는다. 적는 화면의 하루치 조회와 섞이지 않게
 * `listRoutineDates` 를 따로 쓴다 — 섞이면 「하루만 읽는다」를 지킬 수 없다.
 */
function useMonthMarks(classId: number | null, month: string, visit: number) {
  const [marked, setMarked] = useState<string[]>(NO_MARKS);
  useEffect(() => {
    if (classId === null) return;
    let stale = false;
    const { from, to } = monthRange(month);
    void (async () => {
      // 점은 거들 뿐이다. 못 받아 와도 적는 일을 막지 않는다.
      const days = await listRoutineDates(classId, from, to).catch(() => NO_MARKS);
      if (!stale) setMarked(days);
    })();
    return () => {
      stale = true;
    };
  }, [classId, month, visit]);
  return marked;
}

/** 달력에서 오늘에 치는 동그라미. 한 바퀴를 덜 닫아 손으로 그은 자국으로 보인다. */
function CircleMark() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 150 70"
      preserveAspectRatio="none"
      className={ws.circleMark}
    >
      <path
        d="M74 6 C112 4 146 18 143 36 C140 56 100 66 68 64 C32 62 6 50 8 32 C10 14 42 6 78 7"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** 되돌리기 — 왼쪽으로 돌아가는 화살표. 글자만 두면 무슨 단추인지 멀리서 안 보인다. */
function UndoMark() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" className={ws.revertMark}>
      <path
        d="M4 9h9.5a5.5 5.5 0 1 1 0 11H8"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
      />
      <path
        d="M7.6 5 3.6 9l4 4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
