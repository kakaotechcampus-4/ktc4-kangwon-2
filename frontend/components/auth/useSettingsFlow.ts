"use client";

import { useEffect, useRef, useState } from "react";
import { useHydrated } from "@/lib/hooks/use-client-state";
import { loadClassSettings, saveClassSettings, shownPrimaryId } from "@/lib/onboarding/settings";
import { completeAccountOnboarding } from "@/lib/auth/local-account";
import { EMPTY_CLASS_SETTINGS, type ClassSettings } from "@/lib/onboarding/types";
import { normalizeProvince } from "@/lib/onboarding/regions";
import {
  syncCenter,
  syncClasses,
  rememberConsent,
  hasConsent,
  migrateChildren,
  loadServerClasses,
  loadServerChildren,
} from "@/lib/api/onboarding";

/*
 * 설정 쪽지(`SettingsNoteEditors`)의 불러오기 · 저장.
 * 옛 첫 설정 화면(`OnboardingPage.tsx`)의 `useOnboardingFlow` 를 쪽지가 쓰던 부분만 옮겼다.
 * 새 온보딩과 설정은 따로 돈다 — 설정은 이 파일만 보고, 온보딩 화면으로 보내지 않는다.
 */

/** 쪽지 하나가 맡는 칸. 1 원 정보 · 2 반 · 3 아동 명단. */
type Step = 1 | 2 | 3;

export function uid(prefix: string) {
  try {
    return `${prefix}-${crypto.randomUUID()}`;
  } catch {
    return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
}

/** 저장된 설정을 마운트 시 한 번만 읽는다(브라우저 전용, 서버에서는 빈 값). */
function readSaved() {
  const saved = loadClassSettings();
  return {
    saved,
    settings: saved
      ? {
          ...saved,
          regionProvince: normalizeProvince(saved.regionProvince),
          regionDistrict: saved.regionDistrict.trim(),
        }
      : EMPTY_CLASS_SETTINGS,
  };
}

/** `onDone` 은 쪽지를 닫는다. 저장이 끝나면 다음 단계로 가지 않고 부른다. */
export function useSettingsFlow(step: Step, onDone: () => void) {
  const hydrated = useHydrated();
  const [saveError, setSaveError] = useState("");
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const [startup] = useState(readSaved);
  const [settings, setSettings] = useState<ClassSettings>(startup.settings);
  const [listLoaded, setListLoaded] = useState(false);
  const loadsServerList = !!startup.saved && (step === 2 || step === 3);
  const ready = hydrated && (!loadsServerList || listLoaded);

  useEffect(() => {
    const saved = startup.saved;
    if (!saved || !(step === 2 || step === 3)) return;
    let live = true;
    const load = async () => {
      try {
        if (step === 2) {
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
        if (live) setSaveError(e instanceof Error ? e.message : "목록을 불러오지 못했어요.");
      } finally {
        if (live) setListLoaded(true);
      }
    };
    void load();
    return () => {
      live = false;
    };
  }, [step, startup]);

  function patch(p: Partial<ClassSettings>) {
    const next = { ...settings, ...p };
    setSettings(next);
    if (step === 3 && !saveClassSettings(next)) setSaveError("로컬 화면 캐시 저장 실패");
  }

  /** 원 정보 · 반 쪽지의 「저장」. 그 칸만 서버와 브라우저에 쓰고 쪽지를 닫는다. */
  async function save() {
    if (saving.current) return;
    saving.current = true;
    setBusy(true);
    setSaveError("");
    try {
      if (step === 1) await syncCenter(settings);
      if (step === 2) {
        await syncClasses(settings);
        rememberConsent(settings.classes);
      }
      // 담당 반 Select가 있는 반 쪽지에서만 표시 기본값을 확정한다.
      const submitted =
        step === 2 && settings.classes.length > 1
          ? { ...settings, primaryClassId: shownPrimaryId(settings) }
          : settings;
      if (!saveClassSettings(submitted)) throw new Error("설정을 저장하지 못했어요.");
      onDone();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "저장 실패");
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }

  /** 아동 명단 쪽지의 「닫기」. 반 목록을 한 번 맞추고 닫는다. */
  async function finish() {
    if (saving.current) return;
    saving.current = true;
    setBusy(true);
    setSaveError("");
    try {
      await syncClasses(settings);
      const done = { ...settings, completedAt: new Date().toISOString() };
      if (!saveClassSettings(done) || !completeAccountOnboarding())
        throw new Error("설정을 저장하지 못했어요.");
      setSettings(done);
      onDone();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "저장 실패");
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }

  return { ready, saveError, busy, settings, patch, save, finish };
}
