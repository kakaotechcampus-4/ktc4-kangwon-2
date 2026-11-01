"use client";

import type { PlayProjectAnnualPlan } from "@/lib/api/types";
import PlayPickBoard from "@/components/plan-ui/PlayPickBoard";

type Period = PlayProjectAnnualPlan["periods"][number];

type Props = {
  periods: Period[];
  period: Period;
  picks: Record<string, string[]>;
  max: number;
  /** 가운데 「자세히 보기」에 띄운 후보. null 이면 첫 후보. */
  detailKey: string | null;
  idPrefix: string;
  onToggle: (rowKey: string) => void;
  onRemove: (rowKey: string, slot: number) => void;
  onDetail: (rowKey: string | null) => void;
  onArrange: () => void;
};

/**
 * ④ 놀이 고르기. 서버 계획안의 지금 구간을 PlayPickBoard 모양으로 바꿔 넘긴다.
 * 고르기 · 빼기 · 저장은 부모(PlayProjectResult)의 `togglePlayPick` 흐름이 그대로 한다.
 * 구간 탭과 진행 수는 부모가 그린다.
 */
export default function PlayProjectPicking({
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
  const candidates = period.candidates.map((c) => ({
    key: c.row_key,
    name: c.play_name.value,
    materials: c.materials.value,
    support: c.support_direction.value,
    learning: c.learning.value.split("\n").filter((line) => line.trim()),
  }));
  return (
    <PlayPickBoard
      season={period.label}
      max={max}
      candidates={candidates}
      picked={picks[period.period_key] ?? []}
      focus={detailKey}
      idPrefix={idPrefix}
      onFocus={onDetail}
      onToggle={onToggle}
      onRemove={onRemove}
      onNext={onArrange}
      nextLabel="배치하고 다듬기로"
    />
  );
}
