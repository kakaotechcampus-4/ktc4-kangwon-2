"use client";

/**
 * 월간계획안 양식 설정 (docs/api-spec.md §9-4 · FR-305).
 *
 * 월간계획안은 **원마다 칸이 다르다.** 어느 Section 을 쓸지는 이 화면에서 고르고, 고른
 * 결과(TemplateProfile)를 원 기본으로 걸어 둔다. 월간을 만들 때 그 Profile 을 쓴다.
 *
 * **이름 칸이 없다.** Profile 은 버전 · 기반 양식 · Section 으로 구분한다(§9-4). 교사에게는
 * 만든 날짜와 칸 목록을 보여준다.
 *
 * **고치기가 없다.** 서버에 DRAFT 편집 API 가 아직 없다. 바꾸려면 새로 만들어 기본으로 건다.
 */

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { syncCenter } from "@/lib/api/onboarding";
import {
  createTemplateProfile,
  getCenterDefaultProfile,
  listMonthlyTemplates,
  listReadyTemplateProfiles,
  putCenterDefaultProfile,
} from "@/lib/api/templateProfiles";
import type { MonthlyTemplate, ProfilePointer, ProfileRef, ReadyProfile } from "@/lib/api/types";
import { loadClassSettings } from "@/lib/onboarding/settings";
import { WorkspacePage, Empty, Message, ws } from "./WorkspaceUI";

function describe(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.message;
  return e instanceof Error ? e.message : fallback;
}

const same = (a: ProfileRef | null, b: ProfileRef | null) =>
  a?.profile_id === b?.profile_id && a?.profile_version === b?.profile_version;

/** 고를 수 있는 칸만 보여준다. 꼭 들어가는 칸은 끄지 못해서 목록에 두면 헷갈린다. */
const optional = (template: MonthlyTemplate) =>
  template.sections.filter((s) => s.selection === "OPTIONAL");
const required = (template: MonthlyTemplate) =>
  template.sections.filter((s) => s.selection === "REQUIRED");

export default function MonthlyTemplatePage() {
  const [centerId, setCenterId] = useState<number | null>(null);
  const [templates, setTemplates] = useState<MonthlyTemplate[] | null>(null);
  const [profiles, setProfiles] = useState<ReadyProfile[]>([]);
  const [pointer, setPointer] = useState<ProfilePointer | null>(null);
  const [picked, setPicked] = useState<string>("");
  const [extras, setExtras] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [problem, setProblem] = useState("");

  const reload = useCallback(async (id: number) => {
    const [ready, current] = await Promise.all([
      listReadyTemplateProfiles(id),
      getCenterDefaultProfile(id),
    ]);
    setProfiles(ready.items);
    setPointer(current);
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const settings = loadClassSettings();
        if (!settings) throw new Error("원 정보를 먼저 설정해주세요.");
        const id = await syncCenter(settings);
        const { items } = await listMonthlyTemplates();
        await reload(id);
        if (!alive) return;
        setCenterId(id);
        setTemplates(items);
        // 승인된 양식이 하나면 고를 것이 없다. 미리 골라 둔다.
        const usable = items.filter((t) => t.approved);
        if (usable.length === 1) setPicked(usable[0].template_ref.template_version);
      } catch (e) {
        if (alive) setProblem(describe(e, "양식 설정을 불러오지 못했어요."));
      }
    })();
    return () => {
      alive = false;
    };
  }, [reload]);

  const chosen = (templates ?? []).find((t) => t.template_ref.template_version === picked) ?? null;

  async function handleCreate() {
    if (centerId === null || !chosen) return;
    setBusy(true);
    setMessage("");
    setProblem("");
    try {
      const made = await createTemplateProfile(centerId, {
        base_template_ref: chosen.template_ref,
        selected_optional_keys: [...extras],
      });
      // 만들기만 하면 아무 데도 안 쓰인다. 바로 원 기본으로 건다 (§9-4 ③).
      await putCenterDefaultProfile(centerId, {
        profile_ref: made.profile_ref,
        expected_profile_ref: pointer?.profile_ref ?? null,
      });
      await reload(centerId);
      setExtras(new Set());
      setMessage("새 양식을 만들고 원 기본으로 설정했어요.");
    } catch (e) {
      setProblem(describe(e, "양식을 만들지 못했어요."));
    } finally {
      setBusy(false);
    }
  }

  async function handleUse(profile: ReadyProfile) {
    if (centerId === null) return;
    setBusy(true);
    setMessage("");
    setProblem("");
    try {
      await putCenterDefaultProfile(centerId, {
        profile_ref: profile.profile_ref,
        expected_profile_ref: pointer?.profile_ref ?? null,
      });
      await reload(centerId);
      setMessage("원 기본 양식을 바꿨어요.");
    } catch (e) {
      setProblem(describe(e, "기본 양식을 바꾸지 못했어요."));
    } finally {
      setBusy(false);
    }
  }

  const approved = (templates ?? []).filter((t) => t.approved);

  return (
    <WorkspacePage
      title="월간계획안 양식"
      description="월간계획안에 어떤 칸을 둘지 정해요. 정한 양식으로 월간계획안을 만듭니다."
    >
      <Message error>{problem}</Message>
      <Message>{message}</Message>

      <section style={{ marginBottom: 28 }}>
        <h3 className={ws.eyebrow}>지금 쓰는 양식</h3>
        {pointer?.profile_ref ? (
          <p className={ws.message} role="status">
            {profiles.find((p) => same(p.profile_ref, pointer.profile_ref))?.sections.length ?? 0}칸
            · {pointer.profile_ref.profile_version}
          </p>
        ) : (
          <Empty title="아직 정하지 않았어요">
            아래에서 양식을 만들면 월간계획안을 만들 수 있어요.
          </Empty>
        )}
      </section>

      {profiles.length > 0 && (
        <section style={{ marginBottom: 28 }}>
          <h3 className={ws.eyebrow}>만들어 둔 양식</h3>
          <ul className={ws.list}>
            {profiles.map((profile) => {
              const current = same(profile.profile_ref, pointer?.profile_ref ?? null);
              return (
                <li key={profile.profile_ref.profile_version} className={ws.item}>
                  <div>
                    <b>{profile.sections.filter((s) => s.visible).length}칸</b>{" "}
                    <span className={ws.muted}>
                      {profile.sections
                        .filter((s) => s.visible)
                        .map((s) => s.label || s.section_key)
                        .join(" · ")}
                    </span>
                  </div>
                  {current ? (
                    <span className={ws.badge}>지금 쓰는 양식</span>
                  ) : (
                    <button
                      type="button"
                      className={ws.secondary}
                      disabled={busy}
                      onClick={() => handleUse(profile)}
                    >
                      이걸로 쓰기
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <section>
        <h3 className={ws.eyebrow}>새 양식 만들기</h3>
        {templates === null ? (
          <p className={ws.muted}>불러오는 중…</p>
        ) : approved.length === 0 ? (
          <Empty title="쓸 수 있는 기반 양식이 없어요">
            기반 양식은 승인을 받아야 쓸 수 있어요. 운영팀에 문의해주세요.
          </Empty>
        ) : (
          <>
            {approved.length > 1 && (
              <label className={ws.field}>
                기반 양식
                <select value={picked} onChange={(e) => setPicked(e.target.value)}>
                  <option value="">고르기</option>
                  {approved.map((t) => (
                    <option
                      key={t.template_ref.template_version}
                      value={t.template_ref.template_version}
                    >
                      {t.template_ref.template_version}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {chosen && (
              <>
                <p className={ws.muted}>
                  꼭 들어가는 칸 —{" "}
                  {required(chosen)
                    .map((s) => s.label || s.section_key)
                    .join(" · ")}
                </p>
                <fieldset className={ws.stack}>
                  <legend>더 넣을 칸</legend>
                  {optional(chosen).map((s) => (
                    <label key={s.section_key} className={ws.check}>
                      <input
                        type="checkbox"
                        checked={extras.has(s.section_key)}
                        onChange={(e) => {
                          const next = new Set(extras);
                          if (e.target.checked) next.add(s.section_key);
                          else next.delete(s.section_key);
                          setExtras(next);
                        }}
                      />
                      {s.label || s.section_key}
                      {s.repeat_by === "WEEK" && <span className={ws.muted}> (주마다)</span>}
                    </label>
                  ))}
                </fieldset>
                <button
                  type="button"
                  className={ws.primary}
                  disabled={busy || centerId === null}
                  onClick={handleCreate}
                >
                  {busy ? "만드는 중…" : "이 양식으로 쓰기"}
                </button>
              </>
            )}
          </>
        )}
      </section>
    </WorkspacePage>
  );
}
