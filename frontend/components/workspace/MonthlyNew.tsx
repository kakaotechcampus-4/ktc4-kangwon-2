"use client";

/**
 * 월간계획안 만들기(Ⓜ1) — 연간을 확정한 뒤. 월별 주제형 · 놀이 중심형이 한 틀이다.
 * 달 12칸(확정한 달은 잠김, 작성 중인 달은 누르면 그 초안으로), 연간에서 이어받는 내용,
 * 놀이형은 이번 달에 집중할 놀이(`emphasized_row_keys`). 만드는 동안은 원형 화면(Ⓜ2)이다.
 * 월별 주제형은 넣을 칸도 여기서 고른다(따로 양식 화면이 없다). 고른 칸이 지금 양식과 다르면
 * 새 양식(§9-4)을 만들어 원 기본으로 걸고 그 양식으로 만든다.
 * 요청 사항(메모)은 버튼 위에 둔다(ADR-060). 두 형식 모두 받는다.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { existingAfterConflict } from "@/lib/api/conflict";
import { memoError, PlanMemoField } from "@/components/plan-generator/PlanMemo";
import { createMonthlyPlan, listMonthlyPlans } from "@/lib/api/monthly";
import { createPlayMonthly, listPlayMonthly } from "@/lib/api/playMonthly";
import { getAnnualPlan, listAnnualPlans } from "@/lib/api/plans";
import { syncCenter, syncClass } from "@/lib/api/onboarding";
import {
  createTemplateProfile,
  getCenterDefaultProfile,
  getClassTemplateProfile,
  listMonthlyTemplates,
  listReadyTemplateProfiles,
  putCenterDefaultProfile,
} from "@/lib/api/templateProfiles";
import type {
  AnnualPlanResponse,
  MonthlyTemplate,
  ProfileRef,
  ReadyProfile,
  TemplateProfileInput,
} from "@/lib/api/types";
import { sectionName } from "@/lib/monthly/section-labels";
import { chosenClassFor, loadClassSettings } from "@/lib/onboarding/settings";
import { MONTH_ORDER } from "@/lib/onboarding/types";
import { useClientState } from "@/lib/hooks/use-client-state";
import { playSeason } from "@/components/plan-generator/playProjectPagination";
import GenerationRing, { ringFinished } from "@/components/plan-ui/GenerationRing";
import { useCompactShell } from "@/components/app/compact-shell";
import { BACK_BUTTON, BACK_ICON } from "@/components/plan-generator/AnnualFrame";
import { Tape, useClasses } from "./WorkspaceUI";

type Status = { id: number; status: "DRAFT" | "CONFIRMED" };
type Plans = Record<number, Status>;
export type Inherit =
  | { kind: "theme"; theme: string; subs: string[] }
  | { kind: "play"; season: string; plays: { row_key: string; name: string }[] };

const LOOK = {
  theme: {
    name: "월별 주제형",
    chip: "bg-[#e8f1ea] text-[#3b5441]",
    form: "소주제형 월간 양식",
    image: "monthly-theme-month",
    steps: (m: number) => [`${m}월 주제 이어받기`, "주별 놀이 나누기", "문서로 정리하기"],
  },
  play: {
    name: "놀이 중심형",
    chip: "bg-[#eee4f4] text-[#5e4b96]",
    form: "놀이 중심형 월간 양식",
    image: "play-monthly",
    steps: (_: number, season = "") => [
      `${season} 놀이 이어받기`.trim(),
      "함께 할 활동 정하기",
      "문서로 정리하기",
    ],
  },
} as const;

/** 처음 고를 달: 이번 달부터 학년도 순서로 아직 계획안이 없는 첫 달. 다 있으면 이번 달. */
export function firstOpenMonth(now: number, plans: Plans) {
  const start = MONTH_ORDER.indexOf(now as (typeof MONTH_ORDER)[number]);
  const order = [...MONTH_ORDER.slice(start), ...MONTH_ORDER.slice(0, start)];
  return order.find((m) => !plans[m]) ?? now;
}

/** 연간에서 그 달로 이어받는 것. 월별 주제형 = 생활주제 + 소주제, 놀이형 = 그 계절에 고른 놀이. */
export function inheritOf(annual: AnnualPlanResponse | null, month: number): Inherit | null {
  if (!annual) return null;
  if (annual.format === "MONTHLY_THEME") {
    const m = annual.months.find((x) => x.month === month);
    return m ? { kind: "theme", theme: m.theme, subs: m.sub_themes } : null;
  }
  const period = annual.periods.find((p) => p.months.includes(month));
  if (!period) return null;
  return {
    kind: "play",
    season: playSeason(period).name,
    plays: period.selected.flatMap((key) => {
      const c = period.candidates.find((x) => x.row_key === key);
      return c ? [{ row_key: key, name: c.play_name.value }] : [];
    }),
  };
}

/**
 * 칸을 고를 기반 양식: 승인된 최신 판. 옛 판은 그 판으로 만든 양식 · 계획안을 열려고 남아 있을 뿐,
 * 새로 고르는 칸은 늘 최신 판으로 만든다(판이 오를수록 고를 수 있는 칸이 늘었다).
 */
export const pickTemplate = (items: MonthlyTemplate[]) =>
  items
    .filter((t) => t.approved)
    .sort((a, b) =>
      a.template_ref.template_version.localeCompare(b.template_ref.template_version, undefined, {
        numeric: true,
      }),
    )
    .pop() ?? null;

/** 처음 켜 둘 칸: 지금 양식에서 켠 칸 중 이 기반 양식이 고르게 하는 것. */
export const firstExtras = (template: MonthlyTemplate, current: ReadyProfile | null) =>
  (current?.selected_optional_keys ?? []).filter((k) =>
    template.sections.some((s) => s.section_key === k && s.selection === "OPTIONAL"),
  );

/** 지금 양식이 고른 칸과 같으면 그대로 쓴다 — 같은 양식을 또 만들지 않는다. */
export const sameColumns = (
  current: ReadyProfile | null,
  template: MonthlyTemplate,
  extras: string[],
) =>
  !!current &&
  current.base_template_ref.template_version === template.template_ref.template_version &&
  current.base_template_ref.template_id === template.template_ref.template_id &&
  current.selected_optional_keys.length === extras.length &&
  extras.every((k) => current.selected_optional_keys.includes(k));

/**
 * 고른 칸으로 원 양식(Profile)을 시작하는 요청 (§9-4).
 * 화면 이름을 같이 보낸다 — 안 보내면 표의 행 이름이 기계 이름으로 뜬다.
 * 소주제를 켜면 그 뜻도 보내야 서버가 받는다(없으면 422 `focus_variant`). 화면이 「소주제」라 부르니 SUBTHEME.
 */
export function profileInput(template: MonthlyTemplate, extras: string[]): TemplateProfileInput {
  const shown = template.sections.filter(
    (s) =>
      s.selection === "REQUIRED" || (s.selection === "OPTIONAL" && extras.includes(s.section_key)),
  );
  const variants = template.focus_variants;
  return {
    base_template_ref: template.template_ref,
    selected_optional_keys: extras,
    display_labels: Object.fromEntries(
      shown.map((s) => [s.section_key, sectionName(s.section_key, s.label)]),
    ),
    focus_variant: extras.includes("focus")
      ? variants.includes("SUBTHEME")
        ? "SUBTHEME"
        : (variants[0] ?? "SUBTHEME")
      : null,
  };
}

export function MonthlyNewView(props: {
  play: boolean;
  back: { href: string; label: string };
  month: number;
  plans: Plans;
  inherit: Inherit | null;
  focus: string[];
  /** 월별 주제형만: 칸을 고를 기반 양식과 더 넣을 칸. 이미 있는 달은 고르지 않는다. */
  template?: MonthlyTemplate | null;
  extras?: string[];
  onExtras?: (keys: string[]) => void;
  /** 만들 수 없는 까닭(버튼 아래 한 줄). null 이면 만들 수 있다. */
  blocked: ReactNode;
  problem: string;
  /** 요청 사항(ADR-060). 없으면 칸을 그리지 않는다(미리보기). */
  memo?: string;
  memoProblem?: string | null;
  onMemo?: (memo: string) => void;
  onMonth: (month: number) => void;
  onFocus: (keys: string[]) => void;
  onCreate: () => void;
}) {
  const { play, month, plans, inherit, focus, blocked, template, extras = [] } = props;
  const look = play ? LOOK.play : LOOK.theme;
  return (
    <div className="flex w-full flex-col gap-4 px-10 pb-6 pt-[26px] text-[#2b2826] lg:h-[calc(100vh-60px)]">
      <div className="relative grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <Tape />
        <section className="flex min-h-0 flex-col gap-5 overflow-y-auto border border-line bg-paper rounded-md p-7">
          {/* 왼쪽 판 맨 위: 제목 앞 「←」 돌아가기(편집 화면과 같은 버튼) · 방식. */}
          <div className="flex shrink-0 flex-col">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <Link
                href={props.back.href}
                aria-label={`돌아가기: ${props.back.label}`}
                title={props.back.label}
                className={BACK_BUTTON}
              >
                {BACK_ICON}
              </Link>
              <h1 className="m-0 font-display text-[34px] font-bold leading-[1.2] text-ink">
                월간계획안 만들기
              </h1>
              <span className={`rounded-full px-3 py-1 text-[13px] font-bold ${look.chip}`}>
                {look.name}
              </span>
            </div>
          </div>

          <div className="flex shrink-0 flex-col gap-2.5">
            <h2 className="m-0 font-display text-[24px] font-bold leading-tight text-ink">
              어떤 달을 만들까요?
            </h2>
            <div role="radiogroup" aria-label="달" className="grid grid-cols-6 gap-1.5">
              {MONTH_ORDER.map((m) => {
                const st = plans[m]?.status;
                const sel = m === month;
                return (
                  <button
                    key={m}
                    type="button"
                    role="radio"
                    aria-checked={sel}
                    disabled={st === "CONFIRMED"}
                    onClick={() => props.onMonth(m)}
                    className={`flex min-h-[46px] flex-col items-center justify-center rounded-md border text-[15px] leading-tight ${
                      sel
                        ? "border-[#7053a0] bg-[#f6f1fb] font-bold text-[#4a3780]"
                        : st === "CONFIRMED"
                          ? "border-transparent bg-[#f3efe8] text-[#8a8178]"
                          : "border-[#e8e2d8] hover:border-[#c5b7dd]"
                    }`}
                  >
                    {m}월
                    {st === "CONFIRMED" && (
                      <span className="text-[11px] font-bold text-[#3b5441]">✓ 확정</span>
                    )}
                    {st === "DRAFT" && (
                      <span className="text-[11px] font-bold text-[#7053a0]">작성 중</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex shrink-0 flex-col gap-2.5">
            <div className="flex items-baseline justify-between">
              <h2 className="m-0 font-display text-[24px] font-bold leading-tight text-ink">
                연간에서 이어받아요
              </h2>
            </div>
            {!inherit && (
              <p className="m-0 rounded-md bg-[#f7f4ee] px-4 py-3 text-sm text-[#5c5243]">
                연간계획안에서 이 달의 내용을 찾지 못했어요.
              </p>
            )}
            {inherit?.kind === "theme" && (
              <div className="rounded-md bg-[#f7f4ee] px-4 py-3">
                <div className="text-[17px] font-bold">{inherit.theme || "생활주제 없음"}</div>
                <ol className="m-0 mt-2 grid list-none grid-cols-2 gap-x-4 gap-y-1 p-0 text-[14px]">
                  {inherit.subs.map((s, i) => (
                    <li key={i}>
                      <span className="mr-1.5 text-xs font-bold text-[#3b5441]">{i + 1}주</span>
                      {s}
                    </li>
                  ))}
                </ol>
              </div>
            )}
            {inherit?.kind === "play" && (
              <fieldset className="m-0 flex flex-col gap-1.5 border-0 p-0">
                <legend className="mb-1.5 p-0 text-[13px] text-[#5c5243]">
                  이번 달에 더 집중할 놀이를 골라요 (안 골라도 돼요)
                </legend>
                {inherit.plays.map((p) => {
                  const on = focus.includes(p.row_key);
                  return (
                    <label
                      key={p.row_key}
                      className={`flex min-h-[44px] cursor-pointer items-center gap-3 rounded-lg px-3 text-[14px] ${on ? "bg-[#f6f1fb] font-bold" : "bg-[#f7f4ee]"}`}
                    >
                      <input
                        type="checkbox"
                        checked={on}
                        onChange={() =>
                          props.onFocus(
                            on ? focus.filter((k) => k !== p.row_key) : [...focus, p.row_key],
                          )
                        }
                        className="h-[18px] w-[18px] accent-[#7053a0]"
                      />
                      {p.name}
                    </label>
                  );
                })}
              </fieldset>
            )}
          </div>

          {!play && template && !plans[month] && (
            <fieldset className="m-0 flex shrink-0 flex-col gap-1.5 border-0 p-0">
              <legend className="mb-2.5 p-0 font-display text-[24px] font-bold leading-tight text-ink">
                어떤 칸을 넣을까요?
              </legend>
              <p className="m-0 text-[13px] text-[#5c5243]">
                꼭 들어가요 ·{" "}
                {template.sections
                  .filter((s) => s.selection === "REQUIRED")
                  .map((s) => sectionName(s.section_key, s.label))
                  .join(" · ")}
              </p>
              <div className="grid gap-1.5 sm:grid-cols-2">
                {template.sections
                  .filter((s) => s.selection === "OPTIONAL")
                  .map((s) => {
                    const on = extras.includes(s.section_key);
                    return (
                      <label
                        key={s.section_key}
                        className={`flex min-h-[44px] cursor-pointer items-center gap-3 rounded-lg px-3 text-[14px] ${on ? "bg-[#f6f1fb] font-bold" : "bg-[#f7f4ee]"}`}
                      >
                        <input
                          type="checkbox"
                          checked={on}
                          onChange={() =>
                            props.onExtras?.(
                              on
                                ? extras.filter((k) => k !== s.section_key)
                                : [...extras, s.section_key],
                            )
                          }
                          className="h-[18px] w-[18px] accent-[#7053a0]"
                        />
                        {sectionName(s.section_key, s.label)}
                        <span className="ml-auto text-[12px] font-normal text-ink-soft">
                          {s.repeat_by === "WEEK" ? "주마다" : "한 달에 한 번"}
                        </span>
                      </label>
                    );
                  })}
              </div>
            </fieldset>
          )}

          {props.onMemo && !plans[month] && (
            <PlanMemoField
              value={props.memo ?? ""}
              onChange={props.onMemo}
              error={props.memoProblem}
              chips={["바깥놀이 많이", "비 오는 날 대체활동", "행사 반영"]}
              placeholder="예) 셋째 주는 비 소식이 있어 실내 활동을 넉넉히"
            />
          )}

          {props.problem && (
            <p
              role="alert"
              className="m-0 rounded-md bg-[#fbeaea] px-4 py-3 text-sm text-[#8a2f2f]"
            >
              {props.problem}
            </p>
          )}

          {/* 만들기 단추는 화면 아래에 붙여 둔다 — 낮은 화면(1440×900)에서도 스크롤 없이 보이게. */}
          <div className="sticky bottom-0 z-10 mt-auto flex shrink-0 flex-col gap-2 bg-paper pb-1 pt-2">
            <button
              type="button"
              onClick={props.onCreate}
              disabled={!!blocked}
              className="min-h-[54px] rounded-md bg-primary hover:bg-primary-hover text-[17px] font-bold text-white disabled:cursor-not-allowed disabled:bg-[#ddd6ca] disabled:text-ink-soft transition-transform active:translate-x-[2px] active:translate-y-[3px] active:shadow-none"
            >
              {plans[month] ? `${month}월 월간계획안 열기` : `${month}월 월간계획안 만들기`}
            </button>
            {blocked && <p className="m-0 text-sm text-[#5c5243]">{blocked}</p>}
          </div>
        </section>

        <section
          aria-label="양식 미리보기"
          className="flex min-h-[420px] flex-col border border-shell-line bg-shell-hover shadow-[inset_0_1px_4px_rgba(52,49,47,0.08)] p-3"
        >
          <p className="m-0 mb-2 text-[13px] text-ink-soft">
            양식 예시예요. 만들면 고른 달 · 반의 내용으로 채워져요.
          </p>
          <div className="relative min-h-0 flex-1">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`/plan-formats/${look.image}.png`}
              alt={`${look.form} 예시`}
              className="absolute inset-x-0 top-0 mx-auto max-h-full max-w-full rounded-md border border-[#e3ddd2] bg-white object-contain object-top shadow-[0_1px_2px_rgba(43,40,38,0.1),0_14px_32px_-14px_rgba(43,40,38,0.35)]"
            />
          </div>
        </section>
      </div>
    </div>
  );
}

type Loaded = {
  classId: number;
  annual: AnnualPlanResponse | null;
  plans: Plans;
  /** 월별 주제형만. 원 id · 칸을 고를 기반 양식 · 반이 지금 쓰는 양식 · 원 기본 포인터. */
  centerId: number | null;
  template: MonthlyTemplate | null;
  current: ReadyProfile | null;
  pointer: ProfileRef | null;
};

const sameRef = (a: ProfileRef | null, b: ProfileRef | null) =>
  !!a && !!b && a.profile_id === b.profile_id && a.profile_version === b.profile_version;

/** 월별 주제형 칸 고르기에 필요한 것. 서버에 양식이 하나도 없어도 화면은 뜬다. */
async function loadColumns(
  settings: NonNullable<ReturnType<typeof loadClassSettings>>,
  classId: number,
) {
  const centerId = await syncCenter(settings);
  const [templates, ready, resolved, pointer] = await Promise.all([
    listMonthlyTemplates(),
    listReadyTemplateProfiles(centerId),
    getClassTemplateProfile(classId),
    getCenterDefaultProfile(centerId),
  ]);
  const current = ready.items.find((p) => sameRef(p.profile_ref, resolved.profile_ref)) ?? null;
  return {
    centerId,
    template: pickTemplate(templates.items),
    current,
    pointer: pointer.profile_ref,
  };
}

/** 고른 반의 연간 · 월간 목록 · 양식을 읽어 Ⓜ1 을 띄운다. 월별 주제형 초안은 `onOpen` 으로 연다. */
export default function MonthlyNew({
  onOpen,
}: {
  onOpen: (plan: { id: number; classId: number; month: number }) => void;
}) {
  const router = useRouter();
  const [problem, setProblem] = useState("");
  const [memo, setMemo] = useState("");
  const [memoProblem, setMemoProblem] = useState<string | null>(null);
  const classes = useClasses(setProblem);
  const [chosen] = useClientState(() => chosenClassFor(loadClassSettings())?.id ?? "", "");
  const local = classes.find((c) => c.id === chosen) ?? classes[0];
  const [data, setData] = useState<Loaded | null>(null);
  const [month, setMonth] = useState<number | null>(null);
  const [focus, setFocus] = useState<string[]>([]);
  const [extras, setExtras] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useCompactShell(busy);
  useEffect(() => () => controller.current?.abort(), []);

  useEffect(() => {
    let alive = true;
    (async () => {
      const settings = loadClassSettings();
      if (!settings || !local) return;
      try {
        const classId = await syncClass(settings, local);
        const summary = (await listAnnualPlans(classId)).items[0];
        const annual = summary ? await getAnnualPlan(summary.id) : null;
        const play = annual?.format === "PLAY_PROJECT";
        const none = { centerId: null, template: null, current: null, pointer: null };
        const [list, columns] = await Promise.all([
          play ? listPlayMonthly(classId) : listMonthlyPlans(classId),
          play || !annual ? none : loadColumns(settings, classId),
        ]);
        const plans: Plans = Object.fromEntries(
          list.items.map((p) => [p.month, { id: p.id, status: p.status }]),
        );
        if (!alive) return;
        setData({ classId, annual, plans, ...columns });
        if (columns.template) setExtras(firstExtras(columns.template, columns.current));
        setMonth((m) => m ?? firstOpenMonth(new Date().getMonth() + 1, plans));
      } catch (e) {
        if (alive) setProblem(e instanceof Error ? e.message : "불러오지 못했어요.");
      }
    })();
    return () => {
      alive = false;
    };
  }, [local]);

  if (!data || month === null)
    return problem ? (
      <p role="alert" className="m-7">
        {problem}
      </p>
    ) : (
      <p role="status" className="m-7">
        월간계획안을 불러오는 중…
      </p>
    );

  const { classId, annual, plans, centerId, template, current, pointer } = data;
  const play = annual?.format === "PLAY_PROJECT";
  const inherit = inheritOf(annual, month);
  const open = (m: number) => {
    const found = plans[m];
    if (!found) return;
    if (play) router.push(`/plans/monthly/play/${found.id}`);
    else onOpen({ id: found.id, classId, month: m });
  };
  const blocked: ReactNode = !annual ? (
    <>
      연간계획안을 먼저 만들어 확정해 주세요. <Link href="/plans">계획안으로 가기</Link>
    </>
  ) : annual.status !== "CONFIRMED" ? (
    <>
      연간계획안을 확정해야 월간을 만들 수 있어요.{" "}
      <Link href={`/plans/annual/${annual.id}`}>연간계획안 열기</Link>
    </>
  ) : !play && !template && !plans[month] ? (
    "쓸 수 있는 월간 양식이 아직 없어요. 양식은 승인을 받아야 쓸 수 있어요."
  ) : null;

  async function create() {
    if (busy || month === null) return;
    if (plans[month]) return open(month);
    controller.current?.abort();
    const ctl = new AbortController();
    controller.current = ctl;
    setBusy(true);
    setDone(false);
    setProblem("");
    setMemoProblem(null);
    const note = memo.trim() ? { memo: memo.trim() } : {};
    try {
      if (play) {
        const keys = inherit?.kind === "play" ? inherit.plays.map((p) => p.row_key) : [];
        const plan = await createPlayMonthly(
          {
            class_id: classId,
            month,
            emphasized_row_keys: focus.filter((k) => keys.includes(k)),
            ...note,
          },
          ctl.signal,
        );
        if (ctl.signal.aborted) return;
        setDone(true);
        await ringFinished();
        router.push(`/plans/monthly/play/${plan.id}`);
      } else if (template && centerId !== null) {
        let ref = sameColumns(current, template, extras) ? current!.profile_ref : null;
        if (!ref) {
          // 양식 시작은 멱등이 아니다 — 만든 양식을 바로 「지금 양식」으로 둬서 다시 눌러도 또 만들지 않는다.
          const made = await createTemplateProfile(
            centerId,
            profileInput(template, extras),
            ctl.signal,
          );
          ref = made.profile_ref;
          setData((d) => d && { ...d, current: made, pointer: made.profile_ref });
          // 다음 달도 이 칸으로 시작하게 원 기본으로 건다. 못 걸어도 이번 달은 이 양식으로 만든다.
          await putCenterDefaultProfile(centerId, {
            profile_ref: ref,
            expected_profile_ref: pointer,
          }).catch(() => null);
        }
        const plan = await createMonthlyPlan(
          { class_id: classId, month, profile_ref: ref, ...note },
          ctl.signal,
        );
        if (ctl.signal.aborted) return;
        setDone(true);
        await ringFinished();
        onOpen({ id: plan.id, classId, month });
      }
    } catch (e) {
      // 취소했거나 새 요청이 시작됐으면 이 요청은 화면을 바꾸지 않는다(새 요청의 busy 도 풀지 않는다).
      const stale = () => ctl.signal.aborted || controller.current !== ctl;
      if (stale()) return;
      // 그 달이 이미 있으면(409) 목록을 다시 읽어 그 초안으로 간다 — 읽는 동안 화면은 잠근 채로 둔다.
      if (e instanceof ApiError && e.status === 409) {
        const found = await existingAfterConflict(
          () => (play ? listPlayMonthly(classId) : listMonthlyPlans(classId)),
          (p) => p.month === month,
          stale,
        );
        if (stale()) return;
        if (found !== null) {
          if (play) router.push(`/plans/monthly/play/${found}`);
          else onOpen({ id: found, classId, month });
          return;
        }
      }
      setBusy(false);
      const memoMessage = memoError(e);
      if (memoMessage) setMemoProblem(memoMessage);
      // 서버가 보낸 안내(ApiError)만 그대로 — 연결 끊김 같은 브라우저 오류 원문(영어)은 보이지 않는다.
      else
        setProblem(
          e instanceof ApiError
            ? e.message
            : "월간계획안을 만들지 못했어요. 잠시 뒤 다시 해 주세요.",
        );
    }
  }

  if (busy)
    return (
      <div className="flex min-h-[calc(100vh-60px)]">
        <GenerationRing
          kind={play ? "monthly:PLAY_PROJECT" : "monthly:MONTHLY_THEME"}
          // Sol 실측: 주제형 28초(2026-10-31) · 38초, 놀이 중심형 40 · 33 · 43초(2026-11-05).
          expect={play ? 40 : 35}
          title={`${month}월 월간계획안을 만들고 있어요`}
          done={done}
          steps={
            play
              ? LOOK.play.steps(month, inherit?.kind === "play" ? inherit.season : "")
              : LOOK.theme.steps(month)
          }
          onCancel={() => {
            controller.current?.abort();
            setBusy(false);
          }}
        />
      </div>
    );

  return (
    <MonthlyNewView
      play={play}
      back={
        annual
          ? { href: `/plans/annual/${annual.id}`, label: `${annual.school_year} 연간계획안` }
          : { href: "/plans", label: "계획안" }
      }
      month={month}
      plans={plans}
      inherit={inherit}
      focus={focus}
      template={template}
      extras={extras}
      onExtras={setExtras}
      blocked={blocked}
      problem={problem}
      memo={memo}
      memoProblem={memoProblem}
      onMemo={setMemo}
      onMonth={(m) => (plans[m] ? open(m) : setMonth(m))}
      onFocus={setFocus}
      onCreate={() => void create()}
    />
  );
}
