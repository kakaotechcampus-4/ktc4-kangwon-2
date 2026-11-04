"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useClientState, useHydrated } from "@/lib/hooks/use-client-state";
import { chosenClassFor, loadClassSettings, saveClassSettings } from "@/lib/onboarding/settings";
import { EMPTY_CLASS_SETTINGS, MONTH_ORDER, type CharacterMessages } from "@/lib/onboarding/types";
import { changePassword, getCurrentUser } from "@/lib/api/auth";
import { invalidFields } from "@/lib/api/client";
import {
  createInvite,
  getCenterSettings,
  getGreetings,
  saveCenterSettings,
  saveGreetings,
  type Greetings,
  type Invite,
} from "@/lib/api/centers";
import {
  AXES,
  AXIS_LABELS,
  DEFAULT_AXIS,
  type ObservationAxis,
} from "@/lib/workspace/observation-axis";
import { captureSession } from "@/lib/auth/request-session";
import { resetTour } from "@/components/app/Tour";
import { Message, WorkspacePage, ws } from "@/components/workspace/WorkspaceUI";
import { WorkspaceViewState, type ViewStatus } from "@/components/workspace/WorkspaceViewState";
import SettingsGreetings from "./SettingsGreetings";
import styles from "./Settings.module.css";

const TABS = [
  { key: "center", label: "우리 원" },
  { key: "records", label: "기록 · 계획안" },
  { key: "account", label: "내 계정" },
] as const;
type Tab = (typeof TABS)[number]["key"];

function greetingSettings(greetings: Greetings) {
  return {
    characterEducationEnabled: greetings.enabled,
    characterMessages: Object.fromEntries(
      greetings.items.map(({ month, text }) => [month, text]),
    ) as CharacterMessages,
  };
}

export default function SettingsPage() {
  const router = useRouter();
  const [settings, setSettings] = useClientState(
    () => loadClassSettings() || EMPTY_CLASS_SETTINGS,
    EMPTY_CLASS_SETTINGS,
  );
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState<ViewStatus>("loading");
  const [centerId, setCenterId] = useState<number | null>(null);
  // 서버가 마지막으로 돌려준 월별 문구. 사용자가 고쳤는지 비교하는 기준이다.
  const [serverMessages, setServerMessages] = useState<CharacterMessages | null>(null);
  const [saving, setSaving] = useState(false);
  const [requestVersion, setRequestVersion] = useState(0);
  // 원 · 반 · 아동을 고치고 돌아오면 여기로 온다. 그래서 기본이 「우리 원」이다.
  const [tab, setTab] = useState<Tab>("center");
  const ready = useHydrated();

  useEffect(() => {
    let active = true;
    const session = captureSession();
    async function load() {
      try {
        const user = await getCurrentUser();
        session.assertCurrent();
        if (user.center_id === null) throw new Error("원 정보를 먼저 등록해주세요.");
        const greetings = await getGreetings(user.center_id);
        session.assertCurrent();
        if (!active) return;
        const fromServer = greetingSettings(greetings);
        setCenterId(user.center_id);
        setServerMessages(fromServer.characterMessages);
        setSettings((s) => ({ ...s, ...fromServer }));
        setStatus("ready");
      } catch (e) {
        if (!active || !session.isCurrent()) return;
        setError(e instanceof Error ? e.message : "성품인사를 불러오지 못했어요.");
        setStatus("error");
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [requestVersion, setSettings]);

  function retry() {
    setError("");
    setStatus("loading");
    setRequestVersion((v) => v + 1);
  }

  async function save() {
    if (centerId === null || status !== "ready" || saving) return;
    const before = serverMessages;
    // enabled=false 저장은 서버가 items 를 바꾸지 않는다 (§3). 고친 문구가 말없이 사라지므로 먼저 묻는다.
    const discardsEdits =
      !settings.characterEducationEnabled &&
      before !== null &&
      MONTH_ORDER.some((month) => settings.characterMessages[month] !== before[month]);
    if (
      discardsEdits &&
      !window.confirm(
        "성품교육을 사용하지 않으면 수정한 월별 문구는 저장되지 않아요. 계속 저장할까요?",
      )
    )
      return;
    const session = captureSession();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const greetings = await saveGreetings(centerId, {
        enabled: settings.characterEducationEnabled,
        items: MONTH_ORDER.map((month) => ({ month, text: settings.characterMessages[month] })),
      });
      session.assertCurrent();
      const fromServer = greetingSettings(greetings);
      setServerMessages(fromServer.characterMessages);
      // 다른 화면에서 수정한 로컬 원·반 설정도 그대로 유지한다.
      const next = { ...(loadClassSettings() || settings), ...fromServer };
      setSettings(next);
      setMessage(
        saveClassSettings(next)
          ? "설정을 저장했어요."
          : "성품인사는 서버에 저장했지만 이 브라우저에 설정을 저장하지 못했어요.",
      );
    } catch (e) {
      if (session.isCurrent())
        setError(e instanceof Error ? e.message : "성품인사를 저장하지 못했어요.");
    } finally {
      if (session.isCurrent()) setSaving(false);
    }
  }
  // 아동은 이름 없이 수만 보인다.
  const chosen = chosenClassFor(settings);
  const region = [settings.regionProvince, settings.regionDistrict].filter(Boolean).join(" ");
  const children = settings.classes.reduce((sum, c) => sum + c.children.length, 0);
  const org = [
    {
      title: "원 정보",
      href: "/onboarding/center?from=settings",
      summary: settings.orgName
        ? [settings.orgName, region].filter(Boolean).join(" · ")
        : "아직 등록하지 않았어요.",
    },
    {
      title: "반 · 담당 반",
      href: "/onboarding/classes?from=settings",
      summary: settings.classes.length
        ? `반 ${settings.classes.length}개${chosen ? ` · 담당 ${chosen.className}` : ""}`
        : "아직 등록한 반이 없어요.",
    },
    {
      title: "아동 명단",
      href: "/onboarding/children?from=settings",
      summary: chosen
        ? `${chosen.className} ${chosen.children.length}명`
        : settings.classes.length
          ? `전체 ${children}명`
          : "아직 등록한 아동이 없어요.",
    },
  ];

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
      description="우리 원 정보, 기록과 계획안에 쓰는 설정, 내 계정을 관리해요."
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
            {t.label}
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
                <div key={o.title} className={`${ws.card} ${styles.split}`}>
                  <div>
                    <h2>{o.title}</h2>
                    <p className={styles.summary}>{o.summary}</p>
                  </div>
                  <Link href={o.href} className={ws.secondary} aria-label={`${o.title} 수정`}>
                    수정
                  </Link>
                </div>
              ))}
            </div>
            {centerId !== null && <InviteCard centerId={centerId} />}
          </section>
          <section
            role="tabpanel"
            id="settings-panel-records"
            aria-labelledby="settings-tab-records"
            hidden={tab !== "records"}
            className={styles.panel}
          >
            {centerId !== null && (
              <div className={styles.two}>
                <ObservationAxisCard centerId={centerId} />
                <TrendsCard centerId={centerId} />
              </div>
            )}
            {ready && (
              <section className={ws.card}>
                <h2>성품인사</h2>
                <p>월별 성품인사 문구예요. 해당 월의 계획안을 만들 때 써요.</p>
                <WorkspaceViewState
                  status={status}
                  loading="성품인사를 불러오고 있어요."
                  error={error}
                >
                  <fieldset
                    disabled={saving}
                    aria-busy={saving}
                    className="m-0 mt-4 min-w-0 border-0 p-0"
                  >
                    <SettingsGreetings
                      settings={settings}
                      onChange={(p) => setSettings((s) => ({ ...s, ...p }))}
                      onFinish={save}
                    />
                  </fieldset>
                  {error && <Message error>{error}</Message>}
                  <p role="status">{saving ? "저장하고 있어요." : message}</p>
                </WorkspaceViewState>
                {status === "error" && (
                  <button type="button" className={ws.secondary} onClick={retry}>
                    다시 시도
                  </button>
                )}
              </section>
            )}
          </section>
          <section
            role="tabpanel"
            id="settings-panel-account"
            aria-labelledby="settings-tab-account"
            hidden={tab !== "account"}
            className={styles.panel}
          >
            <PasswordCard />
            <section className={`${ws.card} ${styles.split}`}>
              <div>
                <h2>화면 안내</h2>
                <p>화면마다 처음 한 번 뜨는 안내를 다시 켜요.</p>
              </div>
              {/* 끈 안내도 본 안내도 되살리고 첫 화면으로 간다 — 홈에서 바로 다시 뜬다. */}
              <button
                type="button"
                className={ws.secondary}
                onClick={() => {
                  resetTour();
                  router.push("/");
                }}
              >
                화면 안내 다시 보기
              </button>
            </section>
          </section>
        </div>
      </div>
    </WorkspacePage>
  );
}

/**
 * 트렌드봇 끄고 켜기 (FR-808 · §3-1).
 *
 * **기본은 꺼짐이다.** 부가 기능은 원하는 원이 켠다. 끄면 트렌드 화면이 막히고
 * 계획안 생성이 트렌드를 참고로 넣지 않는다. **이미 만든 계획안은 그대로 둔다** —
 * 출처는 그때 그랬다는 기록이다.
 */
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
      .catch(() => live && setError("관찰 영역 설정을 불러오지 못했어요."));
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
      setError("바꾸지 못했어요. 잠시 뒤 다시 해주세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={ws.card}>
      <div className={styles.head}>
        <h2>관찰 영역</h2>
        <span className={styles.badge}>바로 저장</span>
      </div>
      <p>
        관찰 기록을 어떤 영역으로 나눌지 정해요. 원에서 쓰는 관찰일지 양식에 맞추면 돼요.
        <strong> 이미 쓴 기록은 그대로 남아요</strong> — 새로 쓰는 기록부터 바뀐 영역을 써요.
      </p>
      <label className={ws.field}>
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
      <p className={ws.muted}>{AXES[axis ?? DEFAULT_AXIS].join(" · ")}</p>
      {error && <Message error>{error}</Message>}
      <p role="status">{busy ? "바꾸고 있어요." : ""}</p>
    </section>
  );
}

function TrendsCard({ centerId }: { centerId: number }) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    getCenterSettings(centerId)
      .then((s) => live && setEnabled(s.trends_enabled))
      .catch(() => live && setError("트렌드봇 설정을 불러오지 못했어요."));
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
      setError("바꾸지 못했어요. 잠시 뒤 다시 해주세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={ws.card}>
      <div className={styles.head}>
        <h2>트렌드봇</h2>
        <span className={styles.badge}>바로 저장</span>
      </div>
      <p>
        요즘 유행하는 놀이 소재를 모아 계획안에 참고로 붙여요. 쓰지 않으시면 꺼두세요. 꺼도 이미
        만든 계획안은 그대로예요.
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
      {enabled !== null && <p className={ws.muted}>지금 {enabled ? "켜져" : "꺼져"} 있어요.</p>}
      {error && <Message error>{error}</Message>}
      <p role="status">{busy ? "바꾸고 있어요." : ""}</p>
    </section>
  );
}

/** 같은 원 선생님을 부르는 1회용 코드 (§1-1). 코드는 화면에만 띄우고 브라우저에 저장하지 않는다. */
function InviteCard({ centerId }: { centerId: number }) {
  const [invite, setInvite] = useState<Invite | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function create() {
    setBusy(true);
    setError("");
    try {
      setInvite(await createInvite(centerId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "초대 코드를 만들지 못했어요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={ws.card}>
      <div className={styles.split}>
        <div>
          <h2>같은 원 선생님 초대</h2>
          <p>
            코드를 받은 선생님이 첫 설정 화면에서 입력하면 우리 원에 함께 들어와요. 코드는 한 번만
            쓸 수 있고 7일 뒤에 사라져요.
          </p>
          {invite && (
            <p role="status">
              초대 코드 <strong style={{ fontSize: 20, letterSpacing: 2 }}>{invite.code}</strong> ·{" "}
              {new Date(invite.expires_at).toLocaleDateString("ko-KR")}까지
            </p>
          )}
        </div>
        <button type="button" className={ws.secondary} onClick={create} disabled={busy}>
          {busy ? "만들고 있어요." : invite ? "새 코드 만들기" : "초대 코드 만들기"}
        </button>
      </div>
      {error && <Message error>{error}</Message>}
    </section>
  );
}

/**
 * 비밀번호 바꾸기.
 *
 * **다른 곳에서 쓰던 비밀번호로 가입한 교사에게 바꿀 자리가 있어야 한다.** 크롬은 자기가
 * 저장해 둔 비밀번호가 다른 주소의 입력 칸에 들어가면 피싱으로 의심하고 구글에 알린다.
 */
function PasswordCard() {
  // 접어 둔다. 펼쳐 두면 설정에 들어올 때마다 브라우저가 저장된 비밀번호를 채워 넣는다.
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  function close() {
    setOpen(false);
    setCurrent("");
    setNext("");
    setError("");
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    // 브라우저 말풍선(minLength) 대신 다른 오류와 같은 자리에 알린다.
    if (next.length < 8) {
      setError("새 비밀번호는 8자 이상이어야 해요.");
      return;
    }
    setBusy(true);
    setError("");
    setDone(false);
    try {
      await changePassword(current, next);
      close();
      setDone(true);
    } catch (caught) {
      const fields = invalidFields(caught, {
        current_password: "current_password",
        new_password: "new_password",
      });
      if (fields.includes("current_password")) setError("지금 비밀번호가 맞지 않아요.");
      else if (fields.includes("new_password"))
        setError("지금 쓰는 비밀번호와 같아요. 다른 비밀번호를 적어주세요.");
      else setError("바꾸지 못했어요. 잠시 뒤 다시 해주세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={ws.card}>
      <div className={styles.split}>
        <div>
          <h2>비밀번호 바꾸기</h2>
          <p>
            다른 곳에서 쓰는 비밀번호와 같다면 바꿔주세요.
            <strong> 쌤플에서만 쓰는 비밀번호</strong>가 안전해요.
          </p>
        </div>
        {!open && (
          <button
            type="button"
            className={ws.secondary}
            onClick={() => {
              setOpen(true);
              setDone(false);
            }}
          >
            비밀번호 바꾸기
          </button>
        )}
      </div>
      {open && (
        <form onSubmit={submit} className="mt-4">
          <div className={styles.two}>
            <label className={ws.field}>
              지금 비밀번호
              <input
                type="password"
                name="current-password"
                autoComplete="current-password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                required
              />
            </label>
            <label className={ws.field}>
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
          {error && <Message error>{error}</Message>}
          <div className={ws.actions}>
            <button type="submit" className={ws.secondary} disabled={busy}>
              바꾸기
            </button>
            <button type="button" className={ws.secondary} onClick={close} disabled={busy}>
              취소
            </button>
          </div>
        </form>
      )}
      <p role="status">{busy ? "바꾸고 있어요." : done ? "비밀번호를 바꿨어요." : ""}</p>
    </section>
  );
}
