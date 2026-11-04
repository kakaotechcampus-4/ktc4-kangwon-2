"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import OnboardingLayout from "./OnboardingLayout";
import DoneScreen from "./DoneScreen";
import ReviewCenterEdit, { type CenterField } from "./ReviewCenterEdit";
import ReviewClassEdit from "./ReviewClassEdit";
import { Chevron, CtaButton, ErrorLine, LoadingLine, Question } from "./FlowParts";
import { useOnboardingData } from "./useOnboardingData";
import { Notice } from "@/components/workspace/WorkspaceUI";
import { completeAccountOnboarding } from "@/lib/auth/local-account";
import { saveClassSettings, shownPrimaryId } from "@/lib/onboarding/settings";
import { syncClasses, rememberConsent } from "@/lib/api/onboarding";
import { finishedSettings, showsPrimarySelect, withFromSettings } from "@/lib/onboarding/flow";
import { ageSelectionLabel, selectedAgesFor, type ClassroomEntry } from "@/lib/onboarding/types";

const WELCOME_KEY = "saessak.welcome";

type View =
  { kind: "list" } | { kind: "center"; field: CenterField } | { kind: "class"; id: string };

/** /onboarding/review — 마지막 확인. 원 정보와 반을 한눈에 보고, 누르면 그 칸만 고친다. */
export default function ReviewFlow() {
  const router = useRouter();
  const data = useOnboardingData("review");
  const { settings, commit, error, setError, fromSettings } = data;
  const [view, setView] = useState<View>({ kind: "list" });
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const saving = useRef(false);

  function saveSettings(next: typeof settings) {
    const ok = commit(next);
    if (ok) setView({ kind: "list" });
    return ok;
  }

  function saveClass(next: ClassroomEntry) {
    const classes = settings.classes.map((c) => (c.id === next.id ? next : c));
    rememberConsent(classes);
    // 서버가 바뀐 뒤라 브라우저 저장이 안 돼도 화면은 새 값으로 간다.
    if (!commit({ ...settings, classes })) setError("로컬 화면 캐시 저장 실패");
    setView({ kind: "list" });
  }

  function changePrimary(primaryClassId: string) {
    if (!commit({ ...settings, primaryClassId })) setError("설정을 저장하지 못했어요.");
  }

  async function finish() {
    if (saving.current) return;
    saving.current = true;
    setBusy(true);
    setError("");
    try {
      await syncClasses(settings);
      const finished = finishedSettings(settings);
      if (!saveClassSettings(finished) || !completeAccountOnboarding())
        throw new Error("설정을 저장하지 못했어요.");
      // 설정에서 고치러 온 교사에게는 환영 인사를 다시 띄우지 않는다.
      if (fromSettings) {
        router.push("/settings");
        return;
      }
      try {
        sessionStorage.setItem(WELCOME_KEY, "1");
      } catch {}
      setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장하지 못했어요.");
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }

  if (!data.ready) return <LoadingLine />;

  if (done)
    return (
      <DoneScreen
        orgName={settings.orgName}
        classCount={settings.classes.length}
        childCount={settings.classes.reduce((sum, c) => sum + c.children.length, 0)}
      />
    );

  if (view.kind === "center")
    return (
      <>
        <Notice onDone={() => setNotice("")}>{notice}</Notice>
        <ReviewCenterEdit
          field={view.field}
          settings={settings}
          onSaved={saveSettings}
          onCancel={() => setView({ kind: "list" })}
        />
      </>
    );

  const editing =
    view.kind === "class" ? settings.classes.find((c) => c.id === view.id) : undefined;
  if (editing)
    return (
      <>
        <Notice onDone={() => setNotice("")}>{notice}</Notice>
        <ReviewClassEdit
          entry={editing}
          onSaved={saveClass}
          onNotice={setNotice}
          onCancel={() => setView({ kind: "list" })}
        />
      </>
    );

  const addPath = withFromSettings("/onboarding/classes?add=1", fromSettings);
  const childrenPath = (id: string) =>
    withFromSettings(
      `/onboarding/children?class=${encodeURIComponent(id)}&back=review`,
      fromSettings,
    );
  const region = `${settings.regionProvince} ${settings.regionDistrict}`.trim();

  return (
    <OnboardingLayout
      stage={4}
      say={{ title: "다 왔어요!", body: "고칠 곳이 없으면 바로 시작하면 돼요." }}
      progress={1}
      footer={
        <CtaButton disabled={busy || settings.classes.length === 0} onClick={() => void finish()}>
          {fromSettings ? "설정으로 돌아가기" : "이대로 시작할게요"}
        </CtaButton>
      }
    >
      <Notice onDone={() => setNotice("")}>{notice}</Notice>
      <Question
        title={"입력한 정보를\n확인해주세요"}
        hint="고칠 곳을 누르면 그 칸만 바로 고칠 수 있어요."
      />

      <section aria-label="원 정보" className="mb-6">
        <SectionTitle>원 정보</SectionTitle>
        <div className="divide-y divide-shell overflow-hidden rounded-2xl border border-line">
          <Row
            label="원 이름"
            value={settings.orgName}
            onClick={() => setView({ kind: "center", field: "org" })}
          />
          <Row
            label="원장"
            value={settings.directorName}
            onClick={() => setView({ kind: "center", field: "director" })}
          />
          <Row
            label="지역"
            value={region}
            onClick={() => setView({ kind: "center", field: "region" })}
          />
        </div>
      </section>

      <SectionTitle>반</SectionTitle>
      {settings.classes.length === 0 && (
        <p role="status" className="mb-3 text-[15px] text-ink-soft">
          아직 등록한 반이 없어요.
        </p>
      )}
      {settings.classes.map((c) => (
        <ClassCard
          key={c.id}
          classroom={c}
          onEdit={() => setView({ kind: "class", id: c.id })}
          onChildren={() => router.push(childrenPath(c.id))}
        />
      ))}

      {showsPrimarySelect(settings) && (
        <PrimaryPicker
          classes={settings.classes}
          selected={shownPrimaryId(settings)}
          onPick={changePrimary}
        />
      )}
      <button
        type="button"
        onClick={() => router.push(addPath)}
        className="mt-1 min-h-11 self-start px-1 text-[15px] font-bold text-primary-ink hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
      >
        + 반 더 등록하기
      </button>
      <ErrorLine>{error}</ErrorLine>
    </OnboardingLayout>
  );
}

function SectionTitle({ children }: { children: string }) {
  return <h2 className="mb-2 text-[14px] font-bold text-ink-soft">{children}</h2>;
}

const rowClass =
  "flex min-h-14 w-full items-center gap-3 bg-paper py-3 pl-[18px] pr-4 text-left text-ink hover:bg-ivory focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary";

function Row({ label, value, onClick }: { label: string; value: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} aria-label={`${label} 고치기`} className={rowClass}>
      <span className="w-[72px] flex-none text-[14px] text-ink-soft">{label}</span>
      <span className="flex-1 text-[16px] font-semibold">{value || "-"}</span>
      <Chevron />
    </button>
  );
}

function ClassCard({
  classroom,
  onEdit,
  onChildren,
}: {
  classroom: ClassroomEntry;
  onEdit: () => void;
  onChildren: () => void;
}) {
  const consent = classroom.guardianConsent ? "받았어요" : "확인 안 함";
  return (
    <section
      aria-label={`${classroom.className} 정보`}
      className="mb-3 overflow-hidden rounded-2xl border border-line"
    >
      <div className="flex items-center justify-between gap-2 px-[18px] pb-1 pt-4">
        <h3 className="text-[17px] font-bold text-ink">{classroom.className}</h3>
        <button
          type="button"
          onClick={onEdit}
          aria-label={`${classroom.className} 고치기`}
          className="min-h-9 rounded-full border-[1.5px] border-primary-tint-line bg-primary-tint px-3.5 text-[13px] font-bold text-primary-ink hover:border-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
        >
          고치기
        </button>
      </div>
      <dl className="m-0 grid grid-cols-[112px_minmax(0,1fr)] gap-y-1.5 px-[18px] pb-3.5 pt-2 text-[15px]">
        <dt className="text-ink-soft">연령</dt>
        <dd className="m-0 text-ink">{ageSelectionLabel(selectedAgesFor(classroom))}</dd>
        <dt className="text-ink-soft">담임</dt>
        <dd className="m-0 text-ink">{classroom.teacherName}</dd>
        <dt className="text-ink-soft">법정대리인 동의</dt>
        <dd className="m-0 text-ink">{consent}</dd>
      </dl>
      {classroom.guardianConsent && (
        <button
          type="button"
          onClick={onChildren}
          aria-label={`${classroom.className} 아이 명단`}
          className={`${rowClass} border-t border-shell`}
        >
          {/* 위 표(112px 칸)와 값의 시작을 맞춘다 — 줄 사이 간격(gap-3, 12px)만큼 뺀다. */}
          <span className="w-[100px] flex-none text-[15px] text-ink-soft">아이 명단</span>
          <span className="flex-1 text-[16px] font-semibold">{classroom.children.length}명</span>
          <Chevron />
        </button>
      )}
      {!classroom.guardianConsent && (
        <p className="m-0 flex gap-3 border-t border-shell px-[18px] py-3.5 text-[15px] text-ink-soft">
          <span className="w-[112px] flex-none">아이 명단</span>
          <span>동의를 체크하면 넣을 수 있어요</span>
        </p>
      )}
    </section>
  );
}

/** 반이 둘 이상일 때만 — 메인에서 먼저 보여 줄 반. 누르면 바로 저장된다. */
function PrimaryPicker({
  classes,
  selected,
  onPick,
}: {
  classes: ClassroomEntry[];
  selected: string;
  onPick: (id: string) => void;
}) {
  return (
    <section aria-label="주로 보는 반" className="mb-3 mt-3">
      <SectionTitle>주로 보는 반</SectionTitle>
      <p className="mb-2 text-[13.5px] text-ink-soft">메인 화면에서 이 반을 먼저 보여드려요.</p>
      <div className="divide-y divide-shell overflow-hidden rounded-2xl border border-line">
        {classes.map((c, i) => {
          const on = c.id === selected;
          return (
            <button
              key={c.id}
              type="button"
              aria-pressed={on}
              onClick={() => onPick(c.id)}
              className={`${rowClass} ${on ? "bg-primary-tint hover:bg-primary-tint" : ""}`}
            >
              <span className="flex flex-1 flex-col gap-0.5">
                <span className="text-[16px] font-bold">{c.className || `반 ${i + 1}`}</span>
                <span className="text-[14px] text-ink-soft">
                  {ageSelectionLabel(selectedAgesFor(c))}
                </span>
              </span>
              {on && <CheckMark />}
            </button>
          );
        })}
      </div>
    </section>
  );
}

function CheckMark() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="shrink-0 text-primary"
    >
      <path d="M5 12l5 5 9-10" />
    </svg>
  );
}
