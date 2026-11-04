"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Posty } from "@/components/app/Posty";
import OnboardingLayout from "./OnboardingLayout";
import {
  CtaButton,
  ErrorLine,
  FieldLabel,
  LoadingLine,
  Question,
  TextAction,
  Typed,
  onEnter,
  useTypewriter,
} from "./FlowParts";
import { useOnboardingData } from "./useOnboardingData";
import { addServerChild, removeServerChild } from "@/lib/api/onboarding";
import { REVIEW_PATH, withFromSettings } from "@/lib/onboarding/flow";
import type { ChildEntry, ClassroomEntry } from "@/lib/onboarding/types";

/** 받침이 있으면 「은」, 없으면 「는」. 반 · 아이 이름 뒤 조사를 맞춘다. */
function eunNeun(word: string) {
  const code = word.trim().charCodeAt(word.trim().length - 1);
  const batchim = code >= 0xac00 && code <= 0xd7a3 && (code - 0xac00) % 28 !== 0;
  return word + (batchim ? "은" : "는");
}

/** /onboarding/children — 반마다 한 화면. 포스티가 말을 걸고, 이름은 넣을 때마다 바로 저장된다. */
export default function ChildrenFlow() {
  const router = useRouter();
  const data = useOnboardingData("children");
  const { settings, commit, error, setError, fromSettings, params } = data;
  const onlyId = params.get("class");
  const backToReview = params.get("back") === "review";
  const [index, setIndex] = useState(0);
  const [bubble, setBubble] = useState("");

  const classes = onlyId ? settings.classes.filter((c) => c.id === onlyId) : settings.classes;
  const classroom = classes[index];
  const reviewPath = withFromSettings(REVIEW_PATH, fromSettings);

  function updateChildren(id: string, children: ClassroomEntry["children"]) {
    const next = {
      ...settings,
      classes: settings.classes.map((c) =>
        c.id === id ? { ...c, children, childIds: children.map((entry) => entry.id) } : c,
      ),
    };
    // 이름은 서버에 이미 저장됐다. 브라우저 캐시 저장이 안 돼도 화면은 계속 쓸 수 있다.
    if (!commit(next)) setError("로컬 화면 캐시 저장 실패");
  }

  function nextClass() {
    setBubble("");
    if (index + 1 < classes.length) setIndex(index + 1);
    else router.push(reviewPath);
  }

  // 첫 반에서는 되돌아갈 곳이 없다 — 반 정보로 돌아가면 빈 「새 반」 칸이 열려 반이 하나 더 생긴다.
  // 이미 등록한 반은 마지막 확인에서 고친다.
  const canBack = index > 0 || backToReview;
  function back() {
    setBubble("");
    if (index > 0) setIndex(index - 1);
    else router.push(reviewPath);
  }

  if (!data.ready) return <LoadingLine />;
  if (!classroom) return <NoClass onBack={() => router.push(reviewPath)} />;

  const consented = classroom.guardianConsent;
  const count = classroom.children.length;
  const progress = 2 / 3 + ((index + 1) / Math.max(1, classes.length)) * (1 / 3);

  async function add(name: string) {
    const child = await addServerChild(classroom, name);
    updateChildren(classroom.id, [...classroom.children, child]);
    setBubble(`${name} 추가했어요. 다음 친구 이름은요?`);
  }
  async function remove(child: ChildEntry) {
    await removeServerChild(child.id);
    updateChildren(
      classroom.id,
      classroom.children.filter((c) => c.id !== child.id),
    );
    setBubble(`${child.name} 뺐어요.`);
  }

  const speech = bubble || "한 명씩 적고 Enter를 누르면 바로 명단에 들어가요. 이름만 받아요.";

  const footer = consented ? (
    <>
      <TextAction onClick={nextClass}>나중에 넣을게요</TextAction>
      <CtaButton disabled={count === 0} onClick={nextClass}>
        {count ? `${count}명 다 넣었어요` : "다 넣었어요"}
      </CtaButton>
    </>
  ) : (
    <CtaButton onClick={nextClass}>다음</CtaButton>
  );

  return (
    <OnboardingLayout
      stage={3}
      say={
        consented
          ? { title: "마지막 단계예요!", body: speech }
          : { title: "잠깐요!", body: "동의를 확인해야 아이 이름을 받을 수 있어요." }
      }
      live={consented}
      progress={progress}
      onBack={canBack ? back : undefined}
      footer={footer}
    >
      <Question
        title={
          consented
            ? `${classroom.className} 아이들 이름을\n한 명씩 알려주세요`
            : `${classroom.className} 아이 명단은\n동의를 확인한 뒤에 받아요`
        }
      />
      {consented && (
        <>
          <Speech>{speech}</Speech>
          <KidInput
            // 반마다 새로 만든다. 같은 칸을 이어 쓰면 A반에 적다 만 이름이 B반 입력칸에 남아
            // 그대로 B반에 저장된다. 저장 중에 반을 넘겨도 옛 칸은 사라져 이름이 따라오지 않는다.
            key={classroom.id}
            classroom={classroom}
            onAdd={add}
          />
          <p className="mb-2.5 mt-6 text-[14px] font-bold text-ink-soft">
            {classroom.className} · {count}명
          </p>
          <KidChips items={classroom.children} onRemove={remove} />
        </>
      )}
      {!consented && <Locked name={classroom.className} />}
      <ErrorLine>{error}</ErrorLine>
    </OnboardingLayout>
  );
}

/**
 * 포스티 말풍선(휴대폰). 이름을 넣고 뺄 때마다 바뀌므로 화면 읽기 프로그램이 읽어 준다.
 * 768px 부터는 같은 말을 오른쪽 칸 포스티가 한다(OnboardingLayout 의 `say` · `live`).
 */
function Speech({ children }: { children: string }) {
  return (
    <div className="mb-6 flex items-end gap-2.5 md:hidden">
      <Posty pose="stand" tone="note" face="base" size={44} label={null} />
      <p className="max-w-[320px] squircle [--r-bl:6px] [--r:18px] border border-note-soft-line bg-note-soft px-4 py-3 text-[15px] leading-[1.55] text-ink">
        <span className="sr-only" aria-live="polite">
          {children}
        </span>
        <SpeechText key={children} text={children} />
      </p>
    </div>
  );
}

/** 말풍선 글을 한 글자씩 친다(화면 읽기 프로그램에는 숨김 — 다 된 글은 바로 위 sr-only 가 읽힌다). */
function SpeechText({ text }: { text: string }) {
  const shown = useTypewriter(text.length);
  return (
    <span aria-hidden="true">
      <Typed text={text} shown={shown} />
    </span>
  );
}

/** 동의 확인 전인 반 — 이름 칸을 열지 않는다(ADR-004 · screen-spec S2). */
function Locked({ name }: { name: string }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end gap-2.5">
        {/* 768px 부터는 오른쪽 칸 포스티가 「잠깐요!」 한다 — 한 화면에 포스티는 하나. */}
        <Posty pose="stand" tone="caution" face="oh" size={44} label={null} className="md:hidden" />
        <p className="max-w-[320px] squircle [--r-bl:6px] [--r:18px] border border-alert-soft-line bg-alert-soft/40 px-4 py-3 text-[15px] leading-[1.55] text-ink">
          {eunNeun(name)} 아직 법정대리인 동의를 확인하지 않아서 아이 이름을 받지 않아요.
        </p>
      </div>
      <p className="text-[14px] leading-[1.6] text-ink-soft">
        동의를 받으면 마지막 확인 화면에서 체크하고 이름을 넣을 수 있어요.
      </p>
    </div>
  );
}

/**
 * 이름 한 칸 + 「추가」. Enter 로도 넣는다(한글 조합 중 Enter 는 무시).
 * 저장을 기다리지 않고 칸부터 비운다 — 그 사이 치는 다음 이름이 앞 이름에 붙지 않게.
 * 실패하면 적은 이름을 되돌려 둔다(screen-spec S3 「입력한 이름을 지우지 않는다」).
 */
function KidInput({
  classroom,
  onAdd,
}: {
  classroom: ClassroomEntry;
  onAdd: (name: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const empty = draft.trim() === "";

  async function submit() {
    const name = draft.trim();
    if (busy || !name) return;
    if (classroom.children.some((c) => c.name === name)) {
      setError(`${eunNeun(name)} 이미 명단에 있어요.`);
      return;
    }
    setBusy(true);
    setError("");
    setDraft("");
    try {
      await onAdd(name);
    } catch (e) {
      setDraft((d) => d || name);
      setError(e instanceof Error ? e.message : "추가하지 못했어요.");
    } finally {
      setBusy(false);
    }
  }

  const id = `kid-${classroom.id}`;
  return (
    <div>
      <div className="flex items-end gap-2">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <FieldLabel htmlFor={id}>아이 이름</FieldLabel>
          <input
            id={id}
            type="text"
            autoComplete="off"
            autoFocus
            value={draft}
            placeholder="예: 가온"
            aria-invalid={error ? true : undefined}
            onChange={(e) => {
              setDraft(e.target.value);
              setError("");
            }}
            onKeyDown={(e) => onEnter(e, () => void submit())}
            className="w-full border-0 border-b-2 border-primary bg-transparent pb-2.5 pt-1.5 text-[22px] font-semibold text-ink outline-none placeholder:text-ink-hint"
          />
        </div>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={empty || busy}
          className="h-12 flex-none squircle [--r:12px] bg-primary px-5 text-[15px] font-bold text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-primary-tint disabled:text-ink-hint focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          추가
        </button>
      </div>
      <div className="mt-2.5">
        <ErrorLine>{error}</ErrorLine>
      </div>
    </div>
  );
}

/** 넣은 이름 — 알약 모양, × 로 뺀다. */
function KidChips({
  items,
  onRemove,
}: {
  items: ChildEntry[];
  onRemove: (child: ChildEntry) => Promise<void>;
}) {
  const [error, setError] = useState("");
  if (!items.length) return <p className="text-[14px] text-ink-soft">아직 넣은 이름이 없어요.</p>;

  async function remove(child: ChildEntry) {
    setError("");
    try {
      await onRemove(child);
    } catch (e) {
      setError(e instanceof Error ? e.message : "빼지 못했어요.");
    }
  }

  return (
    <>
      <ul className="flex flex-wrap gap-2">
        {items.map((child) => (
          <li
            key={child.id}
            className="inline-flex items-center gap-0.5 rounded-full bg-cream py-0 pl-3.5 pr-0.5 text-[15px] font-medium text-ink"
          >
            {child.name}
            <button
              type="button"
              aria-label={`${child.name} 명단에서 빼기`}
              onClick={() => void remove(child)}
              className="inline-flex h-10 w-10 items-center justify-center rounded-full text-ink-soft hover:bg-shell focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                aria-hidden="true"
              >
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-2">
        <ErrorLine>{error}</ErrorLine>
      </div>
    </>
  );
}

/** 등록된 반이 없을 때(빈 상태). 마지막 확인에서 반을 등록하러 간다. */
function NoClass({ onBack }: { onBack: () => void }) {
  return (
    <OnboardingLayout
      stage={3}
      say={{ title: "넣을 반이 없어요", body: "마지막 확인에서 반을 먼저 등록해요." }}
      progress={1}
      footer={<CtaButton onClick={onBack}>마지막 확인으로</CtaButton>}
    >
      <p role="status" className="text-[15px] text-ink-soft">
        넣을 수 있는 반이 없어요.
      </p>
    </OnboardingLayout>
  );
}
