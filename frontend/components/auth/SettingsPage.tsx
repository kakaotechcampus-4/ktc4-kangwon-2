"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useClientState, useHydrated } from "@/lib/hooks/use-client-state";
import { loadClassSettings, saveClassSettings } from "@/lib/onboarding/settings";
import { EMPTY_CLASS_SETTINGS, MONTH_ORDER, type CharacterMessages } from "@/lib/onboarding/types";
import { getCurrentUser } from "@/lib/api/auth";
import { getGreetings, saveGreetings, type Greetings } from "@/lib/api/centers";
import { captureSession } from "@/lib/auth/request-session";
import { StepCharacterMessages } from "@/components/onboarding/OnboardingPage";
import { Message, WorkspacePage, ws } from "@/components/workspace/WorkspaceUI";
import { WorkspaceViewState, type ViewStatus } from "@/components/workspace/WorkspaceViewState";

function greetingSettings(greetings: Greetings) {
  return {
    characterEducationEnabled: greetings.enabled,
    characterMessages: Object.fromEntries(
      greetings.items.map(({ month, text }) => [month, text]),
    ) as CharacterMessages,
  };
}

export default function SettingsPage() {
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
  return (
    <WorkspacePage title="설정" description="기관·담당 반과 성품인사를 관리해요.">
      <div className={ws.actions}>
        <Link href="/onboarding/center" className={ws.secondary}>
          원 정보 수정
        </Link>
        <Link href="/onboarding/classes" className={ws.secondary}>
          반·담당 반 수정
        </Link>
        <Link href="/onboarding/children" className={ws.secondary}>
          아동 명단 수정
        </Link>
      </div>
      {ready && (
        <section className={ws.card} style={{ marginTop: 24 }}>
          <WorkspaceViewState status={status} loading="성품인사를 불러오고 있어요." error={error}>
            <fieldset disabled={saving} aria-busy={saving} className="m-0 min-w-0 border-0 p-0">
              <StepCharacterMessages
                settings={settings}
                onChange={(p) => setSettings((s) => ({ ...s, ...p }))}
                onPrev={() => history.back()}
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
    </WorkspacePage>
  );
}
