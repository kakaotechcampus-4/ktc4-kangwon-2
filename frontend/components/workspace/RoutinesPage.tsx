"use client";
import Link from "next/link";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { getMe } from "@/lib/api/auth";
import { getClasses, isMyClass } from "@/lib/api/classes";
import { isUnauthenticated } from "@/lib/api/client";
import { isStaleWrite } from "@/lib/api/documents";
import { useUnsavedWarning } from "@/lib/hooks/use-unsaved-warning";
import { classServerId } from "@/lib/api/onboarding";
import {
  chooseRoutineWeather,
  getRoutineDay,
  getRoutineTemplate,
  listRoutineDates,
  routineLocalId,
  routineTime,
  saveRoutineDraft,
  saveRoutineTemplate,
  sortRoutinesByTime,
  trackRoutineMutation,
  waitForRoutineScope,
  type ApiRoutine,
  type DayPreset,
  type DayWeather,
  type DraftRow,
  type DraftSaveResult,
  type RoutineDayDraft,
  type RoutineReviewImpact,
  type Sky,
} from "@/lib/api/routines";
import type { ApiClass } from "@/lib/api/types";
import { useClientState } from "@/lib/hooks/use-client-state";
import { chosenClassFor, loadClassSettings } from "@/lib/onboarding/settings";
import { today, validDate } from "@/lib/workspace/model";
import {
  appendLine,
  contextMatches,
  needsOutdoorSwap,
  planCandidates,
  presetNote,
} from "@/lib/workspace/journal-day";
import { routinesQuery, routinesScope } from "@/lib/workspace/routines-route";
import { Posty } from "@/components/app/Posty";
import { WorkspacePage, Empty, JournalTabs, Message, Notice, ws } from "./WorkspaceUI";
import { WorkspaceViewState, type ViewStatus } from "./WorkspaceViewState";
import RoutineCalendar, { koreanDay, monthRange } from "./RoutineCalendar";
import RoutineClock from "./RoutineClock";
import RoutineWeather from "./RoutineWeather";
import RoutineRowExtras from "./RoutineRowExtras";
import { useDayExtras } from "./use-day-extras";
import DailyJournalCard, { DailyJournalEditor, useDailyJournal } from "./DailyJournalCard";
import css from "./RoutineDay.module.css";

const CLASSES_FAILED = "반 목록을 불러오지 못했어요. 잠시 뒤 다시 열어주세요.";
// 서버 routine_records.name 이 50자다. 더 보내면 422 다 (§10-1).
const NAME_MAX = 50;

/**
 * 그날 적은 게 하나도 없을 때 깔아 두는 하루 (S-J1).
 *
 * 빈 줄 다섯을 깔던 자리다. 어린이집 하루는 반마다 거의 같은데 교사가 매일 그 이름을
 * 열 번 다시 쳤다. 깔아 두고 **실제로 한 것만** 적게 한다 — 키즈노트 · 한그루가 그렇게 한다.
 * 반 기본 일과표 · 지난주 같은 요일 · 최근 기록일이 있으면 서버가 정한 그 줄을 깐다 (ADR-085).
 *
 * 이름과 시간은 국가 공식 양식의 유아 10행형 그대로다
 * (`docs/references/보육일지-공식양식.md` — 중앙육아종합지원센터 배포, 무료 공개 자료).
 *
 * **깔아 둔 줄은 교사가 손대기 전까지 근거로 올리지 않는다.** 손대지 않은 하루가 서버에 쌓이면
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
const UNKNOWN_CLASS = "주소에 적힌 반을 찾을 수 없어요. 왼쪽 위 반 이름을 눌러 반을 골라주세요.";

function messageFor(error: unknown) {
  if (isUnauthenticated(error)) return "로그인이 필요해요. 다시 로그인한 뒤 이용해주세요.";
  return error instanceof Error ? error.message : "요청을 처리하지 못했어요.";
}

/** 화면 한 줄. 시간 · 글은 전부 문자열이다 — `<input>` 이 주는 모양 그대로 들고 있는다. */
interface Row {
  key: string;
  /** 서버에 올라간 줄이면 그 일과 기록 번호. 아직이면 `null` 이다. */
  id: number | null;
  start: string;
  end: string;
  name: string;
  plan: string;
  execution: string;
  /** 교사가 이 줄을 건드렸나. 깔아 둔 줄을 「적은 줄」로 세지 않으려고 둔다. */
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
  /** 어제 지원을 반영한 줄 — 보라 「반영」 도장. 종이에서만 글자가 된다 (ADR-086). */
  reflected: boolean;
  /** 주간계획안에서 교사가 맞다고 눌러 넣은 활동 이름. 주간 「우리반 놀이」 (ADR-086). */
  activities: string[];
}

type Field = "start" | "end" | "name" | "plan" | "execution";

/**
 * 이 화면의 하루 (FR-402 · ADR-084).
 *
 * **쓰는 대로 서버 임시본에 둔다** — 일과 기록(근거)이 아니다. 근거로 올리는 것은 화면을 떠날 때와
 * 「오늘 일지 만들기」 때다. `saved` 는 마지막으로 읽은 일과 기록이라 「되돌리기」가 여기로 간다.
 */
interface Draft {
  key: string;
  rows: Row[];
  /** 지우기로 표시한 **올라간 줄**. 올릴 때 서버가 지운다. */
  removed: number[];
  saved: Record<number, ApiRoutine>;
  /** 교사가 고친 횟수. 임시본 저장이 어디까지 따라왔는지 이것으로 센다. */
  edits: number;
  /** 서버 임시본에 들어간 마지막 `edits`. */
  savedEdits: number;
  /** 지금 줄이 일과 기록에 올라가 있나. 고치면 false 가 되고, 떠날 때 올린다. */
  promoted: boolean;
}

/** 한 번의 조회 결과. `key` 가 화면 조건과 다르면 지금 조건으로 받은 값이 아니다. */
interface Loaded {
  key: string;
  rows: ApiRoutine[];
  /** 서버 임시본. 아직 안 올라간 것이면 그것을 편다 — 다른 기기에서 쓴 글도 여기 있다. */
  draft: RoutineDayDraft | null;
  /** 그날이 비었을 때 깔 줄 (ADR-085). 없으면 표준 하루를 깐다. */
  preset: DayPreset | null;
  weather: DayWeather | null;
  error: string;
}

/** 머리줄 저장 상태. 「어느 화면에서 났나」를 붙여 둔다 — 지난 날짜의 실패가 지금 날짜에 뜨면 안 된다. */
interface SaveState {
  at: string;
  state: "saved" | "failed" | "conflict";
}

/** 멈춘 뒤 이만큼 지나면 임시본을 보낸다. 글자마다 보내지 않는다. */
const AUTOSAVE_MS = 800;
const WEEKDAY_NAMES = ["월", "화", "수", "목", "금", "토"];

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
  reflected: false,
  activities: [],
});
/** 깔아 두는 줄. 이름 · 시간은 있지만 교사가 손대기 전까지 올리지 않는다. */
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
  reflected: row.reflected ?? false,
  activities: row.activities ?? [],
});
/** 임시본 줄을 화면 줄로. 손대지 않은 줄은 깔았을 때 모습이 「되돌리기」 자리다. */
const restoredRow = (row: DraftRow): Row => {
  const start = routineTime(row.start);
  const end = routineTime(row.end);
  return {
    ...blankRow(),
    ...(row.id === null ? {} : { key: `server:${row.id}` }),
    id: row.id,
    start,
    end,
    name: row.name,
    plan: row.plan,
    execution: row.execution,
    touched: row.touched,
    base: row.touched ? null : { name: row.name, start, end },
    reflected: row.reflected ?? false,
    activities: row.activities ?? [],
  };
};
const toDraftRow = (row: Row): DraftRow => ({
  id: row.id,
  start: row.start || null,
  end: row.end || null,
  name: row.name.trim(),
  plan: row.plan,
  execution: row.execution,
  touched: row.touched,
  reflected: row.reflected,
  activities: row.activities,
});

/**
 * 읽어 온 하루 위에 초안을 세운다.
 *
 * 1. 아직 안 올라간 임시본이 있으면 그것이 교사가 마지막으로 쓴 모습이다.
 * 2. 없으면 그날 일과 기록. 읽자마자 시간순으로 세운다 — 번호가 겹친 지난 데이터도 교사 눈에는 시간 순이어야 한다.
 * 3. 그날이 비었으면 서버가 정한 깔 줄(반 기본 일과표 → 지난주 같은 요일 → 가장 최근 기록일), 그것도 없으면 표준 하루.
 */
function draftFrom(key: string, loaded: Loaded): Draft {
  const restored = loaded.draft && !loaded.draft.promoted ? loaded.draft : null;
  const presetRows = loaded.preset?.rows.length
    ? loaded.preset.rows.map((row) =>
        presetRow(row.name, routineTime(row.start), routineTime(row.end)),
      )
    : DEFAULT_ROUTINES.map(([name, start, end]) => presetRow(name, start, end));
  return {
    key,
    rows: restored
      ? restored.rows.map(restoredRow)
      : loaded.rows.length
        ? sortRoutinesByTime(loaded.rows.map(serverRow))
        : sortRoutinesByTime(presetRows),
    removed: restored?.removed ?? [],
    saved: Object.fromEntries(loaded.rows.map((row) => [row.id, row])),
    edits: 0,
    savedEdits: 0,
    promoted: !restored,
  };
}

/**
 * 한 칸이라도 적혀 있으면 「쓰던 줄」이다. 통째로 빈 줄은 올리지 않는다 (FR-402 예외).
 * 깔아 둔 줄은 교사가 손대기 전까지 세지 않는다 — 손대지 않은 하루를 올리지 않는다.
 * 서버(`routines/drafts.py` `filled`)와 같은 규칙이다.
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

/** 떠날 때 올려도 되는 하루인가. 막히는 줄이 있으면 임시본만 두고 올리지 않는다. */
const uploadable = (rows: Row[]) => rows.every((row) => !filled(row) || !problemWith(row));

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
 * **올릴 줄끼리만 본다.** 깔아 둔 기본 하루는 손대기 전까지 서버로 가지 않는다 —
 * 그걸 겹침으로 세면, 교사가 고른 몇 줄이 아직 손대지 않은 줄과 부딪혀 막힌다.
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

/** 서버에 적힌 것과 같은가. 자리(`position`)는 보지 않는다 — 그건 줄 단위 되돌리기가 아니다. */
const sameAsSaved = (row: Row, was: ApiRoutine) => {
  const back = serverRow(was);
  return (["start", "end", "name", "plan", "execution"] as const).every(
    (field) => (field === "name" ? row.name.trim() : row[field]) === back[field],
  );
};

/** 「이 일과를 쓴 보육일지 N건이 다시 검토 대상」 — 올린 뒤 화면에 남기는 한 줄. */
function impactText(impact: RoutineReviewImpact | null) {
  if (!impact) return "";
  const count = impact.newly_stale_document_ids.length;
  const already = impact.affected_document_ids.filter(
    (id) => !impact.newly_stale_document_ids.includes(id),
  ).length;
  const changed = count ? `이 일과를 쓴 보육일지 ${count}건이 다시 검토 대상이 되었어요.` : "";
  const previous = already
    ? ` 이미 재검토 대상인 보육일지 ${already}건도 이 변경의 영향을 받았어요.`
    : "";
  return (changed + previous).trim();
}

/** 월=0 … 토=5. 일요일은 기본 일과표 요일 줄이 없다(-1). */
const templateWeekday = (date: string) => (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7;

const NO_QUERY = { date: "", classId: null };
/** canonical route 의 `?date=&class_id=` (screen-spec S-J1). */
const fromQuery = () =>
  typeof window === "undefined" ? NO_QUERY : routinesScope(window.location.search);

/**
 * 일과 기록 — 반 하루의 일과를 한 줄씩 적는다 (screen-spec S-J1 · FR-402 · ADR-025).
 *
 * **AI 가 쓰지 않는다.** 활동실행은 있었던 일이라 모델이 채우면 위조다 (CLAUDE.md 문서 5분류).
 * 여기 적은 줄이 §11 일일 보육일지의 근거(`source_ids`)가 된다 — 관찰 기록이 아니다.
 *
 * **저장 단추가 없다** (ADR-084). 쓰는 대로 서버 임시본에 두고, 화면을 떠날 때(날짜 · 반을 옮김,
 * 다른 화면으로 감, 창을 닫음)와 「오늘 일지 만들기」 때 그날 일과 기록으로 한 번에 올린다.
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
  const [saveState, setSaveState] = useState<SaveState | null>(null);
  /** 교사가 고른 날씨. 그 화면(`key`)에서 고른 것만 쓴다. */
  const [chosenWeather, setChosenWeather] = useState<{ key: string; value: DayWeather } | null>(
    null,
  );
  /** 「기본 일과표로」 칸. 「요일만」을 누른 줄 열쇠를 들고 있는다. */
  const [template, setTemplate] = useState<Record<string, boolean> | null>(null);
  /**
   * 지금 요청이 도는 중인가. `busy` 는 **다시 그려져야** 버튼이 잠기므로, 그 사이에 한 번 더
   * 눌리면 같은 일이 두 번 간다. 렌더를 기다리지 않는 자물쇠가 따로 필요하다.
   */
  const running = useRef(false);
  /** 반 · 날짜(scope)마다 마지막으로 받은 임시본 판 번호. 앞 요청의 결과를 다음 요청이 따라간다. */
  const revisions = useRef(new Map<string, number>());
  /** 이 탭의 임시본 요청은 줄을 세워 하나씩 보낸다. */
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  /**
   * 화면(`key`)마다 근거로 올린 `edits`. 떠날 때 「이미 올렸나」를 여기서 본다 — 올린 뒤 다시
   * 그리기 전에 떠나면 초안의 `promoted` 는 아직 옛 값이다.
   */
  const uploaded = useRef(new Map<string, number>());
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
   * 보낸 느린 요청의 응답이 두 번째 A 화면에 들어온다. 방문 번호는 되돌아가지 않는다.
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
  const extras = useDayExtras(classId, validDate(date) ? date : "");

  /** 이 반·이 날짜. 방문이 달라도 **같은 자료**를 가리킨다 — 요청 대기줄의 칸이다. */
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
    // **이 반·날짜의 요청이 끝난 뒤에 읽는다.** 먼저 읽으면 커밋 전 값을 받아, 방금 올린
    // 줄이 빠진 화면이 된다. 하루치다 — 줄 · 날씨 · 임시본 · 깔 줄이 한 번에 온다.
    void (async () => {
      try {
        await waitForRoutineScope(scope);
        if (stale) return;
        const day = await getRoutineDay(classId, date);
        if (stale) return;
        revisions.current.set(scope, day.draft?.revision ?? 0);
        setLoaded({
          key,
          rows: day.items,
          draft: day.draft ?? null,
          preset: day.items.length ? null : (day.preset ?? null),
          weather: day.weather ?? null,
          error: "",
        });
      } catch (e) {
        if (!stale)
          setLoaded({
            key,
            rows: [],
            draft: null,
            preset: null,
            weather: null,
            error: messageFor(e),
          });
      }
    })();
    return () => {
      stale = true;
    };
  }, [classId, date, scope, key]);

  /**
   * 보고 있는 반 · 날짜를 주소에 적어 둔다 (P1-3). 적어 두지 않으면 반을 바꾼 뒤
   * 새로고침했을 때 주소에 남은 **옛 반**으로 되돌아간다.
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

  // 지금 반·날짜로 받은 값만 쓴다. 날짜를 바꾸는 동안 지난 날 일과가 남지 않는다.
  const current = loaded?.key === key ? loaded : null;
  // 새로 읽어 온 하루가 있으면 그 위에 초안을 세운다. **같은 열쇠면 손대지 않는다** —
  // 다시 그릴 때마다 세우면 교사가 적던 글이 날아간다.
  if (current && !current.error && draft?.key !== key) {
    setDraft(draftFrom(key, current));
    // 새 서버 snapshot 이다 — 지난 반·날짜에서 띄운 안내는 이 줄들과 상관이 없다.
    setErrors({});
  }
  const now = draft?.key === key ? draft : null;
  const rows = now?.rows ?? [];
  const weather = chosenWeather?.key === key ? chosenWeather.value : (current?.weather ?? null);
  const status = saveState?.at === key ? saveState.state : null;
  // 임시본을 못 둔 채로 창을 닫으려 하면 브라우저가 한 번 묻는다. 둔 글은 떠날 때 올라간다.
  useUnsavedWarning(status === "failed" || status === "conflict");

  /**
   * 시작한 그 화면이 아직 그대로인가. **요청은 끝까지 가되 화면은 건드리지 않는다** —
   * A 반을 올리는 사이 B 반으로 옮기면, 늦게 끝난 A 가 B 화면에 문구를 띄우거나
   * A 반 일지로 넘겨 버린다. 떠난 화면(`mounted === false`)도 마찬가지다.
   */
  const stillHere = (at: string) => active.current.mounted && active.current.key === at;

  /** 시작한 화면(`at`)이 아직 그 화면일 때만 초안을 고친다. */
  const patch = (at: string, change: (draft: Draft) => Draft) =>
    setDraft((prev) => (prev && prev.key === at ? change(prev) : prev));

  /** 교사가 고쳤다 — 임시본을 보내야 하고, 떠날 때 올려야 한다. */
  const change = (fn: (draft: Draft) => Draft) =>
    patch(key, (d) => ({ ...fn(d), edits: d.edits + 1, promoted: false }));

  const changeRow = (rowKey: string, fn: (row: Row) => Row) =>
    change((d) => ({
      ...d,
      rows: d.rows.map((row) => (row.key === rowKey ? { ...fn(row), touched: true } : row)),
    }));

  const editRow = (rowKey: string, field: Field, value: string) =>
    changeRow(rowKey, (row) => ({ ...row, [field]: value }));

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

  /** 「+ 줄 추가」. 빈 줄은 손대기 전까지 올라가지 않는다 (S-J1 동작표). */
  const addRow = () => change((d) => ({ ...d, rows: [...d.rows, blankRow()] }));

  /** 지우기. 올라간 줄이면 번호를 남겨 두고, 올릴 때 서버가 지운다. */
  const removeRow = (rowKey: string) =>
    change((d) => {
      const row = d.rows.find((r) => r.key === rowKey);
      return {
        ...d,
        rows: d.rows.filter((r) => r.key !== rowKey),
        removed: row?.id == null ? d.removed : [...d.removed, row.id],
      };
    });

  /** 그 줄만 마지막으로 읽은 일과 기록으로 되돌린다. 올라간 적 없는 줄은 깔았을 때로 (OLD TASK 2). */
  const revertRow = (rowKey: string) => {
    change((d) => ({
      ...d,
      rows: d.rows.map((row) => {
        if (row.key !== rowKey) return row;
        const was = row.id === null ? null : d.saved[row.id];
        if (was) return { ...serverRow(was), key: row.key, id: row.id, tone: row.tone };
        const base = row.base;
        return {
          ...blankRow(),
          key: row.key,
          tone: row.tone,
          base,
          ...(base ? { name: base.name, start: base.start, end: base.end } : {}),
        };
      }),
    }));
    setErrors((prev) => ({ ...prev, [rowKey]: "" }));
  };

  /** 서버에 적힌 것과 다른가. 올라간 적 없는 줄은 적힌 게 있으면 다르다. */
  const dirtyRow = (row: Row) => {
    const was = row.id === null ? null : now?.saved[row.id];
    return was ? !sameAsSaved(row, was) : filled(row);
  };

  /** 계획에서 고른 활동 — 실제로 한 것에 넣고, 맞다고 한 활동으로 남긴다 (ADR-086). */
  const pickActivity = (rowKey: string, activity: string) =>
    changeRow(rowKey, (row) => ({
      ...row,
      execution: appendLine(row.execution, activity),
      activities: row.activities.includes(activity)
        ? row.activities
        : [...row.activities, activity],
    }));

  /** 관찰 한 줄을 붙여 넣는다. 넣은 뒤의 글은 교사가 고친 일과 기록이다 (ADR-024 덧붙임). */
  const insertObservation = (rowKey: string, text: string) =>
    changeRow(rowKey, (row) => ({ ...row, execution: appendLine(row.execution, text) }));

  const toggleReflect = (rowKey: string) =>
    changeRow(rowKey, (row) => ({ ...row, reflected: !row.reflected }));

  /**
   * 보낼 수 있는 하루인가. 쓰던 줄인데 이름이 없으면 **아무것도 올리지 않고** 그 줄에
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
      // 손대지 않은 빈 줄은 검사하지 않는다 — 깔아 둔 줄이 전부 오류가 되면 안 된다.
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
     * 막으면 교사가 글자 하나 고치려고 남의 줄부터 손봐야 한다. 지금 만들어진 겹침만
     * 돌려보내고, 예전 것은 그대로 둔다.
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
   * 임시본을 보낸다. 판 번호는 **보내는 순간** 이 반 · 날짜의 마지막 값을 쓴다 — 앞 요청이 끝나야
   * 다음이 간다. 같은 반 · 날짜를 다시 읽는 조회는 이 요청이 끝난 뒤에 간다(`trackRoutineMutation`).
   */
  function send(
    target: { classId: number; date: string; scope: string },
    snapshot: Draft,
    promote: boolean,
    keepalive = false,
  ): Promise<DraftSaveResult> {
    const job = queue.current.then(async () => {
      const result = await saveRoutineDraft(
        {
          class_id: target.classId,
          date: target.date,
          expected_revision: revisions.current.get(target.scope) ?? 0,
          rows: snapshot.rows.map(toDraftRow),
          removed: snapshot.removed,
          promote,
        },
        { keepalive },
      );
      revisions.current.set(target.scope, result.draft.revision);
      return result;
    });
    queue.current = job.catch(() => undefined);
    return trackRoutineMutation(target.scope, job);
  }

  /** 멈춘 뒤 한 번 — 임시본만 둔다. 머리줄에 「저장됨」 · 「저장 못 했어요」. */
  async function autosave() {
    const at = key;
    const snapshot = now;
    if (classId === null || !snapshot || snapshot.edits === snapshot.savedEdits) return;
    try {
      await send({ classId, date, scope }, snapshot, false);
      patch(at, (d) => ({ ...d, savedEdits: Math.max(d.savedEdits, snapshot.edits) }));
      if (stillHere(at)) setSaveState({ at, state: "saved" });
    } catch (e) {
      if (stillHere(at)) setSaveState({ at, state: isStaleWrite(e) ? "conflict" : "failed" });
    }
  }

  /**
   * 근거로 올린다 — 하루치를 서버가 한 트랜잭션으로 일과 기록에 쓴다 (ADR-084).
   * 새 줄에 붙은 일과 번호를 이 화면 줄에 옮겨 둔다. 다시 올려도 같은 줄을 두 번 만들지 않는다.
   */
  async function upload(): Promise<DraftSaveResult | null> {
    const at = key;
    const snapshot = now;
    if (classId === null || !snapshot) return null;
    // 보내기 **전에** 적어 둔다. 기다리는 사이 화면을 떠나도 같은 하루를 또 올리지 않는다.
    uploaded.current.set(at, snapshot.edits);
    try {
      const result = await send({ classId, date, scope }, snapshot, true);
      const ids = new Map(
        snapshot.rows.map((row, index) => [row.key, result.draft.rows[index]?.id ?? row.id]),
      );
      patch(at, (d) => ({
        ...d,
        rows: d.rows.map((row) =>
          row.id === null ? { ...row, id: ids.get(row.key) ?? null } : row,
        ),
        removed: d.removed.filter((id) => !snapshot.removed.includes(id)),
        saved: Object.fromEntries((result.items ?? []).map((row) => [row.id, row])),
        savedEdits: Math.max(d.savedEdits, snapshot.edits),
        promoted: d.edits === snapshot.edits,
      }));
      if (stillHere(at)) setSaveState({ at, state: "saved" });
      return result;
    } catch (e) {
      uploaded.current.delete(at);
      if (stillHere(at)) {
        setSaveState({ at, state: isStaleWrite(e) ? "conflict" : "failed" });
        setMessage({ at, text: messageFor(e), error: true });
      }
      return null;
    }
  }

  /**
   * 화면을 떠난다 — 날짜 · 반을 옮기거나, 다른 화면으로 가거나, 창을 닫는다.
   * 안 올라간 하루가 있으면 올린다. 막히는 줄이 있으면 임시본만 둔다(다음에 열면 그대로다).
   * 창을 닫을 때도 요청 하나라 `keepalive` 로 끝까지 간다.
   */
  function leave() {
    const snapshot = now;
    if (classId === null || !snapshot || snapshot.promoted) return;
    if (uploaded.current.get(key) === snapshot.edits) return;
    const promote = uploadable(snapshot.rows);
    if (!promote && snapshot.edits === snapshot.savedEdits) return;
    void send({ classId, date, scope }, snapshot, promote, true).catch(() => undefined);
  }

  // 효과는 마지막 그림의 함수를 부른다 — 타이머 · 떠나기가 옛 하루를 보내지 않게.
  const latest = useRef({ autosave, leave });
  useEffect(() => {
    latest.current = { autosave, leave };
  });
  const edits = now?.edits ?? 0;
  useEffect(() => {
    if (!edits) return;
    const timer = setTimeout(() => void latest.current.autosave(), AUTOSAVE_MS);
    return () => clearTimeout(timer);
  }, [edits, key]);
  // 열쇠가 바뀌면(날짜 · 반 · 다시 읽기) 그리고 화면이 사라지면 그 하루를 떠난 것이다.
  useEffect(() => () => latest.current.leave(), [key]);
  useEffect(() => {
    const hide = () => latest.current.leave();
    window.addEventListener("pagehide", hide);
    return () => window.removeEventListener("pagehide", hide);
  }, []);

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

  /**
   * 「오늘 일지 만들기」 — **근거로 올리고 이 화면에서 연다** (S-J1 수락 기준 3-1).
   * 올리는 것이 실패하면 만들지 않는다. 적은 글자는 그대로 남는다.
   */
  const openDailyLog = () => {
    const at = key;
    const next = `${scope}|${visit + 1}`;
    if (!checkRows()) return;
    return run("open", async () => {
      const done = await upload();
      if (!done || !stillHere(at)) return;
      // 근거는 **실제로 한 것을 적은 줄의 일과 번호**다. 다시 조회해서 찾지 않는다.
      const evidence = (done.items ?? [])
        .filter((row) => row.execution.trim())
        .map((row) => routineLocalId(row.id));
      await journal.make(evidence);
      const impact = impactText(done.review_impact);
      if (impact) setMessage({ at: next, text: impact });
      revisit();
    });
  };

  /** 「다시」 아이콘 — 실패면 다시 보내고, 다른 화면이 먼저 고쳤으면 그 판을 다시 읽는다. */
  const retrySave = () => {
    if (status === "conflict") return revisit();
    patch(key, (d) => ({ ...d, savedEdits: Math.min(d.savedEdits, d.edits - 1) }));
    void autosave();
  };

  /** 날씨를 고른다 (ADR-089). 실패하면 알리고 그대로 둔다. */
  async function chooseWeather(sky: Sky | null) {
    const at = key;
    if (classId === null) return;
    try {
      const value = await chooseRoutineWeather({ class_id: classId, date, sky });
      if (stillHere(at)) setChosenWeather({ key: at, value });
    } catch (e) {
      if (stillHere(at)) setNotice(messageFor(e));
    }
  }

  /**
   * 이 하루를 반 기본 일과표로 둔다 (ADR-085). 「요일만」을 누른 줄은 그 요일에만 더하는 줄,
   * 나머지는 날마다 까는 고정 줄이다. 다른 요일에 더하는 줄은 그대로 둔다.
   */
  async function saveTemplate() {
    const picks = template ?? {};
    if (classId === null || !now) return;
    const weekday = templateWeekday(date);
    try {
      const before = await getRoutineTemplate(classId);
      const others = (before?.rows ?? []).filter(
        (row) => row.weekday != null && row.weekday !== weekday,
      );
      const mine = now.rows
        .filter((row) => row.name.trim())
        .map((row) => ({
          name: row.name.trim(),
          start: row.start || null,
          end: row.end || null,
          ...(picks[row.key] && weekday < 6 ? { weekday } : {}),
        }));
      await saveRoutineTemplate(classId, [...mine, ...others]);
      setTemplate(null);
      setNotice("반 기본 일과표로 두었어요. 새 날은 이 표로 깔아요.");
    } catch (e) {
      setNotice(messageFor(e));
    }
  }

  const classStatus: ViewStatus = classList ? (classList.error ? "error" : "ready") : "loading";
  const noClasses = classStatus === "ready" && !classes?.length;
  const dateOk = validDate(date);
  const needClass = classStatus === "ready" && !noClasses && classId === null;
  // 날짜나 반이 없으면 조회를 보내지 않는다 — 그걸 「불러오는 중」으로 두면 영영 안 끝난다.
  const listStatus: ViewStatus =
    !dateOk || needClass ? "ready" : current ? (current.error ? "error" : "ready") : "loading";
  const ready = listStatus === "ready" && dateOk && !needClass;
  // 활동실행을 적은 줄 수 (FR-402 출력). **화면에 적힌 것으로 센다** — 올리기 전이어도 센다.
  const doneCount = rows.filter((row) => row.execution.trim()).length;
  /** 날짜를 옮긴다. 이 하루는 떠나면서 올라간다 — 일과는 묻지 않고, 펴 놓은 일지에 저장 안 한 글만 묻는다. */
  const moveTo = (next: string, month: string | null) => {
    if (!journal.leave()) return;
    setPickedDate(next);
    setPickedMonth(month);
    revisit();
  };
  const preset =
    now && !now.edits && !current?.rows.length && !current?.draft ? current?.preset : null;
  const weekday = templateWeekday(date);

  return (
    <WorkspacePage
      title="보육일지"
      /* 「일일 보육일지가 이 기록을 근거로 쓴다」는 설명은 뺐다. 화면에 들어온 교사는
         이미 일과를 적으러 온 것이고, 제목 밑 한 줄은 매일 읽히지 않는다. */
      description=""
      /*
        저장 단추는 없다(ADR-084). 머리줄에는 저장 상태 한 단어와 「오늘 일지 만들기」만 둔다.
        「+ 줄 추가」는 목록 끝에 남긴다 — 새 줄이 생기는 자리가 거기다.
      */
      action={
        ready ? (
          <div className={ws.actions} data-tour="routines-actions">
            <SaveStatus state={status} onRetry={retrySave} />
            {/*
              적은 줄이 하나라도 있으면 켠다 — **올렸는지로 판단하지 않는다** (수락 기준 3).
              누르면 먼저 올리고, 성공해야 일지를 만든다.
            */}
            <button
              type="button"
              className={ws.primary}
              disabled={!!busy || !doneCount}
              title={doneCount ? undefined : "실제로 한 것을 한 줄이라도 적어 주세요."}
              onClick={openDailyLog}
            >
              {busy === "open" ? "만드는 중…" : "오늘 일지 만들기 →"}
            </button>
          </div>
        ) : undefined
      }
    >
      <JournalTabs at="daily" daily="/routines" weekly="/weekly-records" />
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
              {/* 안내문을 지우고 그 자리에 날짜를 손글씨로 둔다. 날씨는 날짜 바로 옆이다. */}
              <div className={css.dayHead}>
                <h2 className={ws.sheetDay}>
                  {koreanDay(dateOk ? date : todayDate).day}
                  <span>
                    {koreanDay(dateOk ? date : todayDate).dow}
                    <CircleMark />
                  </span>
                </h2>
                <RoutineWeather weather={weather} disabled={!!busy} onChoose={chooseWeather} />
              </div>
              {/* 교실 칠판에 일과 쪽지를 붙인 모습 (첫 화면 오른쪽 줄과 같은 판이다).
                  줄마다 종이 한 장이라 어디서 한 일과가 끝나는지 선을 안 그어도 보인다. */}
              <div
                className={`${ws.routineSheet} chalkboard`}
                aria-label="일과 목록"
                data-tour="routines-board"
              >
                {preset && <p className={css.presetNote}>{presetNote(preset)}</p>}
                {journal.yesterday && (
                  <aside className={css.yesterday} aria-label="어제 지원">
                    <span className={css.tape} aria-hidden="true" />
                    <b>어제 지원</b>
                    <p>{journal.yesterday}</p>
                    <small>반영한 줄의 「반영」을 누르세요.</small>
                  </aside>
                )}
                {rows.map((row, index) => (
                  <RowCard
                    key={row.key}
                    row={row}
                    index={index}
                    error={errors[row.key] ?? ""}
                    busy={!!busy}
                    dirty={dirtyRow(row)}
                    reflecting={!!journal.yesterday}
                    onEdit={editRow}
                    onTimeSet={timeSet}
                    onRevert={revertRow}
                    onRemove={removeRow}
                    onReflect={toggleReflect}
                  >
                    <RoutineRowExtras
                      candidates={planCandidates(row.name, extras.plan).filter(
                        (name) => !row.activities.includes(name),
                      )}
                      plan={
                        extras.plan && !planCandidates(row.name, extras.plan).length
                          ? extras.plan.all
                          : null
                      }
                      observed={extras.observations.filter((o) =>
                        contextMatches(o.context, row.name),
                      )}
                      outdoor={needsOutdoorSwap(row.name, weather?.indoor_hint ?? null)}
                      disabled={!!busy}
                      onPick={(activity) => pickActivity(row.key, activity)}
                      onInsert={(text) => insertObservation(row.key, text)}
                      onRename={(name) => editRow(row.key, "name", name)}
                    />
                  </RowCard>
                ))}
                <div className={ws.rowTools}>
                  <button type="button" className={ws.rowTool} disabled={!!busy} onClick={addRow}>
                    + 줄 추가
                  </button>
                  <button
                    type="button"
                    className={ws.rowTool}
                    disabled={!!busy}
                    aria-expanded={template !== null}
                    onClick={() => setTemplate(template ? null : {})}
                  >
                    기본 일과표로
                  </button>
                </div>
                {template && (
                  <TemplatePanel
                    rows={rows}
                    weekday={weekday < 6 ? WEEKDAY_NAMES[weekday] : null}
                    picks={template}
                    onPick={(rowKey) => setTemplate({ ...template, [rowKey]: !template[rowKey] })}
                    onSave={saveTemplate}
                    onCancel={() => setTemplate(null)}
                  />
                )}
              </div>
            </WorkspaceViewState>
            {listStatus === "error" && (
              <button type="button" className={ws.secondary} onClick={revisit}>
                다시 시도
              </button>
            )}
            {/* 편집기는 칠판 바로 아래다 — 방금 적은 일과를 보며 손봐야 한다. */}
            {ready && (
              <DailyJournalEditor state={journal} day={koreanDay(date).day} weather={weather} />
            )}
          </section>
        </div>
      </WorkspaceViewState>
      <Notice onDone={() => setNotice("")}>{notice}</Notice>
    </WorkspacePage>
  );
}

/** 머리줄 저장 상태 — 「저장됨」 한 단어, 실패면 「저장 못 했어요」와 다시 아이콘. */
function SaveStatus({ state, onRetry }: { state: SaveState["state"] | null; onRetry: () => void }) {
  if (!state) return null;
  if (state === "saved")
    return (
      <span className={css.saveState} role="status">
        저장됨
      </span>
    );
  const conflict = state === "conflict";
  return (
    <span className={css.saveState} data-state={state} role="alert">
      {conflict ? "다른 화면에서 먼저 고쳤어요" : "저장 못 했어요"}
      <button
        type="button"
        className={css.iconButton}
        aria-label={conflict ? "다시 불러오기" : "다시 저장"}
        title={conflict ? "다시 불러오기" : "다시 저장"}
        onClick={onRetry}
      >
        <RetryMark />
      </button>
    </span>
  );
}

/** 「기본 일과표로」 — 이 하루의 줄을 표로 둔다. 요일에만 더하는 줄은 「{요일}만」을 누른다. */
function TemplatePanel({
  rows,
  weekday,
  picks,
  onPick,
  onSave,
  onCancel,
}: {
  rows: Row[];
  /** 「월」. 일요일이면 null — 요일 줄을 둘 수 없다. */
  weekday: string | null;
  picks: Record<string, boolean>;
  onPick: (rowKey: string) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  const named = rows.filter((row) => row.name.trim());
  return (
    <section className={css.template} aria-label="반 기본 일과표">
      <p>이 하루의 순서 · 시간 · 이름을 새 날마다 깔아요. 적은 글은 옮기지 않아요.</p>
      <ul>
        {named.map((row) => (
          <li key={row.key}>
            <span>
              {row.start || row.end ? `${row.start} ~ ${row.end}  ` : ""}
              {row.name.trim()}
            </span>
            {weekday && (
              <label>
                <input
                  type="checkbox"
                  checked={!!picks[row.key]}
                  onChange={() => onPick(row.key)}
                />
                {weekday}요일만
              </label>
            )}
          </li>
        ))}
      </ul>
      <div className={ws.actions}>
        <button type="button" className={ws.secondary} onClick={onSave}>
          기본 일과표로 두기
        </button>
        <button type="button" className={ws.rowTool} onClick={onCancel}>
          닫기
        </button>
      </div>
    </section>
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
  reflecting,
  onEdit,
  onTimeSet,
  onRevert,
  onRemove,
  onReflect,
  children,
}: {
  row: Row;
  index: number;
  error: string;
  busy: boolean;
  dirty: boolean;
  /** 어제 지원 쪽지가 떠 있다 — 줄마다 「반영」 도장을 누를 수 있다. */
  reflecting: boolean;
  onEdit: (rowKey: string, field: Field, value: string) => void;
  onTimeSet: (rowKey: string) => void;
  onRevert: (rowKey: string) => void;
  onRemove: (rowKey: string) => void;
  onReflect: (rowKey: string) => void;
  /** 줄 아래 계획 후보 · 관찰 끌어오기 (`RoutineRowExtras`). */
  children?: ReactNode;
}) {
  const set = (field: Field) => (value: string) => onEdit(row.key, field, value);
  // 「계획한 것」을 교사가 펼쳤으면 글을 다 지워도 접지 않는다. 글이 있는지만 보고 접었더니
  // 적다가 백스페이스로 비우는 순간 칸이 닫혀 커서를 잃었다(덕철 점검).
  const [planOpen, setPlanOpen] = useState(false);
  return (
    <article className={ws.routineRow} data-tone={row.tone} data-lean={row.tone % 2}>
      <div className={ws.routineHead}>
        {(reflecting || row.reflected) && (
          <button
            type="button"
            className={css.stamp}
            aria-pressed={row.reflected}
            aria-label={`${index + 1}번째 일과에 어제 지원 반영`}
            disabled={busy}
            onClick={() => onReflect(row.key)}
          >
            <span>반영</span>
          </button>
        )}
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
        // 서버 칸이 5,000자다. 넘기면 임시본이 통째로 거절된다.
        maxLength={5000}
        value={row.execution}
        onChange={(e) => set("execution")(e.target.value)}
      />
      {children}

      {/* 「계획한 것」은 안 쓰는 원이 많다. 적은 줄만 펴 두고 나머지는 접는다. */}
      {/* 이름은 안의 글칸 하나만 갖는다. 접는 칸에도 같은 이름을 달면 「계획한 것」을 찾는
          보조기기 · 테스트가 둘을 만나 어느 쪽인지 모른다. 접는 칸은 summary 글자로 읽힌다. */}
      <details
        className={ws.rowPlan}
        open={planOpen || !!row.plan}
        onToggle={(e) => setPlanOpen(e.currentTarget.open)}
      >
        <summary>{row.plan ? "계획한 것" : "계획한 것 적기"} ▾</summary>
        <textarea
          aria-label="계획한 것"
          placeholder="계획한 것"
          maxLength={5000}
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

/** 다시 — 한 바퀴 도는 화살표. 「다시」 글자 대신 아이콘 단추에 쓴다. */
function RetryMark() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        d="M20 12a8 8 0 1 1-2.3-5.6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
      />
      <path
        d="M20 4v5h-5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
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
