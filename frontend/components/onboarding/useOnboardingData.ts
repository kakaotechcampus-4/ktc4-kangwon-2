"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useHydrated } from "@/lib/hooks/use-client-state";
import { loadClassSettings, saveClassSettings } from "@/lib/onboarding/settings";
import { onboardingDestination } from "@/lib/auth/local-account";
import { startupRedirect, type OnboardingRoute } from "@/lib/onboarding/flow";
import { EMPTY_CLASS_SETTINGS, type ClassSettings } from "@/lib/onboarding/types";
import { normalizeProvince } from "@/lib/onboarding/regions";
import {
  syncClasses,
  migrateChildren,
  loadServerClasses,
  loadServerChildren,
  hasConsent,
} from "@/lib/api/onboarding";

/** 저장된 설정과 돌려보낼 곳을 마운트 시 한 번만 읽는다(브라우저 전용, 서버에서는 빈 값). */
function readStartup(route: OnboardingRoute) {
  const saved = loadClassSettings();
  const redirectTo = startupRedirect(route, onboardingDestination());
  return {
    saved,
    redirectTo,
    settings: saved
      ? {
          ...saved,
          regionProvince: normalizeProvince(saved.regionProvince),
          regionDistrict: saved.regionDistrict.trim(),
        }
      : EMPTY_CLASS_SETTINGS,
  };
}

/**
 * 온보딩 화면 넷이 같이 쓰는 시작 절차: 저장된 설정 읽기 → 돌려보내기 → 서버 목록 불러오기.
 * 반 목록은 반 화면에서, 아이 명단은 아이 · 마지막 확인 화면에서 서버 값으로 새로 읽는다.
 */
export function useOnboardingData(route: OnboardingRoute) {
  const router = useRouter();
  const params = useSearchParams();
  const hydrated = useHydrated();
  const [startup] = useState(() => readStartup(route));
  const [settings, setSettings] = useState<ClassSettings>(startup.settings);
  const [error, setError] = useState("");
  const [listLoaded, setListLoaded] = useState(false);
  const loadsList = !startup.redirectTo && !!startup.saved && route !== "center";
  const ready = hydrated && !startup.redirectTo && (!loadsList || listLoaded);

  useEffect(() => {
    const saved = startup.saved;
    if (startup.redirectTo) {
      router.replace(startup.redirectTo);
      return;
    }
    if (!saved || route === "center") return;
    let live = true;
    const load = async () => {
      try {
        if (route === "classes") {
          const next = await loadServerClasses(saved);
          if (live) setSettings(next);
        } else {
          // 브라우저에 있던 명단은 동의가 확인된 반만 서버로 옮긴다.
          await syncClasses(saved);
          const classes = [];
          for (const c of saved.classes) {
            if (c.guardianConsent) await migrateChildren(c);
            const loaded = await loadServerChildren(c);
            classes.push({
              ...loaded,
              guardianConsent: loaded.guardianConsent || hasConsent(c.id),
            });
          }
          if (live) setSettings({ ...saved, classes });
        }
      } catch (e) {
        if (live) setError(e instanceof Error ? e.message : "목록을 불러오지 못했어요.");
      } finally {
        if (live) setListLoaded(true);
      }
    };
    void load();
    return () => {
      live = false;
    };
  }, [route, router, startup]);

  /** 화면에만 반영한다. 입력 중인 값을 저장소에 쓰지 않는다. */
  const edit = (p: Partial<ClassSettings>) => setSettings((s) => ({ ...s, ...p }));
  /** 화면과 브라우저 저장소에 같이 쓴다. 저장소에 못 썼으면 `false`. */
  const commit = (next: ClassSettings) => {
    setSettings(next);
    return saveClassSettings(next);
  };

  return {
    ready,
    settings,
    edit,
    commit,
    error,
    setError,
    params,
  };
}
