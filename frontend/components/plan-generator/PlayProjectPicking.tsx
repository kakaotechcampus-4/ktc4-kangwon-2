"use client";

import { useEffect, useRef } from "react";
import type { PlayProjectAnnualPlan } from "@/lib/api/types";
import workspace from "@/components/workspace/Workspace.module.css";
import styles from "./PlayProjectResult.module.css";
import { fields } from "./playProjectPagination";

type Period = PlayProjectAnnualPlan["periods"][number];
type Candidate = Period["candidates"][number];

type Props = {
  periods: Period[];
  period: Period;
  picks: Record<string, string[]>;
  max: number;
  detailKey: string | null;
  idPrefix: string;
  onToggle: (rowKey: string) => void;
  onRemove: (rowKey: string, slot: number) => void;
  onDetail: (rowKey: string | null) => void;
  onArrange: () => void;
};

function PickToggle({
  picked,
  disabled,
  name,
  onClick,
}: {
  picked: boolean;
  disabled: boolean;
  name: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={styles.toggle}
      aria-pressed={picked}
      aria-label={`「${name}」 ${picked ? "선택됨" : "선택하기"}`}
      disabled={disabled}
      onClick={onClick}
    >
      {picked ? "✓ 선택됨" : "+ 선택하기"}
    </button>
  );
}

// 네이티브 대화 상자: 포커스 가두기 · Esc · 닫을 때 포커스 복귀를 브라우저가 한다.
function DetailDialog({
  candidate,
  picked,
  full,
  onToggle,
  onClose,
}: {
  candidate: Candidate;
  picked: boolean;
  full: boolean;
  onToggle: () => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);
  const titleId = "play-project-detail-title";
  // 닫기는 브라우저에 맡긴다. close 이벤트(onClose)가 상태를 풀고, 포커스를 연 버튼으로 돌려준다.
  const close = () => ref.current?.close();
  return (
    <dialog
      ref={ref}
      className={styles.dialog}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <div className={styles.dialogBody}>
        <h2 id={titleId}>{candidate.play_name.value}</h2>
        <dl className={styles.fields}>
          {fields.slice(1).map((field) => (
            <div key={field.key}>
              <dt>{field.heading}</dt>
              <dd>{candidate[field.key].value}</dd>
            </div>
          ))}
        </dl>
        <div className={styles.dialogActions}>
          <button type="button" className={workspace.secondary} onClick={close}>
            닫기
          </button>
          <PickToggle
            picked={picked}
            disabled={!picked && full}
            name={candidate.play_name.value}
            onClick={onToggle}
          />
        </div>
      </div>
    </dialog>
  );
}

function CandidateCard({
  candidate,
  index,
  picked,
  full,
  onToggle,
  onDetail,
}: {
  candidate: Candidate;
  index: number;
  picked: boolean;
  full: boolean;
  onToggle: () => void;
  onDetail: () => void;
}) {
  const name = candidate.play_name.value;
  return (
    <article
      className={`${workspace.card} ${styles.candidateCard} ${picked ? styles.candidatePicked : ""}`}
    >
      <p className={workspace.eyebrow}>후보 {index + 1}</p>
      <h2 className={styles.candidateName}>{name}</h2>
      <p className={styles.summary}>{candidate.support_direction.value}</p>
      <p className={styles.materialLine}>
        <span>지원매체</span> {candidate.materials.value}
      </p>
      <div className={styles.cardActions}>
        <button
          type="button"
          className={styles.detailButton}
          aria-label={`${name} 자세히 살펴보기`}
          onClick={onDetail}
        >
          자세히 살펴보기
        </button>
        <PickToggle picked={picked} disabled={!picked && full} name={name} onClick={onToggle} />
      </div>
    </article>
  );
}

function PickedSlot({
  slot,
  name,
  removeId,
  onRemove,
}: {
  slot: number;
  name: string | undefined;
  removeId: string;
  onRemove: () => void;
}) {
  const number = <span className={styles.slotNo}>{slot + 1}</span>;
  if (!name)
    return (
      <li className={styles.slot}>
        {number}
        <span className={styles.slotEmpty}>우리 반의 놀이를 골라 주세요</span>
      </li>
    );
  return (
    <li className={styles.slot}>
      {number}
      <span className={styles.slotName}>{name}</span>
      <button
        type="button"
        id={removeId}
        className={styles.slotRemove}
        aria-label={`${name} 빼기`}
        onClick={onRemove}
      >
        ×
      </button>
    </li>
  );
}

export default function PlayProjectPicking({
  periods,
  period,
  picks,
  max,
  detailKey,
  idPrefix,
  onToggle,
  onRemove,
  onDetail,
  onArrange,
}: Props) {
  const periodPicks = picks[period.period_key] ?? [];
  const full = periodPicks.length >= max;
  const detail = period.candidates.find((candidate) => candidate.row_key === detailKey);
  return (
    <div className={styles.pickLayout}>
      <div className={styles.candidateGrid}>
        {period.candidates.map((candidate, index) => (
          <CandidateCard
            key={candidate.row_key}
            candidate={candidate}
            index={index}
            picked={periodPicks.includes(candidate.row_key)}
            full={full}
            onToggle={() => onToggle(candidate.row_key)}
            onDetail={() => onDetail(candidate.row_key)}
          />
        ))}
      </div>
      <aside className={`${workspace.card} ${styles.pickedPanel}`} aria-label="고른 놀이">
        <h2 id={`${idPrefix}-heading`} tabIndex={-1}>
          고른 놀이 {periodPicks.length}/{max}
        </h2>
        <p className={styles.hint}>{period.label}</p>
        <ol className={styles.slots}>
          {Array.from({ length: max }, (_, slot) => (
            <PickedSlot
              key={slot}
              slot={slot}
              name={period.candidates.find((c) => c.row_key === periodPicks[slot])?.play_name.value}
              removeId={`${idPrefix}-remove-${slot}`}
              onRemove={() => onRemove(periodPicks[slot], slot)}
            />
          ))}
        </ol>
        {full && (
          <p role="status" className={`${workspace.muted} ${styles.limitMessage}`}>
            5개를 모두 골랐어요. 바꾸려면 하나를 빼 주세요.
          </p>
        )}
        <ul className={styles.periodProgress} aria-label="구간별 진행">
          {periods.map((item) => (
            <li key={item.period_key}>
              <span>{item.label}</span>
              <span>
                {picks[item.period_key]?.length ?? 0}/{max}
              </span>
            </li>
          ))}
        </ul>
        <button
          type="button"
          className={`${workspace.primary} ${styles.arrange}`}
          onClick={onArrange}
        >
          배치하고 다듬기로
        </button>
      </aside>
      {detail && (
        <DetailDialog
          candidate={detail}
          picked={periodPicks.includes(detail.row_key)}
          full={full}
          onToggle={() => onToggle(detail.row_key)}
          onClose={() => onDetail(null)}
        />
      )}
    </div>
  );
}
