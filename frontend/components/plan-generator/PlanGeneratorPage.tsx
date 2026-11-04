"use client";

/** 연간계획안 만들기 — 방식은 첫 화면(/plans)에서 골라 쿼리로 온다. 반 정보는 지금 고른 반에서 읽는다. */

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  createAnnualPlan,
  deleteAnnualPlan,
  listAnnualPlans,
  testResetAnnualPlan,
  TEST_RESET_ENABLED,
} from "@/lib/api/plans";
import { syncClass } from "@/lib/api/onboarding";
import { ApiError } from "@/lib/api/client";
import type { AnnualInput } from "@/lib/api/types";
import { classAnnualContext, saveAnnualContext } from "@/lib/plan-generator/context";
import { loadClassSettings, primaryClassFor } from "@/lib/onboarding/settings";
import { ageSelectionLabel, selectedAgesFor } from "@/lib/onboarding/types";
import { useClientState } from "@/lib/hooks/use-client-state";
import { schoolYearOf } from "@/lib/workspace/document-archive";
import { today } from "@/lib/workspace/model";
import { Tape } from "@/components/workspace/WorkspaceUI";
import { SlideTour } from "@/components/app/Tour";
import GenerationRing from "@/components/plan-ui/GenerationRing";
import { useCompactShell } from "@/components/app/compact-shell";
import { memoError, PlanMemoField } from "./PlanMemo";
import { BACK_BUTTON, BACK_ICON } from "./AnnualFrame";

type Format = AnnualInput["format"];

// 기관 양식 선택은 버렸다(디자인 결정) — 기본 양식만 잠근 채 보여 준다.
/** 양식 칸 화살표 — 온보딩 Select 의 chevron 과 같은 그림. */
const CHEVRON =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath d='M5 9l7 7 7-7' fill='none' stroke='%236B7280' stroke-width='2.3' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\")";

const FORMAT = {
  MONTHLY_THEME: {
    name: "월별 주제형",
    form: "소주제형 기본 양식",
    image: "monthly-theme-crop",
    alt: "쌤플 기본 연간계획안 양식 예시",
    chip: "bg-[#e8f1ea] text-[#3b5441]",
    steps: ["주제 정하기", "소주제 나누기", "문서로 정리하기"],
  },
  PLAY_PROJECT: {
    name: "놀이 중심형",
    form: "놀이 중심형 기본 양식",
    image: "play-project-crop",
    alt: "놀이 중심형 연간계획안 양식 예시",
    chip: "bg-[#eee4f4] text-[#5e4b96]",
    steps: ["놀이 떠올리기", "계절별로 나누기", "문서로 정리하기"],
  },
} as const;

const NO_ROOM = { className: "", age: "" };

export default function PlanGeneratorPage({ format }: { format: Format | null }) {
  if (!format) return <NoFormat />;
  return <AnnualGenerator format={format} />;
}

/** 방식 없이 들어온 옛 주소(/plans/create · 트렌드 링크). 방식은 첫 화면에서만 고른다. */
function NoFormat() {
  return (
    <div className="flex w-full flex-col gap-3 px-10 pb-12 pt-[26px] text-[#2b2826]">
      <h1 className="m-0 font-display text-[34px] font-bold leading-[1.2] text-ink">
        연간계획안 만들기
      </h1>
      <p className="m-0 text-base text-[#5c5243]">어떤 방식으로 만들지 먼저 골라 주세요.</p>
      <Link href="/plans" className="text-base font-bold text-[#5e4b96]">
        방식 고르러 가기 →
      </Link>
    </div>
  );
}

function AnnualGenerator({ format }: { format: Format }) {
  const router = useRouter();
  const look = FORMAT[format];
  const [room] = useClientState(() => {
    const klass = primaryClassFor(loadClassSettings());
    return klass
      ? { className: klass.className, age: ageSelectionLabel(selectedAgesFor(klass)) }
      : NO_ROOM;
  }, NO_ROOM);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [memo, setMemo] = useState("");
  const [memoProblem, setMemoProblem] = useState<string | null>(null);
  // 그 반에 연간이 이미 있을 때(409) 어느 반인지. 교사가 「새로 만들기」를 고를 때만 지운다 —
  // 확정 전이라도 교사가 쓴 글이 사라지는 일이라 조용히 지우지 않는다.
  const [occupied, setOccupied] = useState<number | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const year = schoolYearOf(today());
  useCompactShell(generating);

  useEffect(() => () => controllerRef.current?.abort(), []);

  async function generate() {
    if (generating) return;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setGenerating(true);
    setError("");
    setMemoProblem(null);
    setOccupied(null);
    let classId: number | null = null;
    try {
      const settings = loadClassSettings(),
        primary = primaryClassFor(settings);
      if (!settings || !primary) throw new Error("반 정보를 먼저 저장해주세요.");
      classId = await syncClass(settings, primary);
      // 놀이 중심형은 form_id 를 보내지 않는다. 월별 주제형은 null = 기본 양식 (§4).
      const plan = await createAnnualPlan(
        {
          class_id: classId,
          format,
          ...(format === "MONTHLY_THEME" ? { form_id: null } : {}),
          ...(memo.trim() ? { memo: memo.trim() } : {}),
        },
        controller.signal,
      );
      if (controller.signal.aborted) return;
      try {
        saveAnnualContext(plan.id, classAnnualContext(primary, plan.school_year));
      } catch (e) {
        console.warn("계획안 표시 정보 캐시 저장 실패", e);
      }
      router.replace("/plans/annual/" + plan.id);
    } catch (e) {
      if (controller.signal.aborted) return;
      // 만들기 경로의 409 는 「이 반의 연간계획안이 이미 있습니다」 하나뿐이다.
      if (e instanceof ApiError && e.status === 409 && classId !== null) setOccupied(classId);
      const memoMessage = memoError(e);
      if (memoMessage) setMemoProblem(memoMessage);
      else setError(e instanceof Error ? e.message : "계획안을 생성하지 못했어요.");
      setGenerating(false);
    }
  }

  /** [그만 만들기]. 화면만 멈춘다 — 이미 보낸 요청은 서버가 끝까지 처리할 수 있다. */
  function stop() {
    controllerRef.current?.abort();
    setGenerating(false);
  }

  /** 그 반의 연간계획안을 지우고 다시 만든다. 교사가 「새로 만들기」를 눌렀을 때만 온다. */
  async function replace(classId: number) {
    setOccupied(null);
    setError("");
    try {
      const { items } = await listAnnualPlans(classId);
      const existing = items[0];
      if (!existing) throw new Error("지울 계획안을 찾지 못했어요. 새로고침 후 다시 해주세요.");
      // 시험 모드면 확정본 · 딸린 월간 · 주간까지 지운다(서버 test-reset). 아니면 서버가 그것들을 막는다.
      await (TEST_RESET_ENABLED ? testResetAnnualPlan : deleteAnnualPlan)(existing.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "지우지 못했어요.");
      return;
    }
    await generate();
  }

  if (generating)
    return (
      <div className="flex min-h-[calc(100vh-60px)]">
        <GenerationRing steps={[...look.steps]} onCancel={stop} />
      </div>
    );

  return (
    <div className="flex w-full flex-col gap-4 px-10 pb-6 pt-[26px] text-[#2b2826] lg:h-[calc(100vh-60px)]">
      {error && (
        <p
          role="alert"
          className="m-0 rounded-md border border-[#e8e2d8] bg-white px-4 py-3 text-sm"
        >
          {error}
          {occupied !== null && (
            <>
              {" "}
              새로 만들면 지금 있는 초안이 사라져요.{" "}
              <button type="button" className="underline" onClick={() => replace(occupied)}>
                새로 만들기
              </button>{" "}
              ·{" "}
              <button type="button" className="underline" onClick={() => setOccupied(null)}>
                그대로 두기
              </button>
            </>
          )}
        </p>
      )}

      {/* 월간 · 주간 만들기와 같은 틀 — 왼쪽 고르기 1 : 오른쪽 양식 1.15, 화면 높이에 맞춤. */}
      <div className="relative grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <Tape />
        <section className="flex min-h-0 flex-col gap-6 overflow-y-auto border border-line bg-paper rounded-md p-7">
          {/* 왼쪽 판 맨 위: 제목 앞 「←」 돌아가기(편집 화면과 같은 버튼) · 방식. */}
          <div className="flex shrink-0 flex-col">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <Link
                href="/plans"
                aria-label="돌아가기: 방식 다시 고르기"
                title="방식 다시 고르기"
                className={BACK_BUTTON}
              >
                {BACK_ICON}
              </Link>
              <h1 className="m-0 font-display text-[34px] font-bold leading-[1.2] text-ink">
                {year} 연간계획안 만들기
              </h1>
              <span className={`rounded-full px-3 py-1 text-[13px] font-bold ${look.chip}`}>
                {look.name}
              </span>
              <span className="ml-auto">
                <SlideTour format={format} />
              </span>
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <h2 className="m-0 font-display text-[24px] font-bold leading-tight text-ink">
              우리 반
            </h2>
            <div className="grid grid-cols-3 gap-3">
              {[
                ["반", room.className || "반 없음"],
                ["연령", room.age || "—"],
                ["학년도", String(year)],
              ].map(([k, v]) => (
                <div key={k} className="flex flex-col gap-1 rounded-md bg-[#f7f4ee] px-4 py-3">
                  <span className="text-[13px] text-[#5c5243]">{k}</span>
                  <span className="text-lg font-bold">{v}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <label
              htmlFor="form"
              className="m-0 font-display text-[24px] font-bold leading-tight text-ink"
            >
              양식
            </label>
            <select
              id="form"
              disabled
              // 기본 화살표는 칸 끝에 붙는다 — 온보딩 Select 와 같은 chevron 을 안쪽(18px)에 둔다.
              className="min-h-[52px] appearance-none rounded-md border border-[#ddd6ca] bg-[#f7f4ee] bg-[length:15px] bg-[right_18px_center] bg-no-repeat pl-4 pr-12 text-base text-[#5c5243]"
              style={{ backgroundImage: CHEVRON }}
            >
              <option>{look.form}</option>
            </select>
          </div>

          <PlanMemoField
            value={memo}
            onChange={setMemo}
            error={memoProblem}
            chips={
              format === "PLAY_PROJECT"
                ? ["자연물 놀이 많이", "실외 활동 중심", "미술 활동 포함"]
                : ["자연물 놀이 많이", "실외 활동 중심", "미술 활동 포함", "명절·행사 반영"]
            }
            placeholder="예) 가을엔 자연물 놀이를 많이 넣어주세요"
          />

          <button
            type="button"
            onClick={() => void generate()}
            disabled={!room.className}
            className="mt-auto min-h-[56px] rounded-md bg-primary-tint-line hover:bg-primary text-[17px] font-bold text-ink hover:text-white disabled:cursor-not-allowed disabled:opacity-50 transition-transform active:translate-x-[2px] active:translate-y-[3px] active:shadow-none"
          >
            연간계획안 만들기
          </button>
        </section>

        <section
          aria-label="양식 미리보기"
          className="flex min-h-[420px] flex-col border border-shell-line bg-shell-hover shadow-[inset_0_1px_4px_rgba(52,49,47,0.08)] p-3"
        >
          <div className="relative min-h-0 flex-1">
            {/* 정답지 ②: 종이 모양(테두리 · 그림자)이 그림 크기에 딱 맞게. fill 은 빈 띠를 남긴다. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`/plan-formats/${look.image}.png`}
              alt={look.alt}
              className="absolute inset-x-0 top-0 mx-auto max-h-full max-w-full rounded-md border border-[#e3ddd2] bg-white object-contain object-top shadow-[0_8px_24px_-12px_rgba(43,40,38,0.25)]"
            />
          </div>
        </section>
      </div>
    </div>
  );
}
