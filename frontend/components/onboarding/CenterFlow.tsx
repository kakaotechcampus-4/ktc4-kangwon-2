"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Posty } from "@/components/app/Posty";
import OnboardingLayout, { type PostySay } from "./OnboardingLayout";
import RegionSheet from "./RegionSheet";
import {
  Chevron,
  CtaButton,
  ErrorLine,
  FieldLabel,
  LineField,
  LoadingLine,
  PickButton,
  Question,
  onEnter,
} from "./FlowParts";
import { useOnboardingData } from "./useOnboardingData";
import { saveClassSettings } from "@/lib/onboarding/settings";
import { districtsFor } from "@/lib/onboarding/regions";
import { syncCenter, joinCenterByCode } from "@/lib/api/onboarding";
import type { ClassSettings } from "@/lib/onboarding/types";

const NEXT_PATH = "/onboarding/classes";
const TITLES = ["어린이집 이름을\n알려주세요", "원장님 성함은요?", "어느 지역에 있나요?"];
/** 오른쪽 칸 포스티의 말(데스크톱). 질문마다 얼마나 남았는지 알려 준다. */
const SAY: PostySay[] = [
  { title: "시작해 볼까요?", body: "원 정보는 세 가지만 물어봐요." },
  { title: "좋아요!", body: "원 정보는 두 개 남았어요." },
  { title: "거의 다 왔어요!", body: "지역만 고르면 원 정보는 끝이에요." },
];
const HINTS = [
  "계획안 작성에 활용할 기본 정보예요.",
  undefined,
  "시·도를 고르면 그 안의 시·군·구가 이어서 나와요.",
];

const regionSet = (s: ClassSettings) => districtsFor(s.regionProvince).includes(s.regionDistrict);
const centerSet = (s: ClassSettings) =>
  s.orgName.trim() !== "" && s.directorName.trim() !== "" && regionSet(s);

type Mode = "fork" | "invite" | "new";

/** /onboarding/center — 처음이면 갈림길, 새 등록이면 질문 셋, 초대 코드면 코드 하나. */
export default function CenterFlow() {
  const router = useRouter();
  const data = useOnboardingData("center");
  const { settings, edit, error, setError } = data;
  const startCentered = centerSet(settings);
  const [mode, setMode] = useState<Mode>(() => (startCentered ? "new" : "fork"));
  // 이미 등록한 원이면 답이 다 찬 채로 마지막 질문에서 시작한다.
  const [q, setQ] = useState(() => (startCentered ? 2 : 0));
  const [code, setCode] = useState("");
  const [sheet, setSheet] = useState(false);
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);

  async function run(job: () => Promise<void>, failure: string) {
    if (saving.current) return;
    saving.current = true;
    setBusy(true);
    setError("");
    try {
      await job();
    } catch (e) {
      setError(e instanceof Error ? e.message : failure);
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }

  const valid = [
    settings.orgName.trim() !== "",
    settings.directorName.trim() !== "",
    regionSet(settings),
  ];

  function submitNew() {
    void run(async () => {
      const next = {
        ...settings,
        orgName: settings.orgName.trim(),
        directorName: settings.directorName.trim(),
      };
      await syncCenter(next);
      if (!saveClassSettings(next)) throw new Error("설정을 저장하지 못했어요.");
      router.push(NEXT_PATH);
    }, "저장하지 못했어요.");
  }

  function submitInvite() {
    void run(async () => {
      const next = await joinCenterByCode(settings, code.trim());
      if (!saveClassSettings(next)) throw new Error("설정을 저장하지 못했어요.");
      router.push(NEXT_PATH);
    }, "초대 코드로 참여하지 못했어요.");
  }

  function advance() {
    if (busy || !valid[q]) return;
    if (q < 2) setQ(q + 1);
    else submitNew();
  }

  function pickRegion(province: string, district: string) {
    edit({ regionProvince: province, regionDistrict: district });
    setSheet(false);
  }

  function back() {
    setError("");
    if (q > 0) setQ(q - 1);
    else setMode("fork");
  }

  if (!data.ready) return <LoadingLine />;

  if (mode === "fork")
    return (
      <OnboardingLayout
        stage={1}
        say={{ title: "반가워요!", body: "원 정보 · 반 · 아이 명단 순서로 채워요." }}
        progress={1 / 3}
      >
        <div className="flex flex-col gap-[22px] pt-3">
          <Posty
            pose="wave"
            tone="note"
            face="base"
            size={84}
            tape
            wave
            label="포스티가 손을 흔들어요"
            // 768px 부터는 오른쪽 칸 포스티가 인사한다 — 한 화면에 포스티는 하나.
            className="md:hidden"
          />
          <h1
            className="font-display text-[31px] font-bold leading-[1.4] text-ink sm:text-[36px]"
            style={{ wordBreak: "keep-all" }}
          >
            선생님, 반가워요!
            <br />
            우리 원은 쌤플이 처음인가요?
          </h1>
          <p className="text-[15px] leading-[1.6] text-ink-soft">
            원 정보와 반, 아이 이름만 알려주시면 바로 시작할 수 있어요.
          </p>
          <div className="mt-1.5 flex flex-col gap-3">
            <ForkButton
              onClick={() => setMode("new")}
              title="처음 등록해요"
              sub="원 정보부터 차례로 채워요"
            />
            <ForkButton
              onClick={() => setMode("invite")}
              title="초대 코드를 받았어요"
              sub="같은 원 선생님이 먼저 등록했어요"
            />
          </div>
        </div>
      </OnboardingLayout>
    );

  if (mode === "invite")
    return (
      <OnboardingLayout
        stage={1}
        say={{ title: "코드 하나면 돼요", body: "원 정보는 같은 원 선생님 것을 그대로 써요." }}
        progress={1 / 3}
        onBack={() => setMode("fork")}
        footer={
          <CtaButton disabled={busy || code.trim() === ""} onClick={submitInvite}>
            {busy ? "확인 중이에요" : "다음"}
          </CtaButton>
        }
      >
        <Question
          title={"받은 초대 코드를\n입력해주세요"}
          hint="같은 원 선생님이 설정 화면에서 만든 코드예요. 한 번만 쓸 수 있고 7일 뒤에 사라져요."
        />
        <LineField
          id="inviteCode"
          label="초대 코드"
          active
          value={code}
          autoFocus
          spellCheck={false}
          placeholder="예: ABCD2345EF"
          style={{ letterSpacing: "0.12em" }}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => onEnter(e, () => code.trim() && !busy && submitInvite())}
        />
        <ErrorLine>{error}</ErrorLine>
      </OnboardingLayout>
    );

  const regionText = valid[2] ? `${settings.regionProvince} ${settings.regionDistrict}` : "";
  const fields = [
    <LineField
      key="org"
      id="orgName"
      label="원 이름"
      active={q === 0}
      value={settings.orgName}
      autoFocus={q === 0}
      placeholder="예: 햇살어린이집"
      onChange={(e) => edit({ orgName: e.target.value })}
      onKeyDown={(e) => onEnter(e, advance)}
    />,
    <LineField
      key="director"
      id="directorName"
      label="원장 이름"
      active={q === 1}
      value={settings.directorName}
      autoFocus={q === 1}
      placeholder="예: 박미소"
      onChange={(e) => edit({ directorName: e.target.value })}
      onKeyDown={(e) => onEnter(e, advance)}
    />,
    <div key="region" className="mb-7 flex flex-col gap-1.5">
      <FieldLabel htmlFor="region">지역</FieldLabel>
      <PickButton
        id="region"
        active={q === 2}
        value={regionText}
        placeholder="시·도 선택"
        onClick={() => setSheet(true)}
      />
    </div>,
  ];
  // 지금 질문이 맨 위, 이미 답한 칸은 그 아래에 최근 것부터 쌓는다.
  const answered = fields.slice(0, q).reverse();

  return (
    <OnboardingLayout
      stage={1}
      say={SAY[q]}
      progress={((q + 1) / 3) * (1 / 3)}
      onBack={q > 0 || !startCentered ? back : undefined}
      footer={
        <CtaButton disabled={busy || !valid[q]} onClick={advance}>
          {busy ? "저장 중이에요" : "다음"}
        </CtaButton>
      }
    >
      <Question title={TITLES[q]} hint={HINTS[q]} focus={q === 2} />
      {fields[q]}
      {answered}
      <ErrorLine>{error}</ErrorLine>
      {sheet && <RegionSheet onPick={pickRegion} onClose={() => setSheet(false)} />}
    </OnboardingLayout>
  );
}

function ForkButton({ title, sub, onClick }: { title: string; sub: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-h-[76px] w-full items-center gap-3 rounded-2xl border-[1.5px] border-line bg-paper px-[18px] py-4 text-left text-ink transition-colors hover:border-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
    >
      <span className="flex flex-1 flex-col gap-1">
        <span className="text-[17px] font-bold">{title}</span>
        <span className="text-[14px] text-ink-soft">{sub}</span>
      </span>
      <Chevron size={20} />
    </button>
  );
}
