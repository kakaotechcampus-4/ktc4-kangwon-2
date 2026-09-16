"use client";
import AgeSelection from "./AgeSelection";

import { useEffect, useRef, useState } from "react";
import { useHydrated } from "@/lib/hooks/use-client-state";
import { useRouter } from "next/navigation";
import OnboardingLayout, { StepFooter, StepHeading } from "./OnboardingLayout";
import FormField, { TextInput } from "./FormField";
import Select from "./Select";
import ChildList from "./ChildList";
import CharacterMessageGrid from "./CharacterMessageGrid";
import PrimaryButton, { GhostButton, TextButton } from "./PrimaryButton";
import { loadClassSettings, saveClassSettings } from "@/lib/onboarding/settings";
import { completeAccountOnboarding, onboardingDestination } from "@/lib/auth/local-account";
import {
  selectedAgesFor,
  ageSelectionLabel,
  DEFAULT_CHARACTER_MESSAGES,
  EMPTY_CLASS_SETTINGS,
  MONTH_ORDER,
  createEmptyClassroom,
  type AgeGroup,
  type ClassSettings,
  type ClassroomEntry,
  type Month,
  type OnboardingStep,
} from "@/lib/onboarding/types";
import { PROVINCE_OPTIONS, districtsFor, normalizeProvince } from "@/lib/onboarding/regions";

import {
  syncCenter,
  syncClasses,
  rememberConsent,
  hasConsent,
  migrateChildren,
  loadServerClasses,
  loadServerChildren,
  addServerChild,
  removeServerChild,
} from "@/lib/api/onboarding";

const HOME_PATH = "/";
const WELCOME_KEY = "saessak.welcome";

function uid(prefix: string) {
  try {
    return `${prefix}-${crypto.randomUUID()}`;
  } catch {
    return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
}

/** 저장된 설정과 진입 가능한 단계를 마운트 시 한 번만 읽는다(브라우저 전용, 서버에서는 빈 값). */
function readStartup(step: OnboardingStep) {
  const saved = loadClassSettings();
  const destination = onboardingDestination();
  const redirectTo =
    (step === 2 || step === 3) && destination === "/onboarding/center"
      ? destination
      : step === 3 && destination === "/onboarding/classes"
        ? destination
        : null;
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

export default function OnboardingPage({ step = 1 }: { step?: OnboardingStep }) {
  const router = useRouter();
  const hydrated = useHydrated();
  const [saveError, setSaveError] = useState("");
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const [startup] = useState(() => readStartup(step));
  const [settings, setSettings] = useState<ClassSettings>(startup.settings);
  const [listLoaded, setListLoaded] = useState(false);
  // 서버 목록을 불러와야 하는 단계인지, 다른 단계로 돌려보내는 중인지는 렌더 중에 계산한다.
  const loadsServerList = !startup.redirectTo && !!startup.saved && (step === 2 || step === 3);
  const ready = hydrated && !startup.redirectTo && (!loadsServerList || listLoaded);

  useEffect(() => {
    const saved = startup.saved;
    if (startup.redirectTo) {
      router.replace(startup.redirectTo);
      return;
    }
    if (!saved || !(step === 2 || step === 3)) return;
    let live = true;
    const load = async () => {
      try {
        if (step === 2) {
          const next = await loadServerClasses(saved);
          if (live) setSettings(next);
        } else {
          // Existing local lists are migrated only after explicit consent.
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
  }, [step, router, startup]);

  function patch(p: Partial<ClassSettings>) {
    const next = { ...settings, ...p };
    next.primaryClassId = next.classes.some((c) => c.id === next.primaryClassId)
      ? next.primaryClassId
      : next.classes[0]?.id;
    setSettings(next);
    if (step === 3 && !saveClassSettings(next)) setSaveError("로컬 화면 캐시 저장 실패");
  }
  async function go(next: OnboardingStep) {
    if (saving.current) return;
    saving.current = true;
    setBusy(true);
    setSaveError("");
    try {
      if (step === 1 && next === 2) await syncCenter(settings);
      if (step === 2 && next === 3) {
        await syncClasses(settings);
        rememberConsent(settings.classes);
      }
      if (!saveClassSettings(settings)) throw new Error("설정을 저장하지 못했어요.");
      router.push(
        next === 1
          ? "/onboarding/center"
          : next === 2
            ? "/onboarding/classes"
            : next === 3
              ? "/onboarding/children"
              : "/settings",
      );
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "저장 실패");
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }
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
      try {
        sessionStorage.setItem(WELCOME_KEY, "1");
      } catch {}
      router.push(HOME_PATH);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "저장 실패");
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }

  if (!ready)
    return (
      <p role="status" className="p-6">
        설정을 불러오고 있어요.
      </p>
    );

  return (
    <OnboardingLayout step={step}>
      {saveError && (
        <p role="alert" className="text-peach-ink">
          {saveError}
        </p>
      )}
      {busy && <p role="status">저장 중이에요.</p>}
      <fieldset disabled={busy} className="contents">
        {step === 1 && <StepOrgInfo settings={settings} onChange={patch} onNext={() => go(2)} />}
        {step === 2 && (
          <StepClasses
            settings={settings}
            onChange={patch}
            onPrev={() => go(1)}
            onNext={() => go(3)}
          />
        )}
        {step === 3 && (
          <StepChildren settings={settings} onChange={patch} onPrev={() => go(2)} onNext={finish} />
        )}
        {step === 4 && (
          <StepCharacterMessages
            settings={settings}
            onChange={patch}
            onPrev={() => go(3)}
            onFinish={finish}
          />
        )}
        {step === "done" && (
          <StepDone
            settings={settings}
            onReview={() => go(1)}
            onHome={() => router.push(HOME_PATH)}
          />
        )}
      </fieldset>
    </OnboardingLayout>
  );
}

// ---------------------------------------------------------------------
// STEP 1 — 원 정보
// ---------------------------------------------------------------------
function StepOrgInfo({
  settings,
  onChange,
  onNext,
}: {
  settings: ClassSettings;
  onChange: (p: Partial<ClassSettings>) => void;
  onNext: () => void;
}) {
  const districts = districtsFor(settings.regionProvince);
  const canNext =
    settings.orgName.trim() !== "" &&
    settings.directorName.trim() !== "" &&
    districts.includes(settings.regionDistrict);

  return (
    <>
      <StepHeading
        title="어린이집 기본 정보를 입력해주세요"
        description="계획안 작성에 활용할 기본 정보를 먼저 설정해요."
      />

      <FormField id="orgName" label="원명">
        <TextInput
          id="orgName"
          value={settings.orgName}
          placeholder="기관명을 입력해주세요"
          onChange={(e) => onChange({ orgName: e.target.value })}
        />
      </FormField>

      <FormField id="directorName" label="원장 이름">
        <TextInput
          id="directorName"
          value={settings.directorName}
          placeholder="원장 이름을 입력해주세요"
          onChange={(e) => onChange({ directorName: e.target.value })}
        />
      </FormField>

      <FormField label="지역">
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
          <Select
            id="regionProvince"
            value={settings.regionProvince}
            options={PROVINCE_OPTIONS}
            placeholder="시·도 선택"
            aria-label="시·도"
            onChange={(e) =>
              onChange({
                regionProvince: e.target.value,
                regionDistrict: e.target.value === "세종특별자치시" ? "세종특별자치시" : "",
              })
            }
          />
          <Select
            id="regionDistrict"
            value={districts.includes(settings.regionDistrict) ? settings.regionDistrict : ""}
            options={districts.map((value) => ({ value, label: value }))}
            disabled={districts.length === 0}
            placeholder={districts.length === 0 ? "시·도를 먼저 선택해주세요" : "시·군·구 선택"}
            aria-label="시·군·구"
            onChange={(e) => onChange({ regionDistrict: e.target.value })}
          />
        </div>
      </FormField>

      <StepFooter
        right={
          <PrimaryButton
            disabled={!canNext}
            onClick={onNext}
            className="flex-1 lg:flex-none lg:min-w-[120px]"
          >
            다음
          </PrimaryButton>
        }
      />
    </>
  );
}

// ---------------------------------------------------------------------
// STEP 2 — 반 정보 · 법정대리인 동의
// ---------------------------------------------------------------------
function StepClasses({
  settings,
  onChange,
  onPrev,
  onNext,
}: {
  settings: ClassSettings;
  onChange: (p: Partial<ClassSettings>) => void;
  onPrev: () => void;
  onNext: () => void;
}) {
  function updateClass(id: string, patch: Partial<ClassroomEntry>) {
    onChange({
      classes: settings.classes.map((c) => (c.id === id ? { ...c, ...patch } : c)),
    });
  }

  function addClass() {
    onChange({ classes: [...settings.classes, createEmptyClassroom(uid("class"))] });
  }

  function removeClass(id: string) {
    if (settings.classes.length <= 1) return;
    onChange({ classes: settings.classes.filter((c) => c.id !== id) });
  }

  const canNext =
    settings.classes.length > 0 &&
    settings.classes.every(
      (c) =>
        c.className.trim() !== "" && selectedAgesFor(c).length > 0 && c.teacherName.trim() !== "",
    );

  return (
    <>
      <StepHeading
        title="우리 반 정보를 설정해주세요"
        description="반 정보와 법정대리인 동의 여부를 확인해주세요. 아동 명단은 다음 단계에서 입력해요."
      />

      <div className="flex flex-col gap-5">
        {settings.classes.map((classroom, index) => (
          <ClassroomCard
            key={classroom.id}
            classroom={classroom}
            index={index}
            canRemove={settings.classes.length > 1}
            onChange={(p) => updateClass(classroom.id, p)}
            onRemove={() => removeClass(classroom.id)}
          />
        ))}
      </div>

      {settings.classes.length > 1 && (
        <FormField id="primaryClassId" label="내 담당 반">
          <Select
            id="primaryClassId"
            value={settings.primaryClassId || settings.classes[0]?.id || ""}
            options={settings.classes.map((c, i) => ({
              value: c.id,
              label: c.className || "반 " + (i + 1),
            }))}
            onChange={(e) => onChange({ primaryClassId: e.target.value })}
          />
        </FormField>
      )}
      <GhostButton onClick={addClass} className="self-start">
        + 반 추가
      </GhostButton>

      <StepFooter
        left={<GhostButton onClick={onPrev}>이전</GhostButton>}
        right={
          <PrimaryButton
            disabled={!canNext}
            onClick={onNext}
            className="flex-1 lg:flex-none lg:min-w-[120px]"
          >
            다음
          </PrimaryButton>
        }
      />
    </>
  );
}

function ClassroomCard({
  classroom,
  index,
  canRemove,
  onChange,
  onRemove,
}: {
  classroom: ClassroomEntry;
  index: number;
  canRemove: boolean;
  onChange: (p: Partial<ClassroomEntry>) => void;
  onRemove: () => void;
}) {
  return (
    <section className="rounded-[20px] border border-line bg-paper p-4 lg:p-5 flex flex-col gap-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-sage-tint text-sage-ink font-mono text-[11px]">
            {index + 1}
          </span>
          <h2 className="font-display text-[16px] text-ink">반 정보</h2>
        </div>
        {canRemove && (
          <button
            type="button"
            onClick={onRemove}
            aria-label={`${classroom.className || `${index + 1}번 반`} 삭제`}
            className="inline-flex items-center justify-center gap-1.5 rounded-xl border-[1.5px] border-red-200 bg-red-50 px-3 py-2 min-h-[40px] text-[12.5px] font-medium text-red-500 hover:bg-red-100 hover:border-red-300 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-300"
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M3 6h18M9 6V4h6v2M5 6l1 14h12l1-14M10 10v6M14 10v6" />
            </svg>
            삭제
          </button>
        )}
      </div>

      <FormField id={`className-${classroom.id}`} label="반 이름">
        <TextInput
          id={`className-${classroom.id}`}
          value={classroom.className}
          placeholder="반 이름을 입력해주세요"
          onChange={(e) => onChange({ className: e.target.value })}
        />
      </FormField>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <AgeSelection
          value={selectedAgesFor(classroom)}
          onChange={(selectedAges) =>
            onChange({
              selectedAges,
              ageGroup: selectedAges.length === 1 ? (String(selectedAges[0]) as AgeGroup) : "",
            })
          }
        />

        <FormField id={`currentChildCount-${classroom.id}`} label="현재 원아 수" optional>
          <TextInput
            id={`currentChildCount-${classroom.id}`}
            type="number"
            min={0}
            inputMode="numeric"
            value={classroom.currentChildCount}
            placeholder="예: 18"
            onChange={(e) =>
              onChange({
                currentChildCount: e.target.value === "" ? "" : Math.max(0, Number(e.target.value)),
              })
            }
          />
        </FormField>
      </div>

      <FormField id={`teacherName-${classroom.id}`} label="담임 이름">
        <TextInput
          id={`teacherName-${classroom.id}`}
          value={classroom.teacherName}
          placeholder="담임 이름을 입력해주세요"
          onChange={(e) => onChange({ teacherName: e.target.value })}
        />
      </FormField>

      <div className="rounded-[18px] border border-line bg-peach-tint px-4 py-3.5">
        <label className="flex items-start gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={classroom.guardianConsent}
            onChange={(e) =>
              onChange({
                guardianConsent: e.target.checked,
                childrenSkipped: e.target.checked ? false : classroom.childrenSkipped,
              })
            }
            className="mt-0.5 w-4 h-4 accent-[var(--pg-sage-ink)]"
          />
          <span>
            <span className="block text-[13.5px] font-medium text-ink">
              이 반 모든 아동의 법정대리인 동의를 받았습니다.
            </span>
            <span className="block mt-1 text-[12px] text-ink-soft">
              동의 확인 전에는 아동 이름을 입력하지 않아요.
            </span>
          </span>
        </label>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------
// STEP 3 — 반별 아동 명단
// ---------------------------------------------------------------------
function StepChildren({
  settings,
  onChange,
  onPrev,
  onNext,
}: {
  settings: ClassSettings;
  onChange: (p: Partial<ClassSettings>) => void;
  onPrev: () => void;
  onNext: () => void;
}) {
  return (
    <>
      <StepHeading
        title="우리 반 아동 명단을 입력해주세요"
        description="반별로 아동의 이름을 한 명씩 등록해주세요. 아동 명단은 나중에 입력할 수도 있어요."
      />
      <div className="flex flex-col gap-5">
        {settings.classes.map((classroom) => (
          <ClassroomChildrenCard
            key={classroom.id}
            classroom={classroom}
            onChange={(patch) =>
              onChange({
                classes: settings.classes.map((c) =>
                  c.id === classroom.id ? { ...c, ...patch } : c,
                ),
              })
            }
          />
        ))}
      </div>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 pt-[54px] mt-1 border-t border-line">
        <div className="justify-self-start">
          <GhostButton onClick={onPrev}>이전</GhostButton>
        </div>
        <p className="text-center text-[13px] text-ink-soft whitespace-nowrap">
          아동 명단은 나중에 등록할 수 있습니다.
        </p>
        <div className="justify-self-end">
          <PrimaryButton onClick={onNext} className="lg:min-w-[120px]">
            설정 완료
          </PrimaryButton>
        </div>
      </div>
    </>
  );
}

function ClassroomChildrenCard({
  classroom,
  onChange,
}: {
  classroom: ClassroomEntry;
  onChange: (p: Partial<ClassroomEntry>) => void;
}) {
  return (
    <section className="rounded-[20px] border border-line bg-paper p-4 lg:p-5 flex flex-col gap-5">
      <h2 className="font-display text-[17px] text-ink">{classroom.className} · 아동 명단</h2>
      {classroom.currentChildCount !== "" &&
        classroom.children.length !== classroom.currentChildCount && (
          <p className="text-xs text-ink-soft">
            현재 원아 수는 {classroom.currentChildCount}명으로 설정되어 있고, 현재 명단에는{" "}
            {classroom.children.length}명이 등록되어 있습니다.
          </p>
        )}
      <ChildList
        idPrefix={`child-${classroom.id}`}
        items={classroom.children}
        onAdd={async (name) => {
          const child = await addServerChild(classroom, name);
          onChange({ children: [...classroom.children, child] });
        }}
        onRemove={async (id) => {
          await removeServerChild(id);
          onChange({ children: classroom.children.filter((c) => c.id !== id) });
        }}
      />
    </section>
  );
}

// ---------------------------------------------------------------------
// STEP 4 — 월별 성품인사
// ---------------------------------------------------------------------
export function StepCharacterMessages({
  settings,
  onChange,
  onPrev,
  onFinish,
}: {
  settings: ClassSettings;
  onChange: (p: Partial<ClassSettings>) => void;
  onPrev: () => void;
  onFinish: () => void;
}) {
  return (
    <>
      <StepHeading
        title="월별 성품인사를 설정해주세요"
        description="월별 성품인사를 확인하고 필요하면 수정해주세요. 설정한 문구는 해당 월의 계획안 작성에 활용돼요."
      />

      <div className="rounded-[18px] border border-line bg-sage-tint px-4 py-3.5">
        <label className="flex items-start gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={!settings.characterEducationEnabled}
            onChange={(e) => onChange({ characterEducationEnabled: !e.target.checked })}
            className="mt-0.5 w-4 h-4 accent-[var(--pg-sage-ink)]"
          />
          <span>
            <span className="block text-[13.5px] font-medium text-ink">
              성품교육을 사용하지 않습니다.
            </span>
            <span className="block mt-1 text-[12px] text-ink-soft">
              체크하면 아래 12개월 성품인사를 계획안에서 사용하지 않아요.
            </span>
          </span>
        </label>
      </div>

      <CharacterMessageGrid
        messages={settings.characterMessages}
        disabled={!settings.characterEducationEnabled}
        onChange={(month: Month, text) =>
          onChange({ characterMessages: { ...settings.characterMessages, [month]: text } })
        }
        onResetAll={() => onChange({ characterMessages: { ...DEFAULT_CHARACTER_MESSAGES } })}
      />

      <StepFooter
        left={<GhostButton onClick={onPrev}>이전</GhostButton>}
        right={
          <PrimaryButton onClick={onFinish} className="flex-1 lg:flex-none lg:min-w-[140px]">
            설정 완료
          </PrimaryButton>
        }
      />
    </>
  );
}

// ---------------------------------------------------------------------
// 완료
// ---------------------------------------------------------------------
function StepDone({
  settings,
  onReview,
  onHome,
}: {
  settings: ClassSettings;
  onReview: () => void;
  onHome: () => void;
}) {
  const edited = MONTH_ORDER.filter(
    (m) => settings.characterMessages[m] !== DEFAULT_CHARACTER_MESSAGES[m],
  ).length;
  const totalChildren = settings.classes.reduce((sum, c) => sum + c.children.length, 0);
  const firstClass = settings.classes[0];
  const firstAge = firstClass ? ageSelectionLabel(selectedAgesFor(firstClass)) : "";

  return (
    <div className="flex flex-col items-center text-center gap-[18px] py-2">
      <svg
        width="132"
        height="90"
        viewBox="0 0 132 90"
        aria-hidden="true"
        style={{ animation: "pg-float 5s ease-in-out infinite" }}
      >
        <circle cx="40" cy="52" r="34" className="fill-sage" />
        <circle cx="30" cy="44" r="3.2" fill="#fff" />
        <circle cx="30" cy="44" r="1.6" fill="var(--pg-ink)" />
        <circle cx="46" cy="44" r="3.2" fill="#fff" />
        <circle cx="46" cy="44" r="1.6" fill="var(--pg-ink)" />
        <path
          d="M30 60Q38 67 47 59"
          stroke="var(--pg-ink)"
          strokeWidth="2.2"
          fill="none"
          strokeLinecap="round"
        />
        <circle cx="98" cy="38" r="24" className="fill-mint" />
        <circle cx="90" cy="33" r="2.6" fill="#fff" />
        <circle cx="90" cy="33" r="1.3" fill="var(--pg-ink)" />
        <circle cx="103" cy="33" r="2.6" fill="#fff" />
        <circle cx="103" cy="33" r="1.3" fill="var(--pg-ink)" />
        <path
          d="M91 44Q98 49 106 43"
          stroke="var(--pg-ink)"
          strokeWidth="2"
          fill="none"
          strokeLinecap="round"
        />
        <circle cx="118" cy="14" r="4" className="fill-peach" />
      </svg>

      <div>
        <h1 className="font-display text-2xl text-ink">초기 설정이 완료되었어요!</h1>
        <p className="mt-2.5 text-[14.5px] leading-relaxed text-ink-soft">
          이제 메인 화면에서 쓱싹요정을 시작할 수 있어요.
        </p>
      </div>

      <dl className="grid grid-cols-2 lg:grid-cols-4 gap-2 lg:gap-2.5 w-full max-w-[640px]">
        {[
          ["어린이집", settings.orgName || "-"],
          [
            "등록 반",
            `${settings.classes.length}개${firstClass?.className ? ` · ${firstClass.className}${firstAge ? ` ${firstAge}` : ""}` : ""}`,
          ],
          ["등록 아동", `${totalChildren}명`],
          [
            "성품인사",
            settings.characterEducationEnabled
              ? `12개월${edited ? ` · ${edited}개 수정` : ""}`
              : "미사용",
          ],
        ].map(([k, v]) => (
          <div key={k} className="rounded-2xl bg-sage-tint px-2.5 py-3">
            <dt className="font-mono text-[10.5px] tracking-wider text-ink-soft">{k}</dt>
            <dd className="mt-0.5 text-[14px] lg:text-[15px] font-bold text-ink break-words">
              {v}
            </dd>
          </div>
        ))}
      </dl>

      <PrimaryButton onClick={onHome} className="w-full lg:w-auto px-8">
        메인으로 이동 →
      </PrimaryButton>
      <TextButton onClick={onReview}>설정 다시 확인하기</TextButton>
    </div>
  );
}
