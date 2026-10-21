"use client";

import { useEffect, useState } from "react";
import { getCurrentUser } from "@/lib/api/auth";
import { getCenterSettings } from "@/lib/api/centers";
import { AXES, DEFAULT_AXIS, type ObservationAxis } from "@/lib/workspace/observation-axis";

/**
 * 우리 원이 쓰는 영역 목록 (`lib/workspace/observation-axis.ts`).
 *
 * 불러오는 동안에도 **기본 축을 돌려준다** — 빈 배열을 주면 영역 고르는 칸이 잠깐 비고,
 * 그때 교사가 저장을 누르면 영역 없이 보내진다. 설정을 못 읽어도 같다(서버가 최종이다).
 */
export function useObservationDomains(): readonly string[] {
  const [axis, setAxis] = useState<ObservationAxis>(DEFAULT_AXIS);
  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const user = await getCurrentUser();
        if (user.center_id === null) return;
        const settings = await getCenterSettings(user.center_id);
        if (live && settings.observation_axis in AXES) setAxis(settings.observation_axis);
      } catch {
        // 설정을 못 읽으면 기본 축으로 둔다. 서버가 틀린 값을 받으면 422 로 알려준다.
      }
    })();
    return () => {
      live = false;
    };
  }, []);
  return AXES[axis];
}
