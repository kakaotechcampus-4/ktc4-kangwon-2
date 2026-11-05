"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import OnboardingLayout, { type PostySay } from "./OnboardingLayout";
import RegionSheet from "./RegionSheet";
import {
  Cascade,
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
import { syncCenter } from "@/lib/api/onboarding";
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

/** /onboarding/center — 원 이름 · 원장 · 지역, 질문 셋. (초대 코드로 들어오는 길은 우선 뺐다.) */
export default function CenterFlow() {
  const router = useRouter();
  const data = useOnboardingData("center");
  const { settings, edit, error, setError } = data;
  const startCentered = centerSet(settings);
  // 이미 등록한 원이면 답이 다 찬 채로 마지막 질문에서 시작한다.
  const [q, setQ] = useState(() => (startCentered ? 2 : 0));
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
    setQ(q - 1);
  }

  if (!data.ready) return <LoadingLine />;

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
  const order = [q, ...Array.from({ length: q }, (_, i) => q - 1 - i)];

  return (
    <OnboardingLayout
      stage={1}
      say={SAY[q]}
      progress={((q + 1) / 3) * (1 / 3)}
      onBack={q > 0 ? back : undefined}
      footer={
        <CtaButton disabled={busy || !valid[q]} onClick={advance}>
          {busy ? "저장 중이에요" : "다음"}
        </CtaButton>
      }
    >
      <Question title={TITLES[q]} hint={HINTS[q]} focus={q === 2} />
      <Cascade fields={fields} order={order} />
      <ErrorLine>{error}</ErrorLine>
      {sheet && <RegionSheet onPick={pickRegion} onClose={() => setSheet(false)} />}
    </OnboardingLayout>
  );
}
