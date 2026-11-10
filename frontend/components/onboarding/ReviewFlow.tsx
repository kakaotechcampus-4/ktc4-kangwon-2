"use client";

import { useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import OnboardingLayout from "./OnboardingLayout";
import DoneScreen from "./DoneScreen";
import ReviewClassEdit from "./ReviewClassEdit";
import { CtaButton, EditIcon, ErrorLine, LoadingLine, Question } from "./FlowParts";
import { useOnboardingData } from "./useOnboardingData";
import { Notice } from "@/components/workspace/WorkspaceUI";
import { completeAccountOnboarding } from "@/lib/auth/local-account";
import { saveClassSettings, shownPrimaryId } from "@/lib/onboarding/settings";
import { syncClasses, rememberConsent } from "@/lib/api/onboarding";
import { finishedSettings, showsPrimarySelect } from "@/lib/onboarding/flow";
import { ageSelectionLabel, selectedAgesFor, type ClassroomEntry } from "@/lib/onboarding/types";

const WELCOME_KEY = "saessak.welcome";

type View = { kind: "list" } | { kind: "class"; id: string };

/** /onboarding/review — 마지막 확인. 원 정보와 반을 한눈에 보고, 누르면 그 칸만 고친다. */
export default function ReviewFlow() {
  const router = useRouter();
  const data = useOnboardingData("review");
  const { settings, commit, error, setError } = data;
  const [view, setView] = useState<View>({ kind: "list" });
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const saving = useRef(false);

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

  const addPath = "/onboarding/classes?add=1";
  const childrenPath = (id: string) =>
    `/onboarding/children?class=${encodeURIComponent(id)}&back=review`;
  const region = `${settings.regionProvince} ${settings.regionDistrict}`.trim();

  return (
    <OnboardingLayout
      stage={4}
      say={{ title: "다 왔어요!", body: "고칠 곳이 없으면 바로 시작하면 돼요." }}
      progress={1}
      footer={
        <CtaButton disabled={busy || settings.classes.length === 0} onClick={() => void finish()}>
          이대로 시작할게요
        </CtaButton>
      }
    >
      <div className="paper">
        <Notice onDone={() => setNotice("")}>{notice}</Notice>
      </div>
      <Question
        title={"입력한 정보를\n확인해주세요"}
        hint="반은 연필을 누르면 고칠 수 있어요. 원 정보는 바꿀 수 없어요."
      />

      {/* 칠판 높이를 다른 화면(760px)과 같게 두려고 원 · 반을 한 줄씩 요약한다. 반이 많으면 반 목록만 상자 안에서 스크롤. */}
      <section aria-label="원 정보" className="mb-5">
        <SectionTitle>원 정보</SectionTitle>
        <CenterRow name={settings.orgName} director={settings.directorName} region={region} />
      </section>

      <ClassList
        classes={settings.classes}
        primaryId={showsPrimarySelect(settings) ? shownPrimaryId(settings) : null}
        onPrimary={changePrimary}
        onEdit={(id) => setView({ kind: "class", id })}
        onChildren={(id) => router.push(childrenPath(id))}
      />
      <button
        type="button"
        onClick={() => router.push(addPath)}
        className="-mt-1.5 min-h-11 self-start px-1 text-[15px] font-bold text-primary-ink hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
      >
        + 반 더 등록하기
      </button>
      <ErrorLine>{error}</ErrorLine>
    </OnboardingLayout>
  );
}

function SectionTitle({ id, children }: { id?: string; children: string }) {
  return (
    <h2
      id={id}
      className="mb-2 text-[15px] font-bold leading-tight tracking-[0.02em] text-ink-soft"
    >
      {children}
    </h2>
  );
}

/** 원 · 반 요약 줄을 담는 상자. */
const boxClass = "overflow-hidden squircle [--r:16px] border border-line";

/**
 * 반이 이만큼을 넘으면 반 목록만 상자 안에서 스크롤한다. 한 줄은 64px(min-h) · 줄 사이 1px.
 * 2줄(128 + 1) + 3번째 줄 윗부분 26 + 줄 사이 1 + 테두리 2 = 158px — 3번째 줄이 걸쳐 보여 아래에 더 있다는 게 보인다.
 */
const SCROLL_FROM = 3;
const SCROLL_BOX = "h-[158px] overflow-y-auto";

/** 원 정보 한 줄 — 이름 / 원장 · 지역. 같은 원 선생님 모두의 정보라 고치지 않는다(ADR-068). */
function CenterRow({ name, director, region }: { name: string; director: string; region: string }) {
  return (
    <div className={`${boxClass} flex min-h-16 items-center gap-2.5 py-2 pl-[18px] pr-2`}>
      <span className="min-w-0 flex-1">
        <b className="block text-[17px] leading-6 text-ink">{name || "-"}</b>
        <span className="block text-[13.5px] leading-5 text-ink-soft">
          원장 {director || "-"} · {region || "-"}
        </span>
      </span>
      <span
        role="img"
        aria-label="원 정보는 바꿀 수 없어요"
        className="inline-flex h-11 w-11 flex-none items-center justify-center text-ink-hint"
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <rect x="5" y="11" width="14" height="10" rx="2" />
          <path d="M8 11V7a4 4 0 0 1 8 0v4" />
        </svg>
      </span>
    </div>
  );
}

/**
 * 반 목록 — 반 하나가 한 줄. 반이 둘 이상이면 줄 왼쪽 동그라미로 메인에서 먼저 볼 반을 고른다(누르면 바로 저장).
 * 반이 SCROLL_FROM 개 이상이면 목록만 상자 안에서 스크롤해 칠판 높이가 늘지 않는다.
 */
function ClassList({
  classes,
  primaryId,
  onPrimary,
  onEdit,
  onChildren,
}: {
  classes: ClassroomEntry[];
  /** 「주로 보는 반」을 고를 수 있을 때(반 2개 이상)만 값이 있다. */
  primaryId: string | null;
  onPrimary: (id: string) => void;
  onEdit: (id: string) => void;
  onChildren: (id: string) => void;
}) {
  const headingId = useId();
  const many = classes.length >= SCROLL_FROM;
  return (
    <section aria-labelledby={headingId} className="mb-5">
      <div className="flex items-baseline justify-between gap-3">
        <SectionTitle id={headingId}>{many ? `반 ${classes.length}개` : "반"}</SectionTitle>
        {primaryId !== null && (
          <span className="text-[13px] text-ink-soft">고른 반을 메인에서 먼저 보여요</span>
        )}
      </div>
      {classes.length === 0 && (
        <p role="status" className="text-[15px] text-ink-soft">
          아직 등록한 반이 없어요.
        </p>
      )}
      {classes.length > 0 && (
        <div className={boxClass}>
          <ul className={`divide-y divide-shell ${many ? SCROLL_BOX : ""}`}>
            {classes.map((c) => (
              <ClassRow
                key={c.id}
                classroom={c}
                primary={primaryId === null ? null : primaryId === c.id}
                onPrimary={() => onPrimary(c.id)}
                onEdit={() => onEdit(c.id)}
                onChildren={() => onChildren(c.id)}
              />
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

/** 반 한 줄 — (동그라미) · 반 이름 / 연령 · 담임 · 동의 · 「아이 n명」 · 연필. 단추 이름은 e2e 가 찾는 그대로. */
function ClassRow({
  classroom: c,
  primary,
  onPrimary,
  onEdit,
  onChildren,
}: {
  classroom: ClassroomEntry;
  /** null 이면 고를 수 없다(반 하나). */
  primary: boolean | null;
  onPrimary: () => void;
  onEdit: () => void;
  onChildren: () => void;
}) {
  const consent = c.guardianConsent ? "동의 받았어요" : "동의 확인 안 함";
  // 반마다 「{반} 정보」 영역 — 예전 반 카드와 같은 이름이라 화면 읽기와 e2e 가 그대로 찾는다.
  return (
    <li>
      <section
        aria-label={`${c.className} 정보`}
        className={`flex min-h-16 items-center gap-1.5 py-2 pr-2 ${primary === null ? "pl-[18px]" : "pl-1.5"} ${primary ? "bg-primary-tint" : ""}`}
      >
        {primary !== null && (
          <PrimaryRadio name={c.className} checked={primary} onClick={onPrimary} />
        )}
        <span className="min-w-0 flex-1">
          <b className="block text-[17px] leading-6 text-ink">
            {c.className}
            {primary && (
              <span className="ml-2 font-display text-[19px] text-primary">주로 봐요</span>
            )}
          </b>
          <span className="block text-[13.5px] leading-5 text-ink-soft">
            {ageSelectionLabel(selectedAgesFor(c))} · 담임 {c.teacherName} · {consent}
          </span>
        </span>
        {c.guardianConsent ? (
          <ChildrenLink name={c.className} count={c.children.length} onClick={onChildren} />
        ) : (
          <span className="flex-none px-2 text-[13px] text-ink-hint">명단은 동의 뒤에</span>
        )}
        <button
          type="button"
          onClick={onEdit}
          aria-label={`${c.className} 수정`}
          title={`${c.className} 수정`}
          className="inline-flex h-11 w-11 flex-none items-center justify-center squircle [--r:12px] text-ink-soft hover:bg-primary-tint hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
        >
          <EditIcon />
        </button>
      </section>
    </li>
  );
}

/** 「주로 보는 반」 동그라미. 둘 중 하나만 고르니 라디오 모양이다. */
function PrimaryRadio({
  name,
  checked,
  onClick,
}: {
  name: string;
  checked: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={checked}
      aria-label={`${name} 주로 보기`}
      onClick={onClick}
      className="inline-flex h-11 w-10 flex-none items-center justify-center focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
    >
      <span
        aria-hidden="true"
        className={`inline-flex h-5 w-5 items-center justify-center rounded-full border-2 ${checked ? "border-primary" : "border-ink-hint"}`}
      >
        {checked && <span className="h-2.5 w-2.5 rounded-full bg-primary" />}
      </span>
    </button>
  );
}

/** 「아이 n명 ›」 — 그 반 아이 명단으로. */
function ChildrenLink({
  name,
  count,
  onClick,
}: {
  name: string;
  count: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`${name} 아이 명단`}
      className="inline-flex min-h-11 flex-none items-center gap-0.5 pl-2.5 pr-1.5 text-[14px] font-semibold text-ink hover:text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
    >
      <span className="underline decoration-primary underline-offset-4">아이 {count}명</span>
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        className="text-primary"
      >
        <path d="M9 6l6 6-6 6" />
      </svg>
    </button>
  );
}
