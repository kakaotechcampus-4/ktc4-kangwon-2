"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import OnboardingLayout, { type PostySay } from "./OnboardingLayout";
import RegionSheet from "./RegionSheet";
import {
  AnsweredList,
  Cascade,
  CtaButton,
  ErrorLine,
  FieldHint,
  FieldLabel,
  LineField,
  LoadingLine,
  PickButton,
  Question,
  onEnter,
  type Answered,
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

/**
 * 찾기 결과 상자 높이. 한 줄은 66px(min-h) · 줄 사이 4px.
 * 3줄(198 + 12) + 4번째 줄 윗부분 44px + 안쪽 여백 12 + 점선 4 = 270px.
 * 4곳부터는 4번째 줄이 이름과 번호까지 보이다 상자 바닥에 잘려, 아래에 더 있다는 게 보인다.
 * (26px 만 보이면 이름 윗부분만 보이고 번호는 안 보여 어색했다.) 줄 높이를 바꾸면 이 높이도 같이 바꾼다.
 */
const RESULT_BOX = "h-[270px]";

/** /onboarding/center — 지역 · 어린이집 · (처음 쓰는 원이면) 원장. */
export default function CenterFlow() {
  const router = useRouter();
  const data = useOnboardingData("center");
  const { settings, edit, error, setError } = data;
  // 이미 등록한 원이면 답이 다 찬 채로 마지막 질문에서 시작한다.
  const [step, setStep] = useState<Step>(() => (centerSet(settings) ? "director" : "region"));
  // 그렇게 들어온 원은 서버에 이미 있어 지역 · 이름을 고쳐도 chooseCenter 가 서버 값을 돌려준다.
  // 고친 것처럼 보이고 저장되지 않으니 요약 줄에 「고치기」를 두지 않는다.
  const [centerLocked] = useState(() => centerSet(settings));
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

  /** 요약 줄의 「고치기」 — 그 질문으로 돌아간다. */
  function revisit(target: Step) {
    setError("");
    setStep(target);
  }

  if (!data.ready) return <LoadingLine />;

  const place = PLACE[step];
  const regionText = regionSet(settings)
    ? `${settings.regionProvince} ${settings.regionDistrict}`
    : "";
  const results = found?.key === searchKey ? found.items : null;
  // 안내는 질문 제목 아래가 아니라 지금 칸 밑에 둔다(FieldHint).
  const hint = step === "find" ? `${regionText}에서 찾아요. 이름 일부만 쳐도 돼요.` : HINTS[step];
  const orgStep: Step = settings.registryKey ? "find" : "manual";
  const answered: Answered[] = [
    {
      label: "지역",
      value: regionText,
      onEdit: centerLocked ? undefined : () => revisit("region"),
    },
    {
      label: "어린이집 이름",
      value: settings.orgName,
      onEdit: centerLocked ? undefined : () => revisit(orgStep),
    },
  ]
    .slice(0, place)
    .reverse();

  function orgField() {
    if (step === "find")
      return (
        <FindField
          key="org"
          query={query}
          onQuery={setQuery}
          results={results}
          settings={settings}
          hint={hint}
          onPick={pick}
          onManual={manual}
        />
      );
    return (
      <LineField
        key="org"
        id="orgName"
        label="어린이집 이름"
        active={step === "manual"}
        readOnly={step !== "manual"}
        hint={step === "manual" ? hint : undefined}
        value={settings.orgName}
        autoFocus={step === "manual"}
        placeholder="예: 쌤플어린이집"
        onChange={(e) => edit({ orgName: e.target.value })}
        onKeyDown={(e) => onEnter(e, advance)}
      />
    );
  }

  function directorField() {
    if (step === "join") return <JoinCard key="director" daycare={picked} settings={settings} />;
    return (
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
    );
  }

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
      {step === "region" && hint && <FieldHint>{hint}</FieldHint>}
    </div>,
    orgField(),
    directorField(),
    <AnsweredList key="answered" items={answered} />,
  ];
  // 지금 질문이 맨 위, 그 아래에 앞에서 답한 요약(3번 칸).
  // 찾기만은 예외 — 결과 쪽지가 길어 요약까지 쌓으면 칠판이 화면 밖으로 길어진다. 지역은 안내 줄에 적는다.
  const order = step === "find" || place === 0 ? [place] : [place, 3];

  return (
    <OnboardingLayout
      stage={1}
      say={SAY[step]}
      progress={((place + 1) / 3) * (1 / 3)}
      onBack={step !== "region" ? back : undefined}
      // 찾기는 목록에서 고르면 바로 넘어가 주 버튼이 없다. 「직접 적기」는 목록 옆(FindField)에 있다.
      footer={
        step !== "find" && <Footer step={step} busy={busy} valid={valid[step]} onNext={advance} />
      }
    >
      <Question title={TITLES[step]} focus={step === "region"} />
      <Cascade fields={fields} order={order} />
      <ErrorLine>{error}</ErrorLine>
      {sheet && <RegionSheet onPick={pickRegion} onClose={() => setSheet(false)} />}
    </OnboardingLayout>
  );
}

/**
 * 찾기 칸 — 이름을 치는 밑줄 칸, 그 아래 점선 상자 안의 결과, 출처 줄.
 * 「직접 적기」는 목록을 다 훑은 눈이 닿는 출처 줄 오른쪽에 작게 두고, 못 찾았으면 상자 가운데 크게 둔다.
 */
function FindField({
  query: q,
  onQuery,
  results: items,
  settings: s,
  hint,
  onPick,
  onManual,
}: {
  query: string;
  onQuery: (q: string) => void;
  results: Daycare[] | null;
  settings: ClassSettings;
  hint?: string;
  onPick: (d: Daycare) => void;
  onManual: () => void;
}) {
  const empty = items !== null && items.length === 0;
  // 칠판 높이(760px)를 다른 화면과 같게 두려고 이 칸만 여백을 줄인다 — 질문 쪽으로 8px 당기고(-mt-2),
  // 안내와 상자 사이 4px(-mt-6), 출처 줄을 상자에 바짝(mt-1). 결과 상자 270px 를 지키려는 것이다.
  return (
    <div className="-mt-2">
      <LineField
        id="daycareName"
        label="어린이집 이름"
        active
        autoFocus
        hint={hint}
        value={q}
        placeholder="예: 햇살"
        onChange={(e) => onQuery(e.target.value)}
      />
      {/* 결과 자리는 높이를 고정한다 — 찾은 수에 따라 아래 출처 줄이 오르내리지 않게. 넘치면 안에서 스크롤.
          높이는 3줄 + 4번째 줄 머리(RESULT_BOX): 3곳이면 꽉 차 보이고, 4곳부터는 4번째 줄이 바닥에 걸친다. */}
      <div
        className={`-mt-6 ${RESULT_BOX} squircle [--r:16px] border-2 border-dashed border-line p-1.5`}
      >
        {empty ? (
          <NoDaycare query={q} district={s.regionDistrict} onManual={onManual} />
        ) : (
          <DaycareResults items={items} settings={s} onPick={onPick} />
        )}
      </div>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-x-4">
        <p className="text-[13px] text-board-ink-soft">어린이집 목록: 어린이집정보공개포털</p>
        {!empty && <ManualLink onClick={onManual} />}
      </div>
    </div>
  );
}

/** 출처 줄 오른쪽 「직접 적기」. 이름(「목록에 없어요 · 직접 적기」)은 e2e 가 찾는 그대로 둔다. */
function ManualLink({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      // 누르는 자리는 44px 로 두되(min-h-11) 위아래로 겹쳐(-my-3) 줄 높이는 글자만큼만 차지한다.
      className="-my-3 inline-flex min-h-11 items-center gap-1.5 px-1 text-[14.5px] font-semibold text-ink hover:text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
    >
      <span className="underline decoration-primary underline-offset-4">
        목록에 없어요 · 직접 적기
      </span>
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        className="text-primary"
      >
        <path d="M5 12h14M13 6l6 6-6 6" />
      </svg>
    </button>
  );
}

/** 받침이 있으면 「이」, 없으면 「가」(「숲」이 · 「숲속나라」가). 한글이 아니면 「가」. */
function iGa(word: string) {
  const code = word.charCodeAt(word.length - 1);
  const batchim = code >= 0xac00 && code <= 0xd7a3 && (code - 0xac00) % 28 !== 0;
  return batchim ? "이" : "가";
}

/** 찾은 원이 없을 때 — 결과 상자 가운데에 「직접 적기」를 크게. */
function NoDaycare({
  query,
  district,
  onManual,
}: {
  query: string;
  district: string;
  onManual: () => void;
}) {
  const q = query.trim();
  return (
    <div
      role="status"
      className="flex h-full flex-col items-center justify-center gap-2.5 px-4 text-center"
    >
      <b className="text-[17px] text-ink">
        {q
          ? `${district}에 「${q}」${iGa(q)} 들어간 어린이집이 없어요`
          : `${district}에서 찾은 어린이집이 없어요`}
      </b>
      <small className="text-[14px] leading-[1.55] text-ink-soft">
        이번 달에 새로 문을 연 원은 목록에 아직 없을 수 있어요.
      </small>
      <CtaButton className="mt-2" onClick={onManual}>
        직접 적기
      </CtaButton>
    </div>
  );
}

/**
 * 찾은 어린이집 — 칠판에 번호를 매겨 적은 목록. 쌤플을 쓰는 원이면 선생님 수를 단다(이름은 안 보인다).
 * 마우스를 올리면(키보드로 가도) 이름에 노란 분필로 동그라미를 치고 체크를 그린다. 누르면 바로 고른다.
 */
function DaycareResults({
  items,
  settings,
  onPick,
}: {
  /** 빈 목록은 부르는 쪽(NoDaycare)이 따로 그린다. */
  items: Daycare[] | null;
  settings: ClassSettings;
  onPick: (d: Daycare) => void;
}) {
  if (items === null) return <p className="p-2 text-[15px] text-board-ink-soft">찾는 중이에요…</p>;
  return (
    <ol
      aria-label="찾은 어린이집"
      className="flex h-full flex-col gap-1 overflow-y-auto overflow-x-hidden"
    >
      {items.map((d, i) => (
        <li key={d.key}>
          <button
            type="button"
            onClick={() => onPick(d)}
            className="group grid min-h-[66px] w-full grid-cols-[34px_minmax(0,1fr)_40px] items-center gap-2.5 px-1 py-1.5 text-left text-ink focus-visible:outline-none"
          >
            <span
              aria-hidden="true"
              className="text-center font-display text-[26px] font-bold text-ink-soft group-hover:text-primary group-focus-visible:text-primary"
            >
              {i + 1}
            </span>
            <span className="relative min-w-0 justify-self-start py-1 pl-3 pr-3.5">
              <ChalkRing />
              <b className="text-[18px] leading-[26px]">{d.name}</b>
              {d.teacher_count > 0 && (
                <span className="ml-2 font-display text-[19px] font-bold text-primary">
                  쌤플 선생님 {d.teacher_count}명
                </span>
              )}
              {d.status === "휴지" && (
                <span className="ml-2 font-display text-[19px] font-bold text-ink-soft">휴지</span>
              )}
              <small className="mt-0.5 block truncate text-[13px] leading-[18px] text-ink-soft">
                {d.kind} · {street(d, settings)}
              </small>
            </span>
            <ChalkCheck />
          </button>
        </li>
      ))}
    </ol>
  );
}

/** 이름에 친 분필 동그라미 — 한 획으로 돌리고 시작한 자리를 조금 지나쳐 끝난다. 결은 OnboardingLayout 의 #chalk 필터. */
function ChalkRing() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 100 40"
      preserveAspectRatio="none"
      className="pointer-events-none absolute -inset-x-2.5 -inset-y-2 h-[calc(100%+16px)] w-[calc(100%+20px)] overflow-visible text-primary opacity-0 transition-opacity duration-150 group-hover:opacity-90 group-focus-visible:opacity-100 motion-reduce:transition-none"
    >
      <path
        d="M50 3.5 C78.7 1.5 99 8 98 20 C97 32 70 38 48.7 37 C24.7 36 1.7 31.5 2.3 19.5 C3 7.5 26 2.5 57.3 5"
        fill="none"
        stroke="currentColor"
        strokeWidth={2.6}
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
        filter="url(#chalk)"
      />
    </svg>
  );
}

/** 동그라미와 같이 나타나는 분필 체크. */
function ChalkCheck() {
  return (
    <svg
      aria-hidden="true"
      width="34"
      height="34"
      viewBox="0 0 34 34"
      className="text-primary opacity-0 transition-opacity duration-150 group-hover:opacity-90 group-focus-visible:opacity-100 motion-reduce:transition-none"
    >
      <path
        d="M6 18 L14 26 L29 6"
        fill="none"
        stroke="currentColor"
        strokeWidth={3.4}
        strokeLinecap="round"
        strokeLinejoin="round"
        filter="url(#chalk)"
      />
    </svg>
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
}: {
  step: Step;
  busy: boolean;
  valid: boolean;
  onNext: () => void;
}) {
  return (
    <CtaButton disabled={busy || !valid} onClick={onNext}>
      {busy ? "저장 중이에요" : step === "join" ? "이 원으로 시작하기" : "다음"}
    </CtaButton>
  );
}
