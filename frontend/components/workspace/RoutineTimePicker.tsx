"use client";
import { useState } from "react";
import { routineTimeFrom12, routineTimeParts12 } from "@/lib/api/routines";
import { ws } from "./WorkspaceUI";

const HOURS = Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, "0"));
const MINUTES = Array.from({ length: 12 }, (_, i) => String(i * 5).padStart(2, "0"));

export default function RoutineTimePicker({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const [draft, setDraft] = useState(() => ({ source: value, ...routineTimeParts12(value) }));
  const parts = draft.source === value ? draft : routineTimeParts12(value);
  function pick(next: ReturnType<typeof routineTimeParts12>) {
    const time = routineTimeFrom12(next.hour, next.minute, next.period);
    setDraft({ source: time, ...next });
    onChange(time);
  }
  return (
    <div className={ws.field} role="group" aria-label={label}>
      <span>{label}</span>
      <div className={ws.timePicker}>
        <select
          aria-label={`${label} 시`}
          disabled={disabled}
          value={parts.hour}
          onChange={(e) => pick({ ...parts, hour: e.target.value })}
        >
          <option value="">—</option>
          {HOURS.map((hour) => (
            <option key={hour} value={hour}>
              {hour}
            </option>
          ))}
        </select>
        <span aria-hidden="true">:</span>
        <select
          aria-label={`${label} 분`}
          disabled={disabled}
          value={parts.minute}
          onChange={(e) => pick({ ...parts, minute: e.target.value })}
        >
          {!MINUTES.includes(parts.minute) && (
            <option value={parts.minute}>{parts.minute} (기존)</option>
          )}
          {MINUTES.map((minute) => (
            <option key={minute} value={minute}>
              {minute}
            </option>
          ))}
        </select>
        <button
          type="button"
          className={ws.secondary}
          aria-label={`${label} AM/PM`}
          aria-pressed={parts.period === "PM"}
          disabled={disabled}
          onClick={() => pick({ ...parts, period: parts.period === "AM" ? "PM" : "AM" })}
        >
          {parts.period}
        </button>
        <button
          type="button"
          className={ws.secondary}
          aria-label={`${label} 시간 지우기`}
          disabled={disabled || !value}
          onClick={() => pick(routineTimeParts12(""))}
        >
          ×
        </button>
      </div>
    </div>
  );
}
