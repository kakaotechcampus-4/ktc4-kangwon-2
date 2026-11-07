"use client";

import { useEffect, useRef, useState } from "react";
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
  TextAction,
  onEnter,
} from "./FlowParts";
import { useOnboardingData } from "./useOnboardingData";
import { saveClassSettings } from "@/lib/onboarding/settings";
import { districtsFor } from "@/lib/onboarding/regions";
import { chooseCenter } from "@/lib/api/onboarding";
import { searchDaycares } from "@/lib/api/centers";
import type { Daycare } from "@/lib/api/types";
import type { ClassSettings } from "@/lib/onboarding/types";

const NEXT_PATH = "/onboarding/classes";

/**
 * 원 정보 세 질문 (ADR-068). 지역을 먼저 고르고, 그 지역 정부 어린이집 목록에서 이름을 찾는다.
 *
 * - `region` 지역 → `find` 어린이집 찾기
 * - 쌤플을 이미 쓰는 원을 고르면 `join` — 원장 이름을 묻지 않고 그 원으로 들어간다(승인 없음)
 * - 처음 쓰는 원이면 `director` 원장 이름
 * - 목록에 없으면 `manual` 직접 적기 → `director`. 직접 적은 원은 다른 선생님이 찾을 수 없다
 */
type Step = "region" | "find" | "manual" | "director" | "join";
const PLACE: Record<Step, number> = { region: 0, find: 1, manual: 1, director: 2, join: 2 };
const TITLES: Record<Step, string> = {
  region: "어느 지역\n어린이집이에요?",
  find: "어린이집 이름을\n찾아 주세요",
  manual: "어린이집 이름을\n직접 적어 주세요",
  director: "원장님 성함은요?",
  join: "같은 원 선생님들과\n함께 써요",
};
const HINTS: Partial<Record<Step, string>> = {
  region: "시·도를 고르면 시·군·구가 이어서 나와요.",
  manual: "이번 달에 새로 문을 연 원은 목록에 아직 없을 수 있어요.",
};
/** 오른쪽 칸 포스티의 말(데스크톱). */
const SAY: Record<Step, PostySay> = {
  region: { title: "시작해 볼까요?", body: "지역을 고르면 그 지역 어린이집을 찾아 드려요." },
  find: { title: "좋아요!", body: "목록에서 우리 어린이집을 골라 주세요." },
  manual: { title: "괜찮아요", body: "직접 적은 원은 다른 선생님이 찾을 수 없어요." },
  director: {
    title: "거의 다 왔어요!",
    body: "쌤플을 처음 쓰는 원이에요. 원장님 성함만 적어 주세요.",
  },
  join: { title: "거의 다 왔어요!", body: "다음은 선생님 반을 만들어요." },
};

const regionSet = (s: ClassSettings) => districtsFor(s.regionProvince).includes(s.regionDistrict);
const centerSet = (s: ClassSettings) =>
  s.orgName.trim() !== "" && s.directorName.trim() !== "" && regionSet(s);
/** 「강원특별자치도 춘천시 영서로 …」 → 「영서로 …」. 지역은 이미 골랐다. */
const street = (d: Daycare, s: ClassSettings) =>
  d.address.replace(`${s.regionProvince} ${s.regionDistrict}`, "").trim() || d.address;

/** /onboarding/center — 지역 · 어린이집 · (처음 쓰는 원이면) 원장. */
export default function CenterFlow() {
  const router = useRouter();
  const data = useOnboardingData("center");
  const { settings, edit, error, setError } = data;
  // 이미 등록한 원이면 답이 다 찬 채로 마지막 질문에서 시작한다.
  const [step, setStep] = useState<Step>(() => (centerSet(settings) ? "director" : "region"));
  const [sheet, setSheet] = useState(false);
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<{ key: string; items: Daycare[] } | null>(null);
  const [picked, setPicked] = useState<Daycare | null>(null);
  const saving = useRef(false);
  const searchKey = `${settings.regionProvince}|${settings.regionDistrict}|${query.trim()}`;

  // 고른 지역에서 이름을 찾는다. 칠 때마다 부르지 않고 잠깐 멈추면 부른다.
  useEffect(() => {
    if (step !== "find" || !regionSet(settings)) return;
    let live = true;
    const timer = window.setTimeout(() => {
      searchDaycares(settings.regionProvince, settings.regionDistrict, query.trim())
        .then((items) => live && setFound({ key: searchKey, items }))
        .catch(() => live && setFound({ key: searchKey, items: [] }));
    }, 250);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [step, settings, query, searchKey]);

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

  /** 서버에 원을 만들거나 그 원으로 들어가고, 서버 값으로 브라우저 사본을 맞춘다. */
  function submit() {
    void run(async () => {
      const next = {
        ...settings,
        orgName: settings.orgName.trim(),
        directorName: settings.directorName.trim(),
      };
      const center = await chooseCenter(next);
      const saved = {
        ...next,
        orgName: center.name,
        directorName: center.director_name,
        regionProvince: center.region_sido,
        regionDistrict: center.region_sigungu,
        registryKey: center.registry_key ?? "",
      };
      if (!saveClassSettings(saved)) throw new Error("설정을 저장하지 못했어요.");
      router.push(NEXT_PATH);
    }, "저장하지 못했어요.");
  }

  function pick(d: Daycare) {
    setPicked(d);
    edit({ orgName: d.name, registryKey: d.key });
    setStep(d.teacher_count > 0 ? "join" : "director");
  }

  function manual() {
    setPicked(null);
    edit({ orgName: "", registryKey: "" });
    setStep("manual");
  }

  const valid: Record<Step, boolean> = {
    region: regionSet(settings),
    find: false, // 목록에서 고르면 바로 넘어간다
    manual: settings.orgName.trim() !== "",
    director: settings.directorName.trim() !== "",
    join: true,
  };

  function advance() {
    if (busy || !valid[step]) return;
    if (step === "region") setStep("find");
    else if (step === "manual") setStep("director");
    else submit();
  }

  function back() {
    setError("");
    if (step === "find") setStep("region");
    else if (step === "manual" || step === "join") setStep("find");
    else if (step === "director") setStep(settings.registryKey ? "find" : "manual");
  }

  function pickRegion(province: string, district: string) {
    edit({ regionProvince: province, regionDistrict: district, orgName: "", registryKey: "" });
    setFound(null);
    setQuery("");
    setSheet(false);
  }

  if (!data.ready) return <LoadingLine />;

  const place = PLACE[step];
  const regionText = regionSet(settings)
    ? `${settings.regionProvince} ${settings.regionDistrict}`
    : "";
  const results = found?.key === searchKey ? found.items : null;
  const fields = [
    <div key="region" className="mb-7 flex flex-col gap-1.5">
      <FieldLabel htmlFor="region">지역</FieldLabel>
      <PickButton
        id="region"
        active={step === "region"}
        value={regionText}
        placeholder="시·도 선택"
        onClick={() => setSheet(true)}
      />
    </div>,
    step === "find" ? (
      <FindField
        key="org"
        query={query}
        onQuery={setQuery}
        results={results}
        settings={settings}
        onPick={pick}
      />
    ) : (
      <LineField
        key="org"
        id="orgName"
        label="어린이집 이름"
        active={step === "manual"}
        readOnly={step !== "manual"}
        value={settings.orgName}
        autoFocus={step === "manual"}
        placeholder="예: 쌤플어린이집"
        onChange={(e) => edit({ orgName: e.target.value })}
        onKeyDown={(e) => onEnter(e, advance)}
      />
    ),
    step === "join" ? (
      <JoinCard key="director" daycare={picked} settings={settings} />
    ) : (
      <LineField
        key="director"
        id="directorName"
        label="원장 이름"
        active={step === "director"}
        value={settings.directorName}
        autoFocus={step === "director"}
        placeholder="예: 포스티"
        onChange={(e) => edit({ directorName: e.target.value })}
        onKeyDown={(e) => onEnter(e, advance)}
      />
    ),
  ];
  // 지금 질문이 맨 위, 이미 답한 칸은 그 아래에 최근 것부터 쌓는다.
  // 찾기만은 예외 — 결과 쪽지가 길어 지역 칸까지 쌓으면 칠판이 화면 밖으로 길어진다. 지역은 힌트 줄에 적는다.
  const order =
    step === "find" ? [place] : [place, ...Array.from({ length: place }, (_, i) => place - 1 - i)];
  const hint = step === "find" ? `${regionText}에서 찾아요. 이름 일부만 쳐도 돼요.` : HINTS[step];

  return (
    <OnboardingLayout
      stage={1}
      say={SAY[step]}
      progress={((place + 1) / 3) * (1 / 3)}
      onBack={step !== "region" ? back : undefined}
      footer={
        <Footer step={step} busy={busy} valid={valid[step]} onNext={advance} onManual={manual} />
      }
    >
      <Question title={TITLES[step]} hint={hint} focus={step === "region"} />
      <Cascade fields={fields} order={order} />
      <ErrorLine>{error}</ErrorLine>
      {sheet && <RegionSheet onPick={pickRegion} onClose={() => setSheet(false)} />}
    </OnboardingLayout>
  );
}

/** 찾기 칸 — 이름을 치는 밑줄 칸과 그 아래 결과 쪽지. */
function FindField({
  query: q,
  onQuery,
  results: items,
  settings: s,
  onPick,
}: {
  query: string;
  onQuery: (q: string) => void;
  results: Daycare[] | null;
  settings: ClassSettings;
  onPick: (d: Daycare) => void;
}) {
  return (
    <div className="mb-7">
      <LineField
        id="daycareName"
        label="어린이집 이름"
        active
        autoFocus
        value={q}
        placeholder="예: 햇살"
        onChange={(e) => onQuery(e.target.value)}
      />
      <DaycareResults items={items} settings={s} onPick={onPick} />
      <p className="mt-3 text-[13px] text-board-ink-soft">
        어린이집 목록: 어린이집정보공개포털 (매달 새로 받아요)
      </p>
    </div>
  );
}

/** 찾은 어린이집 — 칠판 위에 붙인 흰 쪽지. 쌤플을 쓰는 원이면 선생님 수를 단다(이름은 안 보인다). */
function DaycareResults({
  items,
  settings,
  onPick,
}: {
  items: Daycare[] | null;
  settings: ClassSettings;
  onPick: (d: Daycare) => void;
}) {
  if (items === null)
    return <p className="-mt-4 text-[15px] text-board-ink-soft">찾는 중이에요…</p>;
  if (!items.length)
    return (
      <p className="-mt-4 text-[15px] text-board-ink-soft">
        이 지역에 그 이름의 어린이집이 없어요. 「목록에 없어요」로 직접 적어 주세요.
      </p>
    );
  return (
    <ul
      aria-label="찾은 어린이집"
      className="paper -mt-3 grid max-h-[232px] gap-2 overflow-y-auto pr-1"
    >
      {items.map((d) => (
        <li key={d.key}>
          <button
            type="button"
            onClick={() => onPick(d)}
            className="squircle [--r:12px] grid w-full grid-cols-[1fr_auto] items-center gap-3 bg-paper px-4 py-3 text-left text-ink shadow-[2px_3px_0_rgba(0,0,0,0.25)] hover:bg-ivory"
          >
            <span className="min-w-0">
              <b className="text-[15.5px]">{d.name}</b>
              {d.teacher_count > 0 && (
                <span className="ml-1.5 inline-block rounded-full bg-sage-tint px-2 align-[2px] text-[11.5px] font-bold text-sage-ink">
                  쌤플 선생님 {d.teacher_count}명
                </span>
              )}
              {d.status === "휴지" && (
                <span className="ml-1.5 inline-block rounded-full bg-cream px-2 align-[2px] text-[11.5px] font-bold text-ink-soft">
                  휴지
                </span>
              )}
              <small className="block truncate text-[12.5px] text-ink-soft">
                {d.kind} · {street(d, settings)}
              </small>
            </span>
            <span className="squircle [--r:8px] whitespace-nowrap border-[1.5px] border-primary-deep px-3 py-1.5 text-[13px] font-bold text-primary-deep">
              이 원이에요
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/** 쌤플을 이미 쓰는 원을 골랐을 때 — 들어가면 무엇이 보이는지 먼저 알린다. */
function JoinCard({ daycare, settings }: { daycare: Daycare | null; settings: ClassSettings }) {
  return (
    <div className="paper squircle [--r:14px] mb-7 bg-paper px-5 py-4 text-ink shadow-[2px_3px_0_rgba(0,0,0,0.25)]">
      <b className="block font-display text-[24px] leading-tight">{settings.orgName}</b>
      <small className="mb-2 block text-[13px] text-ink-soft">
        {settings.regionProvince} {settings.regionDistrict}
        {daycare ? ` · 쌤플 선생님 ${daycare.teacher_count}명` : ""}
      </small>
      <ul className="list-disc space-y-0.5 pl-5 text-[14px]">
        <li>
          홈 · 우리 반에는 <b>선생님이 만든 반만</b> 보여요.
        </li>
        <li>
          다른 반 문서는 문서 보관함에서 <b>열람 요청</b>으로 봐요.
        </li>
        <li>원 정보는 바꿀 수 없어요.</li>
      </ul>
    </div>
  );
}

function Footer({
  step,
  busy,
  valid,
  onNext,
  onManual,
}: {
  step: Step;
  busy: boolean;
  valid: boolean;
  onNext: () => void;
  onManual: () => void;
}) {
  if (step === "find") return <TextAction onClick={onManual}>목록에 없어요 · 직접 적기</TextAction>;
  return (
    <CtaButton disabled={busy || !valid} onClick={onNext}>
      {busy ? "저장 중이에요" : step === "join" ? "이 원으로 시작하기" : "다음"}
    </CtaButton>
  );
}
