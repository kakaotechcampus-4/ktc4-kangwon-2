"use client";
import { useRouter } from "next/navigation";
import {
  useEffect,
  useId,
  useLayoutEffect,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { useClientState } from "@/lib/hooks/use-client-state";
import { chosenClassFor, loadClassSettings } from "@/lib/onboarding/settings";
import { EMPTY_CLASS_SETTINGS, type ClassroomEntry } from "@/lib/onboarding/types";
import { hydrateClassChildren } from "@/lib/api/onboarding";
import { changePassword, getCurrentUser } from "@/lib/api/auth";
import { invalidFields } from "@/lib/api/client";
import { getCenterSettings, saveCenterSettings } from "@/lib/api/centers";
import {
  AXES,
  AXIS_LABELS,
  DEFAULT_AXIS,
  type ObservationAxis,
} from "@/lib/workspace/observation-axis";
import { captureSession } from "@/lib/auth/request-session";
import { resetTour } from "@/components/app/Tour";
import { Message, WorkspacePage, ws } from "@/components/workspace/WorkspaceUI";
import { ClassesEditor, KidsEditor, NoteSheet, OrgEditor } from "./SettingsNoteEditors";
import { SettingsIcon, type SettingsIconName } from "./SettingsIcons";
import styles from "./Settings.module.css";

const TABS = [
  { key: "center", label: "어린이집" },
  { key: "records", label: "기록 · 계획안" },
  { key: "account", label: "내 계정" },
] as const;
type Tab = (typeof TABS)[number]["key"];
type Tone = "yellow" | "plum" | "clay" | "sage";

/** 쪽지를 떼어 크게 여는 칸. 여는 단추와 떼어 낸 쪽지 안을 준다. */
type Peel = {
  trigger: (open: () => void) => ReactNode;
  content: (close: () => void) => ReactNode;
  onClosed?: () => void;
};

/**
 * 쪽지가 붙어 있던 자리에서 가운데로 날아오게 한다(되돌아갈 때는 거꾸로).
 * 움직임을 줄여 달라고 한 사람에게는 바로 열고 닫는다.
 */
function fly(from: HTMLElement | null, to: HTMLElement, tilt: number, back = false) {
  if (!from || !to.animate || matchMedia("(prefers-reduced-motion: reduce)").matches) return null;
  const a = from.getBoundingClientRect();
  const b = to.getBoundingClientRect();
  const frames = [
    {
      transform: `translate(${a.left - b.left}px, ${a.top - b.top}px) scale(${a.width / b.width}, ${a.height / b.height}) rotate(${tilt}deg)`,
      opacity: 0.6,
    },
    { transform: "none", opacity: 1 },
  ];
  return to.animate(back ? frames.reverse() : frames, {
    duration: 320,
    easing: "cubic-bezier(.2, .8, .2, 1)",
    fill: back ? "forwards" : "none",
  });
}

/**
 * 종이에 붙인 쪽지 한 장. 색 머리띠에 손글씨 이름, 점선 아래 크림 바탕에 내용.
 * 기울기는 장마다 다르게 준다 — 같은 각도면 붙여 놓은 느낌이 안 난다.
 *
 * `peel` 을 주면 쪽지를 떼어 가운데에 크게 연다. 브라우저 모달이라 Esc 로 닫히고 포커스가 안에 머문다.
 * 떼어 낸 동안 제자리에는 점선 자국만 남는다.
 */
function Note({
  title,
  icon,
  tone,
  tilt,
  peel,
  children,
}: {
  title: string;
  icon: SettingsIconName;
  tone: Tone;
  tilt: number;
  peel?: Peel;
  children: ReactNode;
}) {
  // ref 대신 상태로 받는다. 닫는 함수를 떼어 낸 쪽지 안에 넘기므로 렌더 중에 ref 를 읽지 않게.
  const [note, setNote] = useState<HTMLElement | null>(null);
  const [dialog, setDialog] = useState<HTMLDialogElement | null>(null);
  const [open, setOpen] = useState(false);
  const titleId = useId();

  // 안이 그려진 뒤에 열어야 크기를 재서 날아올 수 있다.
  useLayoutEffect(() => {
    if (!open || !dialog || dialog.open) return;
    dialog.showModal();
    fly(note, dialog, tilt);
  }, [open, dialog, note, tilt]);

  async function close() {
    if (!dialog?.open) return;
    const back = fly(note, dialog, tilt, true);
    await back?.finished.catch(() => {});
    dialog.close();
    back?.cancel();
  }

  return (
    <>
      <section
        ref={setNote}
        className={`${ws.card} ${styles.note} ${styles[tone]} ${open ? styles.lifted : ""}`}
        style={{ "--tilt": `${tilt}deg` } as CSSProperties}
      >
        <span className={styles.tape} aria-hidden="true" />
        <div className={styles.noteHead}>
          <h2 className={styles.title}>
            <SettingsIcon name={icon} />
            {title}
          </h2>
        </div>
        <div className={styles.noteBody}>
          {children}
          {peel?.trigger(() => setOpen(true))}
        </div>
      </section>
      {peel && (
        <dialog
          ref={setDialog}
          aria-labelledby={titleId}
          onCancel={(e) => {
            e.preventDefault();
            void close();
          }}
          onClose={() => {
            setOpen(false);
            peel.onClosed?.();
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) void close();
          }}
          className={`${styles.peeled} ${styles[tone]}`}
        >
          {open && (
            <>
              <h2 id={titleId} className={`${styles.title} ${styles.peeledHead}`}>
                <SettingsIcon name={icon} size={22} />
                {title}
              </h2>
              {peel.content(close)}
            </>
          )}
        </dialog>
      )}
    </>
  );
}

export default function SettingsPage() {
  const router = useRouter();
  const [settings, setSettings] = useClientState(
    () => loadClassSettings() || EMPTY_CLASS_SETTINGS,
    EMPTY_CLASS_SETTINGS,
  );
  const [error, setError] = useState("");
  const [centerId, setCenterId] = useState<number | null>(null);
  const [account, setAccount] = useState<{ name: string; email: string } | null>(null);
  const [requestVersion, setRequestVersion] = useState(0);
  const [tab, setTab] = useState<Tab>("center");

  // 관찰 영역 · 트렌드봇은 원 번호로 저장한다. 내 계정 칸의 이름 · 이메일도 여기서 받는다.
  useEffect(() => {
    let active = true;
    const session = captureSession();
    async function load() {
      try {
        const user = await getCurrentUser();
        session.assertCurrent();
        if (active) setAccount({ name: user.name, email: user.email });
        if (user.center_id === null) throw new Error("원 정보를 먼저 등록해야 합니다.");
        if (active) setCenterId(user.center_id);
      } catch (e) {
        if (!active || !session.isCurrent()) return;
        setError(e instanceof Error ? e.message : "설정을 불러오지 못했습니다.");
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [requestVersion]);

  // 아동 수는 서버에서 센다. 브라우저 저장소에는 아동 명단이 남지 않는다(ADR-013).
  // 쪽지를 닫으면 settings 가 새로 읽혀 다시 센다. 이름은 버리고 수만 둔다.
  const [kidCounts, setKidCounts] = useState<Record<string, number>>({});
  useEffect(() => {
    let live = true;
    hydrateClassChildren(settings)
      .then((classes) => {
        if (live) setKidCounts(Object.fromEntries(classes.map((c) => [c.id, c.children.length])));
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [settings]);

  function retry() {
    setError("");
    setRequestVersion((v) => v + 1);
  }

  // 아동은 이름 없이 수만 보인다.
  const chosen = chosenClassFor(settings);
  const region = [settings.regionProvince, settings.regionDistrict].filter(Boolean).join(" ");
  const kidCount = (c: ClassroomEntry) => kidCounts[c.id] ?? c.childIds?.length ?? 0;
  const children = settings.classes.reduce((sum, c) => sum + kidCount(c), 0);
  const org = [
    {
      title: "어린이집 정보",
      icon: "buildings",
      tone: "yellow",
      tilt: -2,
      Editor: OrgEditor,
      empty: "아직 등록하지 않았습니다.",
      facts: settings.orgName
        ? [
            ["이름", settings.orgName],
            ["지역", region],
          ]
        : [],
    },
    {
      title: "반 수 · 담당 반",
      icon: "users",
      tone: "plum",
      tilt: 1.5,
      Editor: ClassesEditor,
      empty: "아직 등록한 반이 없습니다.",
      facts: settings.classes.length
        ? [
            ["반 수", `${settings.classes.length}`],
            ...(chosen ? [["담당 반", chosen.className]] : []),
          ]
        : [],
    },
    {
      title: "아동 명단",
      icon: "baby",
      tone: "clay",
      tilt: -1,
      Editor: KidsEditor,
      empty: "아직 등록한 아동이 없습니다.",
      facts: settings.classes.length
        ? [chosen ? [chosen.className, `${kidCount(chosen)}명`] : ["전체", `${children}명`]]
        : [],
    },
  ] satisfies {
    title: string;
    icon: SettingsIconName;
    tone: Tone;
    tilt: number;
    Editor: typeof OrgEditor;
    empty: string;
    facts: string[][];
  }[];

  // 화살표로 옆 묶음으로 옮긴다 — 탭 목록의 키보드 약속이다.
  function moveTab(step: number) {
    const at = TABS.findIndex((t) => t.key === tab);
    const next = TABS[(at + step + TABS.length) % TABS.length].key;
    setTab(next);
    document.getElementById(`settings-tab-${next}`)?.focus();
  }

  return (
    <WorkspacePage
      title="설정"
      description="어린이집 정보, 기록과 계획안 작성에 필요한 설정, 내 계정을 관리합니다."
    >
      <div
        role="tablist"
        aria-label="설정 묶음"
        className={styles.tabs}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") moveTab(1);
          if (e.key === "ArrowLeft") moveTab(-1);
        }}
      >
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            id={`settings-tab-${t.key}`}
            aria-selected={tab === t.key}
            aria-controls={`settings-panel-${t.key}`}
            tabIndex={tab === t.key ? 0 : -1}
            className={`${styles.tab} ${styles[t.key]}`}
            onClick={() => setTab(t.key)}
          >
            <span>{t.label}</span>
          </button>
        ))}
      </div>
      <div className={styles.paper}>
        <div className={styles.sheet}>
          <section
            role="tabpanel"
            id="settings-panel-center"
            aria-labelledby="settings-tab-center"
            hidden={tab !== "center"}
            className={styles.panel}
          >
            <div className={styles.three}>
              {org.map((o) => (
                <Note
                  key={o.title}
                  title={o.title}
                  icon={o.icon}
                  tone={o.tone}
                  tilt={o.tilt}
                  peel={{
                    // 단추 모양 없이 연필만. 누르는 자리는 44px 로 남긴다.
                    trigger: (open) => (
                      <button
                        type="button"
                        className={styles.edit}
                        aria-label={`${o.title} 수정`}
                        title={`${o.title} 수정`}
                        onClick={open}
                      >
                        <SettingsIcon name="pencil" size={22} />
                      </button>
                    ),
                    // 저장 길은 첫 설정 화면과 같다(useOnboardingFlow).
                    content: (close) => <o.Editor onDone={close} />,
                    // 저장하면 이 브라우저의 원 · 반 설정이 바뀐다. 쪽지 요약을 다시 읽는다.
                    onClosed: () => setSettings(loadClassSettings() || EMPTY_CLASS_SETTINGS),
                  }}
                >
                  <Facts facts={o.facts} empty={o.empty} />
                </Note>
              ))}
            </div>
          </section>
          <section
            role="tabpanel"
            id="settings-panel-records"
            aria-labelledby="settings-tab-records"
            hidden={tab !== "records"}
            className={styles.panel}
          >
            {error && (
              <div>
                <Message error>{error}</Message>
                <button
                  type="button"
                  className={`${ws.secondary} ${styles.action}`}
                  onClick={retry}
                >
                  다시 시도
                </button>
              </div>
            )}
            {centerId !== null && (
              <div className={styles.two}>
                <ObservationAxisCard centerId={centerId} />
                <TrendsCard centerId={centerId} />
              </div>
            )}
          </section>
          <section
            role="tabpanel"
            id="settings-panel-account"
            aria-labelledby="settings-tab-account"
            hidden={tab !== "account"}
            className={styles.panel}
          >
            {account && (
              <div className={styles.strip}>
                <AccountCard name={account.name} email={account.email} />
              </div>
            )}
            <div className={styles.two}>
              <PasswordCard />
              <Note title="설명 다시 보기" icon="compass" tone="sage" tilt={1}>
                <p>
                  홈 화면으로 돌아가 <strong>쌤플</strong> 이용 방법을 다시 볼 수 있습니다.
                </p>
                {/* 끈 안내도 본 안내도 되살리고 첫 화면으로 간다 — 홈에서 바로 다시 뜬다. */}
                <button
                  type="button"
                  className={`${ws.secondary} ${styles.action}`}
                  onClick={() => {
                    resetTour();
                    router.push("/");
                  }}
                >
                  다시 보기
                </button>
              </Note>
            </div>
          </section>
        </div>
      </div>
    </WorkspacePage>
  );
}

/**
 * 쪽지 요약. 정보 이름(이름 · 지역 · 반 수 …)은 문장에 섞지 않고 손글씨 이름표로 뺀다.
 * 등록한 것이 없으면 안내 한 줄만.
 */
function Facts({ facts, empty }: { facts: string[][]; empty: string }) {
  if (!facts.length) return <p className={styles.summary}>{empty}</p>;
  return (
    <dl className={styles.facts}>
      {facts.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** 지금 로그인한 계정. 이름 첫 글자를 동그라미에 넣는다. */
function AccountCard({ name, email }: { name: string; email: string }) {
  return (
    <div className={styles.me}>
      <span className={styles.meMark} aria-hidden="true">
        {name.slice(0, 1) || "쌤"}
      </span>
      <span className={styles.meName}>{name ? `${name} 선생님` : "선생님"}</span>
      <span className={styles.meEmail}>{email}</span>
    </div>
  );
}

/**
 * 관찰 영역 축. 교사가 쓴 관찰일지 3건 중 2건이 누리과정 5영역이 아니었다
 * (`docs/references/관찰일지-서술-기준.md`). 원이 쓰는 양식에 맞춘다.
 */
function ObservationAxisCard({ centerId }: { centerId: number }) {
  const [axis, setAxis] = useState<ObservationAxis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    getCenterSettings(centerId)
      .then((s) => live && setAxis(s.observation_axis))
      .catch(() => live && setError("관찰 영역 설정을 불러오지 못했습니다."));
    return () => {
      live = false;
    };
  }, [centerId]);

  async function choose(next: ObservationAxis) {
    setBusy(true);
    setError("");
    // 화면을 먼저 바꾸지 않는다. 저장이 실패하면 바뀐 줄 알고 넘어간다.
    try {
      const saved = await saveCenterSettings(centerId, { observation_axis: next });
      setAxis(saved.observation_axis);
    } catch {
      setError("변경하지 못했습니다. 잠시 뒤 다시 시도해주세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Note title="관찰 영역" icon="search" tone="sage" tilt={-1.5}>
      <p>
        어린이집에서 사용하는 관찰일지 양식에 맞춰 영역을 구분합니다. 기존 기록은 그대로 유지됩니다.
      </p>
      <label className={`${ws.field} ${styles.inlineField}`}>
        영역 구분
        <select
          value={axis ?? DEFAULT_AXIS}
          disabled={axis === null || busy}
          onChange={(e) => choose(e.target.value as ObservationAxis)}
        >
          {(Object.keys(AXES) as ObservationAxis[]).map((key) => (
            <option key={key} value={key}>
              {AXIS_LABELS[key]}
            </option>
          ))}
        </select>
      </label>
      {error && <Message error>{error}</Message>}
      <p role="status">{busy ? "변경하고 있습니다." : ""}</p>
    </Note>
  );
}

/**
 * 트렌드봇 끄고 켜기 (FR-808 · §3-1).
 *
 * **기본은 꺼짐이다.** 부가 기능은 원하는 원이 켠다. 끄면 트렌드 화면이 막히고
 * 계획안 생성이 트렌드를 참고로 넣지 않는다. **이미 만든 계획안은 그대로 둔다** —
 * 출처는 그때 그랬다는 기록이다.
 */
function TrendsCard({ centerId }: { centerId: number }) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    getCenterSettings(centerId)
      .then((s) => live && setEnabled(s.trends_enabled))
      .catch(() => live && setError("트렌드봇 설정을 불러오지 못했습니다."));
    return () => {
      live = false;
    };
  }, [centerId]);

  async function toggle(next: boolean) {
    setBusy(true);
    setError("");
    // 화면을 먼저 바꾸지 않는다. 저장이 실패하면 켠 줄 알고 넘어간다.
    try {
      const saved = await saveCenterSettings(centerId, { trends_enabled: next });
      setEnabled(saved.trends_enabled);
    } catch {
      setError("변경하지 못했습니다. 잠시 뒤 다시 시도해주세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Note title="트렌드봇" icon="sparkle" tone="clay" tilt={1.2}>
      <p>
        최근 유행하는 놀이 소재를 모아 계획안에 참고 자료로 제공합니다. 이미 작성된 계획안에는
        영향을 주지 않습니다.
      </p>
      <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input
          type="checkbox"
          checked={enabled ?? false}
          disabled={enabled === null || busy}
          onChange={(e) => toggle(e.target.checked)}
        />
        트렌드봇 사용
      </label>
      {enabled !== null && (
        <p className={ws.muted}>현재 트렌드봇이 {enabled ? "켜져" : "꺼져"} 있습니다.</p>
      )}
      {error && <Message error>{error}</Message>}
      <p role="status">{busy ? "변경하고 있습니다." : ""}</p>
    </Note>
  );
}

/**
 * 비밀번호 변경.
 *
 * **다른 곳에서 쓰던 비밀번호로 가입한 교사에게 바꿀 자리가 있어야 한다.** 크롬은 자기가
 * 저장해 둔 비밀번호가 다른 주소의 입력 칸에 들어가면 피싱으로 의심하고 구글에 알린다.
 */
function PasswordCard() {
  const [done, setDone] = useState(false);
  return (
    <Note
      title="비밀번호 변경"
      icon="lock"
      tone="yellow"
      tilt={-1.5}
      peel={{
        trigger: (open) => (
          <button
            type="button"
            className={`${ws.secondary} ${styles.action}`}
            onClick={() => {
              setDone(false);
              open();
            }}
          >
            비밀번호 변경
          </button>
        ),
        content: (close) => (
          <PasswordForm
            onCancel={close}
            onChanged={() => {
              setDone(true);
              void close();
            }}
          />
        ),
      }}
    >
      <p>다른 서비스에서 사용한 적 없는 비밀번호 사용을 권장합니다.</p>
      <p role="status">{done ? "비밀번호를 변경했습니다." : ""}</p>
    </Note>
  );
}

/** 떼어 낸 쪽지 안에서만 그린다. 닫으면 사라져 적던 값도 같이 지워진다. */
function PasswordForm({ onCancel, onChanged }: { onCancel: () => void; onChanged: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    // 브라우저 말풍선(minLength) 대신 다른 오류와 같은 자리에 알린다.
    if (next.length < 8) {
      setError("새 비밀번호는 8자 이상이어야 합니다.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await changePassword(current, next);
      onChanged();
    } catch (caught) {
      const fields = invalidFields(caught, {
        current_password: "current_password",
        new_password: "new_password",
      });
      if (fields.includes("current_password")) setError("현재 비밀번호가 맞지 않습니다.");
      else if (fields.includes("new_password"))
        setError("현재 사용하는 비밀번호와 같습니다. 다른 비밀번호를 입력해주세요.");
      else setError("변경하지 못했습니다. 잠시 뒤 다시 시도해주세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className={styles.sheetForm}>
      <NoteSheet
        actions={
          <>
            <button type="button" className={styles.btn} onClick={onCancel} disabled={busy}>
              취소
            </button>
            <button type="submit" className={`${styles.btn} ${styles.solid}`} disabled={busy}>
              변경
            </button>
          </>
        }
      >
        <div className={styles.row2}>
          <label className={styles.field}>
            현재 비밀번호
            <input
              type="password"
              name="current-password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
            />
          </label>
          <label className={styles.field}>
            새 비밀번호
            <input
              type="password"
              name="new-password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
            />
          </label>
        </div>
        {error && (
          <p role="alert" className={styles.err}>
            {error}
          </p>
        )}
        <p role="status">{busy ? "변경하고 있습니다." : ""}</p>
      </NoteSheet>
    </form>
  );
}
