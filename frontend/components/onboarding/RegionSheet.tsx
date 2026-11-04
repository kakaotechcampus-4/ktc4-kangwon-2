"use client";

import { useEffect, useRef, useState } from "react";
import { PROVINCE_OPTIONS, districtsFor } from "@/lib/onboarding/regions";

const SEJONG = "세종특별자치시";

const item =
  "flex min-h-12 w-full items-center justify-center squircle [--r:12px] border-[1.5px] border-line bg-paper px-2.5 py-2 text-center text-[15px] font-medium text-ink transition-colors hover:border-primary hover:bg-primary-tint focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary";
const iconButton =
  "inline-flex h-10 w-10 items-center justify-center squircle [--r:12px] text-ink-soft hover:bg-primary-tint focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary";

/**
 * 지역 고르개. 휴대폰에서는 아래에서 올라오는 시트, 데스크톱에서는 가운데 대화 상자다.
 * 시·도를 고르면 같은 자리의 목록이 그 시·도의 시·군·구로 바뀐다. 세종은 시·군·구가 없어 바로 끝난다.
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
  const [province, setProvince] = useState("");

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  function pickProvince(value: string) {
    if (value === SEJONG) onPick(value, SEJONG);
    else setProvince(value);
  }

  const districts = districtsFor(province);
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      aria-labelledby="region-sheet-title"
      className="m-0 mt-auto max-h-[80vh] w-full max-w-none squircle [--r-bl:0px] [--r-br:0px] [--r:24px] border-0 bg-paper p-0 pb-6 shadow-[0_-8px_32px_rgba(46,42,38,0.14)] backdrop:bg-[rgba(46,42,38,0.45)] sm:m-auto sm:max-w-[520px] sm:[--r-bl:20px] sm:[--r-br:20px] sm:[--r:20px]"
    >
      <div aria-hidden="true" className="mx-auto mt-3 h-1 w-10 rounded-sm bg-line sm:hidden" />
      <div className="flex items-center gap-2 px-6 pb-4 pt-3 sm:pt-5">
        {province && (
          <button
            type="button"
            onClick={() => setProvince("")}
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
        <h2 id="region-sheet-title" className="flex-1 text-[20px] font-bold text-ink">
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
      {province && <p className="-mt-2 mb-3.5 px-6 text-[14px] text-ink-soft">{province}</p>}
      <ul
        className={`grid max-h-[60vh] gap-2 overflow-y-auto px-6 ${province ? "grid-cols-3 sm:grid-cols-4" : "grid-cols-2 sm:grid-cols-3"}`}
        style={{ wordBreak: "keep-all" }}
      >
        {!province &&
          PROVINCE_OPTIONS.map((p) => (
            <li key={p.value}>
              <button type="button" className={item} onClick={() => pickProvince(p.value)}>
                {p.label}
              </button>
            </li>
          ))}
        {province &&
          districts.map((d) => (
            <li key={d}>
              <button type="button" className={item} onClick={() => onPick(province, d)}>
                {d}
              </button>
            </li>
          ))}
      </ul>
    </dialog>
  );
}
