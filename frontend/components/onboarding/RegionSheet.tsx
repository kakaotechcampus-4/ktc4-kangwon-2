"use client";

import { useEffect, useRef, useState } from "react";
import { PROVINCE_OPTIONS, districtsFor, matchesRegion } from "@/lib/onboarding/regions";
import { ChalkLine } from "./FlowParts";

const SEJONG = "세종특별자치시";

/**
 * 칸 하나 = 칠판에 적은 이름. 손글씨체는 읽기 어렵다는 시험 의견이 있어 기본 글씨체로 쓰고, 분필 결만 입힌다.
 * 마우스를 올리면(키보드로 가도) 이름을 분필로 쓱 친 네모로 두른다(ChalkBox).
 * 네모는 글자 양옆으로 조금 더 나가되(-mx · px), 글자 자리는 다른 칸과 그대로 맞는다.
 */
const item =
  "group relative -mx-2.5 inline-flex min-h-12 items-center px-2.5 text-left text-[18px] font-bold leading-tight text-ink focus-visible:outline-none";

/** 손으로 친 네모 — 칸마다 조금씩 다르게 비뚤고, 한 획으로 그어 시작한 귀퉁이에서 살짝 삐져나온다. */
const CHALK_BOXES = [
  "M3 6 L97.5 3.5 L97 36.5 L2.5 37 L3.5 1.5",
  "M2.5 4 L98 5.5 L97.5 37.5 L3 35.5 L2 8 L6 3.8",
  "M4 3 L96.5 4.5 L98 35 L3 37.5 L2.5 4.5",
];

/**
 * 분필로 친 네모. 칸 크기에 맞춰 늘어나도(preserveAspectRatio none) 선 굵기는 그대로이고
 * (non-scaling-stroke), 분필 가루처럼 끊기고 번진 결은 OnboardingLayout 의 #chalk 필터가 낸다.
 * 늘 그려 두고 투명하게 있다가, 칸에 마우스를 올리거나 키보드로 가면 보인다.
 */
function ChalkBox({ index }: { index: number }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 100 40"
      preserveAspectRatio="none"
      className="pointer-events-none absolute inset-0 h-full w-full overflow-visible opacity-0 transition-opacity duration-150 group-hover:opacity-85 group-focus-visible:opacity-100 motion-reduce:transition-none"
    >
      <path
        d={CHALK_BOXES[index % CHALK_BOXES.length]}
        fill="none"
        stroke="currentColor"
        strokeWidth={2.2}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
        filter="url(#chalk)"
      />
    </svg>
  );
}
const iconButton =
  "inline-flex h-10 w-10 items-center justify-center squircle [--r:12px] text-ink-soft hover:bg-primary-tint focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary";

/**
 * 지역 고르개 — 칠판 위에 뜨는 작은 칠판, 이름은 분필로 적은 글씨. 휴대폰에서는 아래에서 올라오는 판,
 * 데스크톱에서는 나무테를 두른 가운데 판이다.
 * 시·도를 고르면 같은 자리의 목록이 그 시·도의 시·군·구로 바뀐다. 세종은 시·군·구가 없어 바로 끝난다.
 * 판 크기는 늘 같다(걸러서 이름이 줄어도 안 변한다). 열리면 검색칸에 커서가 있어 바로 이름이나
 * 초성(예: ㅊㅊ)을 치면 목록이 걸러진다. 한 개만 남으면 Enter 로 고른다.
 * 네이티브 `<dialog>` 라서 포커스를 가두고 Esc 로 닫히며, 닫으면 눌렀던 단추로 포커스가 돌아간다.
 */
export default function RegionSheet({
  onPick,
  onClose,
}: {
  onPick: (province: string, district: string) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const [province, setProvince] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
    // 열리자마자 바로 초성을 칠 수 있게 검색칸에 커서를 둔다(showModal 은 첫 단추에 포커스를 준다).
    search.current?.focus();
  }, []);

  // 목록이 바뀌면 검색어는 비운다.
  function openProvince(value: string) {
    setProvince(value);
    setQuery("");
    // 눌렀던 이름 단추는 목록과 함께 사라지므로 포커스를 검색칸으로 되돌린다.
    search.current?.focus();
  }
  function pickProvince(value: string) {
    if (value === SEJONG) onPick(value, SEJONG);
    else openProvince(value);
  }

  const entries = province
    ? districtsFor(province).map((d) => ({ key: d, label: d, pick: () => onPick(province, d) }))
    : PROVINCE_OPTIONS.map((p) => ({
        key: p.value,
        label: p.label,
        pick: () => pickProvince(p.value),
      }));
  const shown = entries.filter((e) => matchesRegion(e.label, query));
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      aria-labelledby="region-sheet-title"
      className="chalkboard m-0 mt-auto h-[min(640px,85vh)] w-full max-w-none squircle [--r-bl:0px] [--r-br:0px] [--r:24px] p-0 pb-7 text-ink open:flex open:flex-col backdrop:bg-[rgba(46,42,38,0.55)] sm:m-auto sm:max-w-[560px] sm:[--r:0px]"
    >
      <div
        aria-hidden="true"
        className="mx-auto mt-3 h-1 w-10 flex-none rounded-sm bg-line sm:hidden"
      />
      <div className="flex flex-none items-center gap-2 px-6 pb-4 pt-3 sm:pt-5">
        {province && (
          <button
            type="button"
            onClick={() => openProvince("")}
            aria-label="시·도 다시 고르기"
            className={`${iconButton} -ml-2.5 text-ink`}
          >
            <svg
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M15 5l-7 7 7 7" />
            </svg>
          </button>
        )}
        <h2
          id="region-sheet-title"
          className="flex-1 font-display text-[28px] font-bold leading-tight text-ink sm:text-[34px]"
        >
          {province ? "시·군·구를 골라주세요" : "시·도를 골라주세요"}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="닫기"
          className={`${iconButton} -mr-2.5`}
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            aria-hidden="true"
          >
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>
      {/* 고른 시·도는 눈에 안 보이게 두고 화면 읽기 프로그램에만 알린다. */}
      {province && <p className="sr-only">{province}</p>}
      {/* 제목과 아래 이름 목록을 가르는 분필 점선 */}
      <div
        aria-hidden="true"
        className="mx-6 mb-3 flex-none border-t-2 border-dashed border-line"
      />
      <div className="group relative mx-6 mb-3 flex-none">
        <input
          ref={search}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && shown.length === 1) shown[0].pick();
          }}
          aria-label={province ? "시·군·구 찾기" : "시·도 찾기"}
          placeholder="이름이나 초성으로 찾기 (예: ㅅㅇ)"
          autoComplete="off"
          spellCheck={false}
          enterKeyHint="search"
          className="w-full bg-transparent px-1 pb-2 pt-1 text-[17px] text-ink placeholder:text-ink-soft focus:outline-none"
        />
        <ChalkLine className="text-line group-focus-within:text-primary" />
      </div>
      {/* 판 크기는 고정이다 — 걸러서 이름이 줄어도 판이 오르내리지 않고, 넘치면 이 안에서만 스크롤된다. */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <ul
          className={`grid gap-x-4 gap-y-1 px-6 pb-2 pt-1 ${province ? "grid-cols-3 sm:grid-cols-4" : "grid-cols-2 sm:grid-cols-3"}`}
          style={{ wordBreak: "keep-all" }}
        >
          {shown.map((e, i) => (
            <li key={e.key}>
              <button type="button" className={item} onClick={e.pick}>
                {/* 이름은 분필로 쓴 듯한 결을 입힌다(#chalk-text). 네모(ChalkBox)는 따로 결을 받는다. */}
                <span className="[filter:url(#chalk-text)]">{e.label}</span>
                <ChalkBox index={i} />
              </button>
            </li>
          ))}
        </ul>
        {shown.length === 0 && (
          <p role="status" className="px-6 pb-2 text-[15px] text-ink-soft">
            찾는 이름이 없어요. 다른 글자로 찾아보세요.
          </p>
        )}
      </div>
    </dialog>
  );
}
