"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import AgeSelection from "./AgeSelection";
import OnboardingLayout, { type PostySay } from "./OnboardingLayout";
import {
  Cascade,
  CtaButton,
  ErrorLine,
  LineField,
  LoadingLine,
  Question,
  onEnter,
} from "./FlowParts";
import { useOnboardingData } from "./useOnboardingData";
import { saveClassSettings } from "@/lib/onboarding/settings";
import { accountName } from "@/lib/auth/local-account";
import { isAlreadyExists } from "@/lib/api/client";
import { syncClass, rememberConsent } from "@/lib/api/onboarding";
import { childrenPathAfterAdd, isCompleteClass } from "@/lib/onboarding/flow";
import {
  createEmptyClassroom,
  selectedAgesFor,
  type AgeGroup,
  type ClassroomEntry,
  type SelectedAge,
} from "@/lib/onboarding/types";

const NAME_TAKEN = "같은 이름의 반이 이미 있어요";
const TITLES = [
  "맡고 계신 반 이름을\n알려주세요",
  "몇 살 반인가요?",
  "담임 선생님 성함은요?",
  "아이 이름을 받기 전에\n확인할게요",
];
/** 오른쪽 칸 포스티의 말(데스크톱). */
const SAY: PostySay[] = [
  { title: "원 정보는 끝났어요!", body: "이제 맡고 계신 반을 등록해요." },
  { title: "좋아요!", body: "반 정보는 세 개 남았어요." },
  { title: "잘하고 있어요!", body: "반 정보는 두 개 남았어요." },
  { title: "거의 다 왔어요!", body: "이것만 확인하면 반 정보는 끝이에요." },
];
const HINTS = [
  undefined,
  "여러 연령이 함께 지내면 모두 골라주세요.",
  "가입할 때 적은 이름을 넣어 두었어요. 다르면 고쳐주세요.",
  "동의서는 원에서 보호자에게 받아요. 쌤플은 받았는지만 확인해요.",
];

function uid(prefix: string) {
  try {
    return `${prefix}-${crypto.randomUUID()}`;
  } catch {
    return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
}

/** 연령이 3·5 뿐이면 사이의 4세도 한 반이다 (ADR-038 · screen-spec S2). */
const skipsFour = (ages: SelectedAge[]) =>
  ages.includes(3) && ages.includes(5) && !ages.includes(4);

/**
 * /onboarding/classes — 한 번에 반 하나를 등록한다.
 * 반 이름 → 연령 → 담임 → 동의, 마지막 「다음」이 곧 등록이다. 확인 창은 없다.
 */
export default function ClassFlow() {
  const router = useRouter();
  const data = useOnboardingData("classes");
  const { settings, error, setError, params } = data;
  const adding = params.get("add") === "1";
  const [q, setQ] = useState(0);
  // 담임 이름은 가입할 때 적은 이름을 먼저 넣어 둔다.
  const [draft, setDraft] = useState<ClassroomEntry>(() => ({
    ...createEmptyClassroom(uid("class")),
    teacherName: accountName() ?? "",
  }));
  const [nameError, setNameError] = useState("");
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);

  const ages = selectedAgesFor(draft);
  const valid = [
    draft.className.trim() !== "",
    ages.length > 0,
    draft.teacherName.trim() !== "",
    true,
  ];

  function patch(p: Partial<ClassroomEntry>) {
    setDraft((d) => ({ ...d, ...p }));
  }

  async function register() {
    if (saving.current) return;
    saving.current = true;
    setBusy(true);
    setError("");
    setNameError("");
    try {
      const entry: ClassroomEntry = {
        ...draft,
        className: draft.className.trim(),
        teacherName: draft.teacherName.trim(),
        childrenSkipped: draft.guardianConsent ? false : draft.childrenSkipped,
      };
      // 옛 흐름에서 남은 빈 반은 버리고 새 반을 뒤에 붙인다.
      const next = { ...settings, classes: [...settings.classes.filter(isCompleteClass), entry] };
      await syncClass(next, entry);
      rememberConsent(next.classes);
      if (!saveClassSettings(next)) throw new Error("설정을 저장하지 못했어요.");
      router.push(adding ? childrenPathAfterAdd(entry.id) : "/onboarding/children");
    } catch (e) {
      if (isAlreadyExists(e)) {
        setNameError(NAME_TAKEN);
        setQ(0);
      } else setError(e instanceof Error ? e.message : "반을 등록하지 못했어요.");
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }

  function advance() {
    if (busy || !valid[q]) return;
    if (q < 3) setQ(q + 1);
    else void register();
  }

  function back() {
    setError("");
    if (q > 0) setQ(q - 1);
    else router.push(adding ? "/onboarding/review" : "/onboarding/center");
  }

  if (!data.ready) return <LoadingLine />;

  const fields = [
    <LineField
      key="name"
      id="className"
      label="반 이름"
      active={q === 0}
      value={draft.className}
      autoFocus={q === 0}
      placeholder="예: 쌤플반"
      error={nameError}
      onChange={(e) => {
        patch({ className: e.target.value });
        setNameError("");
      }}
      onKeyDown={(e) => onEnter(e, advance)}
    />,
    <div key="age">
      <AgeSelection
        active={q === 1}
        value={ages}
        onChange={(selectedAges) =>
          patch({
            selectedAges,
            ageGroup: selectedAges.length === 1 ? (String(selectedAges[0]) as AgeGroup) : "",
          })
        }
      />
      {skipsFour(ages) && (
        <p role="status" className="-mt-4 mb-7 text-[14px] font-medium text-primary-ink">
          만 4세도 함께 포함돼요
        </p>
      )}
    </div>,
    <LineField
      key="teacher"
      id="teacherName"
      label="담임 이름"
      active={q === 2}
      value={draft.teacherName}
      autoFocus={q === 2}
      placeholder="예: 김하늘"
      onChange={(e) => patch({ teacherName: e.target.value })}
      onKeyDown={(e) => onEnter(e, advance)}
    />,
    <div key="consent" className="mb-7">
      <ConsentBox
        checked={draft.guardianConsent}
        onChange={(guardianConsent) => patch({ guardianConsent })}
      />
      <p className="mx-0.5 mt-3 text-[14px] leading-[1.6] text-ink-soft">
        {draft.guardianConsent
          ? "다음 단계에서 이 반 아이 이름을 넣을 수 있어요."
          : "체크하지 않아도 반은 등록돼요. 동의를 받으면 마지막 확인 화면에서 체크하고 아이 이름을 넣을 수 있어요."}
      </p>
    </div>,
  ];
  // 지금 질문이 맨 위, 이미 답한 칸은 그 아래에 최근 것부터 쌓는다.
  const order = [q, ...Array.from({ length: q }, (_, i) => q - 1 - i)];

  return (
    <OnboardingLayout
      stage={2}
      say={SAY[q]}
      progress={1 / 3 + ((q + 1) / 4) * (1 / 3)}
      onBack={back}
      footer={
        <CtaButton disabled={busy || !valid[q]} onClick={advance}>
          {busy ? "등록 중이에요" : "다음"}
        </CtaButton>
      }
    >
      <Question title={TITLES[q]} hint={HINTS[q]} focus={q === 1 || q === 3} />
      <Cascade fields={fields} order={order} />
      <ErrorLine>{error}</ErrorLine>
    </OnboardingLayout>
  );
}

/** 동의 확인 — 시안 A 의 큰 카드. 문장 두 줄은 바꾸지 않는다(screen-spec S2 「이 줄을 빼지 않는다」). */
export function ConsentBox({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label
      className={`flex cursor-pointer items-start gap-3.5 squircle [--r:16px] border-[1.5px] p-[18px] ${checked ? "border-primary bg-primary-tint" : "border-line bg-ivory"}`}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-[22px] w-[22px] flex-none accent-[var(--pg-primary)]"
      />
      <span className="flex flex-col gap-1.5">
        <span className="text-[16px] font-bold leading-[1.5] text-ink">
          이 반 모든 아동의 법정대리인 동의를 받았습니다.
        </span>
        <span className="text-[14px] leading-[1.5] text-ink-soft">
          동의 확인 전에는 아동 이름을 입력하지 않아요.
        </span>
      </span>
    </label>
  );
}
