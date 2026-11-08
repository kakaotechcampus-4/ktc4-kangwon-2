"use client";

import type { PlayProjectAnnualPlan } from "@/lib/api/types";
import PlayPickBoard from "@/components/plan-ui/PlayPickBoard";
import { playSeason } from "./playProjectPagination";
import SeasonIcon from "./SeasonIcon";

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
  /** 다음 계절 탭으로 옮긴다. */
  onPeriod: (index: number) => void;
};

/**
 * ④ 놀이 고르기. 서버 계획안의 지금 구간을 PlayPickBoard 모양으로 바꿔 넘긴다.
 * 고르기 · 빼기 · 저장은 부모(PlayProjectResult)의 `togglePlayPick` 흐름이 그대로 한다.
 * 구간 탭과 진행 수는 부모가 그린다.
 */
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
  onPeriod,
}: Props) {
  // 정답지 ④: 다음 계절로 가기가 기본, 마지막 계절이면 문서 만들기. 중간에 끝내기는 아래 작은 버튼.
  const index = periods.findIndex((p) => p.period_key === period.period_key);
  const next = index >= 0 && index < periods.length - 1 ? index + 1 : null;
  const candidates = period.candidates.map((c) => ({
    key: c.row_key,
    name: c.play_name.value,
    fields: [
      { label: "내용 및 지원 방향", lines: [c.support_direction.value] },
      {
        label: "놀이를 통한 배움",
        lines: c.learning.value.split("\n").filter((line) => line.trim()),
      },
    ],
    memoApplied: c.memo_applied,
  }));
  return (
    <PlayPickBoard
      subject={`${playSeason(period).name} 놀이`}
      icon={<SeasonIcon periodKey={period.period_key} />}
      max={max}
      candidates={candidates}
      picked={picks[period.period_key] ?? []}
      focus={detailKey}
      idPrefix={idPrefix}
      onFocus={onDetail}
      onToggle={onToggle}
      onRemove={onRemove}
      onNext={next === null ? onArrange : () => onPeriod(next)}
      nextLabel={next === null ? "문서 만들기" : `${playSeason(periods[next]).name} 고르러 가기`}
      onFinishEarly={next === null ? undefined : onArrange}
    />
  );
}
