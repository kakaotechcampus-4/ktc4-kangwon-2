"use client";

import { useState } from "react";
import OnboardingLayout from "./OnboardingLayout";
import RegionSheet from "./RegionSheet";
import {
  CtaButton,
  ErrorLine,
  FieldLabel,
  LineField,
  PickButton,
  Question,
  onEnter,
} from "./FlowParts";
import { syncCenter } from "@/lib/api/onboarding";
import type { ClassSettings } from "@/lib/onboarding/types";

export type CenterField = "org" | "director" | "region";

const COPY = {
  org: { title: "어린이집 이름을\n고쳐주세요", label: "원 이름" },
  director: { title: "원장님 성함을\n고쳐주세요", label: "원장 이름" },
  region: { title: "어느 지역에 있나요?", label: "지역" },
} as const;

/** 마지막 확인에서 원 정보 한 칸만 고친다. 저장하면 서버(원 수정)와 브라우저에 같이 쓴다. */
export default function ReviewCenterEdit({
  field,
  settings,
  onSaved,
  onCancel,
}: {
  field: CenterField;
  settings: ClassSettings;
  onSaved: (next: ClassSettings) => boolean;
  onCancel: () => void;
}) {
  const [org, setOrg] = useState(settings.orgName);
  const [director, setDirector] = useState(settings.directorName);
  const [sheet, setSheet] = useState(field === "region");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save(patch: Partial<ClassSettings>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const next = { ...settings, ...patch };
      await syncCenter(next);
      if (!onSaved(next)) throw new Error("설정을 저장하지 못했어요.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장하지 못했어요.");
    } finally {
      setBusy(false);
    }
  }

  const value = field === "org" ? org : director;
  const submit = () => {
    if (value.trim() === "") return;
    void save(field === "org" ? { orgName: org.trim() } : { directorName: director.trim() });
  };
  const region = `${settings.regionProvince} ${settings.regionDistrict}`.trim();

  return (
    <OnboardingLayout
      stage={4}
      say={{ title: "고쳐 볼까요?", body: "고친 내용은 바로 저장돼요." }}
      progress={1}
      onBack={onCancel}
      footer={
        field !== "region" && (
          <CtaButton disabled={busy || value.trim() === ""} onClick={submit}>
            {busy ? "저장 중이에요" : "저장"}
          </CtaButton>
        )
      }
    >
      <Question title={COPY[field].title} />
      {field !== "region" && (
        <LineField
          id="centerField"
          label={COPY[field].label}
          active
          value={value}
          autoFocus
          onChange={(e) => (field === "org" ? setOrg(e.target.value) : setDirector(e.target.value))}
          onKeyDown={(e) => onEnter(e, submit)}
        />
      )}
      {field === "region" && (
        <div className="mb-7 flex flex-col gap-1.5">
          <FieldLabel htmlFor="region">지역</FieldLabel>
          <PickButton
            id="region"
            active
            value={region}
            placeholder="시·도 선택"
            onClick={() => setSheet(true)}
          />
        </div>
      )}
      <ErrorLine>{error}</ErrorLine>
      {sheet && (
        <RegionSheet
          onClose={() => setSheet(false)}
          onPick={(regionProvince, regionDistrict) => {
            setSheet(false);
            void save({ regionProvince, regionDistrict });
          }}
        />
      )}
    </OnboardingLayout>
  );
}
