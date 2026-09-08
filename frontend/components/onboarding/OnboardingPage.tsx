"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import OnboardingLayout, { StepFooter, StepHeading } from "./OnboardingLayout";
import FormField, { TextInput } from "./FormField";
import Select from "./Select";
import ChildList from "./ChildList";
import CharacterMessageGrid from "./CharacterMessageGrid";
import PrimaryButton, { GhostButton, TextButton } from "./PrimaryButton";
import { loadClassSettings, saveClassSettings } from "@/lib/onboarding/settings";
import {
  AGE_OPTIONS,
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
import { AGE_LABEL } from "@/lib/plan-generator/types";

const HOME_PATH = "/home";
const WELCOME_KEY = "saessak.welcome";

function uid(prefix: string) {
  try {
    return `${prefix}-${crypto.randomUUID()}`;
  } catch {
    return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
}

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState<OnboardingStep>(1);
  const [settings, setSettings] = useState<ClassSettings>(EMPTY_CLASS_SETTINGS);

  useEffect(() => {
    const saved = loadClassSettings();
    if (saved) setSettings(saved);
  }, []);

  function patch(p: Partial<ClassSettings>) {
    setSettings((s) => ({ ...s, ...p }));
  }

  function go(next: OnboardingStep) {
    setStep(next);
    if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function finish() {
    const done = { ...settings, completedAt: new Date().toISOString() };
    setSettings(done);
    saveClassSettings(done);
    try { sessionStorage.setItem(WELCOME_KEY, "1"); } catch { /* noop */ }
    go("done");
  }

  const orgLabel = useMemo(() => {
    const firstTeacher = settings.classes.find((c) => c.teacherName.trim())?.teacherName.trim();
    if (settings.orgName && firstTeacher) return `🌼 ${settings.orgName} · ${firstTeacher} 선생님`;
    if (settings.orgName) return `🌼 ${settings.orgName}`;
    return undefined;
  }, [settings.orgName, settings.classes]);

  return (
    <OnboardingLayout step={step} orgLabel={orgLabel}>
      {step === 1 && <StepOrgInfo settings={settings} onChange={patch} onNext={() => go(2)} />}
      {step === 2 && <StepClasses settings={settings} onChange={patch} onPrev={() => go(1)} onNext={() => go(3)} />}
      {step === 3 && <StepCharacterMessages settings={settings} onChange={patch} onPrev={() => go(2)} onFinish={finish} />}
      {step === "done" && <StepDone settings={settings} onReview={() => go(1)} onHome={() => router.push(HOME_PATH)} />}
    </OnboardingLayout>
  );
}

// ---------------------------------------------------------------------
// STEP 1 — 원 정보
// ---------------------------------------------------------------------
function StepOrgInfo({
  settings, onChange, onNext,
}: {
  settings: ClassSettings;
  onChange: (p: Partial<ClassSettings>) => void;
  onNext: () => void;
}) {
  const canNext =
    settings.orgName.trim() !== "" &&
    settings.directorName.trim() !== "" &&
    settings.regionProvince.trim() !== "" &&
    settings.regionDistrict.trim() !== "";

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
          placeholder="예: 햇살어린이집"
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
          <TextInput
            id="regionProvince"
            value={settings.regionProvince}
            placeholder="시·도  예: 경기도"
            aria-label="시·도"
            onChange={(e) => onChange({ regionProvince: e.target.value })}
          />
          <TextInput
            id="regionDistrict"
            value={settings.regionDistrict}
            placeholder="시·군·구  예: 군포시"
            aria-label="시·군·구"
            onChange={(e) => onChange({ regionDistrict: e.target.value })}
          />
        </div>
      </FormField>

      <StepFooter
        right={<PrimaryButton disabled={!canNext} onClick={onNext} className="flex-1 lg:flex-none lg:min-w-[120px]">다음</PrimaryButton>}
      />
    </>
  );
}

// ---------------------------------------------------------------------
// STEP 2 — 반 정보 · 반복 입력 + 아동 명단
// ---------------------------------------------------------------------
function StepClasses({
  settings, onChange, onPrev, onNext,
}: {
  settings: ClassSettings;
  onChange: (p: Partial<ClassSettings>) => void;
  onPrev: () => void;
  onNext: () => void;
}) {
  function updateClass(id: string, patch: Partial<ClassroomEntry>) {
    onChange({
      classes: settings.classes.map((c) => c.id === id ? { ...c, ...patch } : c),
    });
  }

  function addClass() {
    onChange({ classes: [...settings.classes, createEmptyClassroom(uid("class"))] });
  }

  function removeClass(id: string) {
    if (settings.classes.length <= 1) return;
    onChange({ classes: settings.classes.filter((c) => c.id !== id) });
  }

  const canNext = settings.classes.length > 0 && settings.classes.every((c) =>
    c.className.trim() !== "" && c.ageGroup !== "" && c.teacherName.trim() !== ""
  );

  const totalChildren = settings.classes.reduce((sum, c) => sum + c.children.length, 0);

  return (
    <>
      <StepHeading
        title="우리 반 정보를 설정해주세요"
        description="우리 반 아동의 이름을 한 명씩 입력해주세요."
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

      <GhostButton onClick={addClass} className="self-start">+ 반 추가</GhostButton>

      <StepFooter
        left={<GhostButton onClick={onPrev}>이전</GhostButton>}
        note={totalChildren === 0 ? "아동 명단은 나중에 입력할 수도 있어요" : `현재 ${totalChildren}명의 아동이 등록되어 있어요`}
        right={<PrimaryButton disabled={!canNext} onClick={onNext} className="flex-1 lg:flex-none lg:min-w-[120px]">다음</PrimaryButton>}
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
  const ageValue = classroom.ageGroup === "mixed" ? "" : classroom.ageGroup;
  const childInputDisabled = !classroom.guardianConsent || classroom.childrenSkipped;

  return (
    <section className="rounded-[20px] border border-line bg-paper p-4 lg:p-5 flex flex-col gap-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-sage-tint text-sage-ink font-mono text-[11px]">{index + 1}</span>
          <h2 className="font-display text-[16px] text-ink">반 정보</h2>
        </div>
        {canRemove && <TextButton onClick={onRemove}>이 반 삭제</TextButton>}
      </div>

      <FormField id={`className-${classroom.id}`} label="반 이름">
        <TextInput
          id={`className-${classroom.id}`}
          value={classroom.className}
          placeholder="예: 햇살반"
          onChange={(e) => onChange({ className: e.target.value })}
        />
      </FormField>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormField id={`ageGroup-${classroom.id}`} label="연령">
          <Select<Exclude<AgeGroup, "mixed">>
            id={`ageGroup-${classroom.id}`}
            value={ageValue as Exclude<AgeGroup, "mixed"> | ""}
            placeholder="연령을 선택해주세요"
            options={AGE_OPTIONS}
            onChange={(e) => onChange({ ageGroup: e.target.value as AgeGroup | "" })}
          />
        </FormField>

        <FormField id={`currentChildCount-${classroom.id}`} label="현재 원아 수" optional>
          <TextInput
            id={`currentChildCount-${classroom.id}`}
            type="number"
            min={0}
            inputMode="numeric"
            value={classroom.currentChildCount}
            placeholder="예: 18"
            onChange={(e) => onChange({ currentChildCount: e.target.value === "" ? "" : Math.max(0, Number(e.target.value)) })}
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
            onChange={(e) => onChange({ guardianConsent: e.target.checked, childrenSkipped: e.target.checked ? false : classroom.childrenSkipped })}
            className="mt-0.5 w-4 h-4 accent-[var(--pg-sage-ink)]"
          />
          <span>
            <span className="block text-[13.5px] font-medium text-ink">이 반 모든 아동의 법정대리인 동의를 받았습니다.</span>
            <span className="block mt-1 text-[12px] text-ink-soft">동의 확인 전에는 아동 이름을 입력하지 않아요.</span>
          </span>
        </label>
      </div>

      <div className="flex items-center justify-between gap-3">
        <h3 className="font-display text-[15px] text-ink">아동 명단</h3>
        <TextButton
          onClick={() => onChange({ childrenSkipped: !classroom.childrenSkipped })}
          className={classroom.childrenSkipped ? "bg-sage-tint text-sage-ink" : ""}
        >
          {classroom.childrenSkipped ? "지금 입력하기" : "나중에 입력할래요"}
        </TextButton>
      </div>

      {classroom.childrenSkipped ? (
        <div className="rounded-[18px] border border-dashed border-line bg-sage-tint px-4 py-4 text-[13px] leading-relaxed text-ink-soft">
          아동 명단은 나중에 입력할 수 있어요. 아동별 기록 기능을 사용할 때 다시 등록하면 됩니다.
        </div>
      ) : (
        <ChildList
          idPrefix={`child-${classroom.id}`}
          children={classroom.children}
          disabled={childInputDisabled}
          onAdd={(name) => onChange({ children: [...classroom.children, { id: uid("child"), name }] })}
          onRemove={(id) => onChange({ children: classroom.children.filter((c) => c.id !== id) })}
        />
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
// STEP 3 — 월별 성품인사
// ---------------------------------------------------------------------
function StepCharacterMessages({
  settings, onChange, onPrev, onFinish,
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
            <span className="block text-[13.5px] font-medium text-ink">성품교육을 사용하지 않습니다.</span>
            <span className="block mt-1 text-[12px] text-ink-soft">체크하면 아래 12개월 성품인사를 계획안에서 사용하지 않아요.</span>
          </span>
        </label>
      </div>

      <CharacterMessageGrid
        messages={settings.characterMessages}
        disabled={!settings.characterEducationEnabled}
        onChange={(month: Month, text) => onChange({ characterMessages: { ...settings.characterMessages, [month]: text } })}
        onResetAll={() => onChange({ characterMessages: { ...DEFAULT_CHARACTER_MESSAGES } })}
      />

      <StepFooter
        left={<GhostButton onClick={onPrev}>이전</GhostButton>}
        right={<PrimaryButton onClick={onFinish} className="flex-1 lg:flex-none lg:min-w-[140px]">설정 완료</PrimaryButton>}
      />
    </>
  );
}

// ---------------------------------------------------------------------
// 완료
// ---------------------------------------------------------------------
function StepDone({ settings, onReview, onHome }: { settings: ClassSettings; onReview: () => void; onHome: () => void }) {
  const edited = MONTH_ORDER.filter((m) => settings.characterMessages[m] !== DEFAULT_CHARACTER_MESSAGES[m]).length;
  const totalChildren = settings.classes.reduce((sum, c) => sum + c.children.length, 0);
  const firstClass = settings.classes[0];
  const firstAge = firstClass?.ageGroup ? AGE_LABEL[firstClass.ageGroup].replace("만 ", "") : "";

  return (
    <div className="flex flex-col items-center text-center gap-[18px] py-2">
      <svg width="132" height="90" viewBox="0 0 132 90" aria-hidden="true" style={{ animation: "pg-float 5s ease-in-out infinite" }}>
        <circle cx="40" cy="52" r="34" className="fill-sage" />
        <circle cx="30" cy="44" r="3.2" fill="#fff" /><circle cx="30" cy="44" r="1.6" fill="var(--pg-ink)" />
        <circle cx="46" cy="44" r="3.2" fill="#fff" /><circle cx="46" cy="44" r="1.6" fill="var(--pg-ink)" />
        <path d="M30 60Q38 67 47 59" stroke="var(--pg-ink)" strokeWidth="2.2" fill="none" strokeLinecap="round" />
        <circle cx="98" cy="38" r="24" className="fill-mint" />
        <circle cx="90" cy="33" r="2.6" fill="#fff" /><circle cx="90" cy="33" r="1.3" fill="var(--pg-ink)" />
        <circle cx="103" cy="33" r="2.6" fill="#fff" /><circle cx="103" cy="33" r="1.3" fill="var(--pg-ink)" />
        <path d="M91 44Q98 49 106 43" stroke="var(--pg-ink)" strokeWidth="2" fill="none" strokeLinecap="round" />
        <circle cx="118" cy="14" r="4" className="fill-peach" />
      </svg>

      <div>
        <h1 className="font-display text-2xl text-ink">초기 설정이 완료되었어요!</h1>
        <p className="mt-2.5 text-[14.5px] leading-relaxed text-ink-soft">이제 메인 화면에서 새싹플랜을 시작할 수 있어요.</p>
      </div>

      <dl className="grid grid-cols-2 lg:grid-cols-4 gap-2 lg:gap-2.5 w-full max-w-[640px]">
        {[
          ["어린이집", settings.orgName || "-"],
          ["등록 반", `${settings.classes.length}개${firstClass?.className ? ` · ${firstClass.className}${firstAge ? ` ${firstAge}` : ""}` : ""}`],
          ["등록 아동", `${totalChildren}명`],
          ["성품인사", settings.characterEducationEnabled ? `12개월${edited ? ` · ${edited}개 수정` : ""}` : "미사용"],
        ].map(([k, v]) => (
          <div key={k} className="rounded-2xl bg-sage-tint px-2.5 py-3">
            <dt className="font-mono text-[10.5px] tracking-wider text-ink-soft">{k}</dt>
            <dd className="mt-0.5 text-[14px] lg:text-[15px] font-bold text-ink break-words">{v}</dd>
          </div>
        ))}
      </dl>

      <PrimaryButton onClick={onHome} className="w-full lg:w-auto px-8">메인으로 이동 →</PrimaryButton>
      <TextButton onClick={onReview}>설정 다시 확인하기</TextButton>
    </div>
  );
}
