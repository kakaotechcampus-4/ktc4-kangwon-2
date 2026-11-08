"use client";
import { useState, type ReactNode } from "react";
import { uid, useSettingsFlow } from "./useSettingsFlow";
import { shownPrimaryId } from "@/lib/onboarding/settings";
import {
  createEmptyClassroom,
  selectedAgesFor,
  type AgeGroup,
  type ClassroomEntry,
  type SelectedAge,
} from "@/lib/onboarding/types";

import { addServerChild, classServerId, removeServerChild } from "@/lib/api/onboarding";
import { SettingsIcon } from "./SettingsIcons";
import styles from "./Settings.module.css";

/*
 * 설정에서 떼어 낸 쪽지 안. 원 정보 · 반 · 아동 명단을 고친다.
 * 칸 모양은 쪽지에 맞춰 따로 그리고, 불러오기 · 저장은 `useSettingsFlow` 가 맡는다.
 */

type Flow = ReturnType<typeof useSettingsFlow>;
const AGES = [3, 4, 5] as const satisfies readonly SelectedAge[];

/** 떼어 낸 쪽지의 틀 — 안내 한 줄, 길면 안쪽만 스크롤되는 본문, 아래 단추. */
export function NoteSheet({
  hint,
  actions,
  children,
}: {
  hint?: string;
  actions: ReactNode;
  children: ReactNode;
}) {
  return (
    <>
      {hint && <p className={styles.hint}>{hint}</p>}
      <div className={styles.body}>{children}</div>
      <div className={styles.actions}>{actions}</div>
    </>
  );
}

function Loading() {
  return <p role="status">설정을 불러오고 있어요.</p>;
}

function SaveState({ flow }: { flow: Flow }) {
  return (
    <>
      {flow.saveError && (
        <p role="alert" className={styles.err}>
          {flow.saveError}
        </p>
      )}
      <p role="status">{flow.busy ? "저장 중이에요." : ""}</p>
    </>
  );
}

function SaveActions({
  onCancel,
  onSave,
  canSave,
  busy,
}: {
  onCancel: () => void;
  onSave: () => void;
  canSave: boolean;
  busy: boolean;
}) {
  return (
    <>
      <button type="button" className={styles.btn} onClick={onCancel} disabled={busy}>
        취소
      </button>
      <button
        type="button"
        className={`${styles.btn} ${styles.solid}`}
        onClick={onSave}
        disabled={!canSave || busy}
      >
        저장
      </button>
    </>
  );
}

export function ClassesEditor({ onDone }: { onDone: () => void }) {
  const flow = useSettingsFlow(2, onDone);
  if (!flow.ready) return <Loading />;
  const { settings, patch, save, busy } = flow;
  const update = (id: string, p: Partial<ClassroomEntry>) =>
    patch({ classes: settings.classes.map((c) => (c.id === id ? { ...c, ...p } : c)) });
  const canSave =
    settings.classes.length > 0 &&
    settings.classes.every(
      (c) =>
        c.className.trim() !== "" && selectedAgesFor(c).length > 0 && c.teacherName.trim() !== "",
    );
  // 서버에 올라간 반은 고치면 기존 아동 · 기록이 끊긴다. 칸 대신 글로만 보인다.
  const locked = (c: ClassroomEntry) => classServerId(c.id) !== null;

  return (
    <NoteSheet
      hint={
        settings.classes.some(locked)
          ? "등록한 반의 이름 · 연령 · 담임 · 동의 여부는 아직 수정할 수 없습니다. 반 추가와 담당 반 선택만 할 수 있습니다."
          : undefined
      }
      actions={<SaveActions onCancel={onDone} onSave={save} canSave={canSave} busy={busy} />}
    >
      {settings.classes.map((c, i) => (
        <ClassCard
          key={c.id}
          classroom={c}
          index={i}
          locked={locked(c)}
          canRemove={settings.classes.length > 1}
          onChange={(p) => update(c.id, p)}
          onRemove={() => patch({ classes: settings.classes.filter((x) => x.id !== c.id) })}
        />
      ))}
      {settings.classes.length > 1 && (
        <label className={styles.field}>
          내 담당 반
          <select
            value={shownPrimaryId(settings)}
            onChange={(e) => patch({ primaryClassId: e.target.value })}
          >
            {settings.classes.map((c, i) => (
              <option key={c.id} value={c.id}>
                {c.className || "반 " + (i + 1)}
              </option>
            ))}
          </select>
        </label>
      )}
      <button
        type="button"
        className={styles.addclass}
        onClick={() =>
          patch({ classes: [...settings.classes, createEmptyClassroom(uid("class"))] })
        }
      >
        + 반 추가
      </button>
      <SaveState flow={flow} />
    </NoteSheet>
  );
}

function ClassCard({
  classroom: c,
  index,
  locked,
  canRemove,
  onChange,
  onRemove,
}: {
  classroom: ClassroomEntry;
  index: number;
  locked: boolean;
  canRemove: boolean;
  onChange: (p: Partial<ClassroomEntry>) => void;
  onRemove: () => void;
}) {
  const ages = selectedAgesFor(c);
  function toggleAge(age: SelectedAge, checked: boolean) {
    const next = AGES.filter((a) => (a === age ? checked : ages.includes(a)));
    onChange({
      selectedAges: next,
      ageGroup: next.length === 1 ? (String(next[0]) as AgeGroup) : "",
    });
  }

  return (
    <div className={styles.classcard}>
      <div className={styles.classHead}>
        <b>
          <span className={styles.no}>{index + 1}</span>반 정보
        </b>
        {canRemove && (
          <button
            type="button"
            className={styles.del}
            aria-label={`${c.className || `${index + 1}번 반`} 삭제`}
            onClick={onRemove}
          >
            삭제
          </button>
        )}
      </div>
      <TextRow
        label="반 이름"
        value={c.className}
        locked={locked}
        placeholder="반 이름을 입력해주세요"
        onChange={(className) => onChange({ className })}
      />
      <div className={styles.field} role="group" aria-label="연령">
        연령
        <div className={styles.chips}>
          {AGES.map((age) =>
            locked ? (
              <span key={age} className={`${styles.chip} ${ages.includes(age) ? styles.on : ""}`}>
                만 {age}세
              </span>
            ) : (
              <label key={age} className={`${styles.chip} ${ages.includes(age) ? styles.on : ""}`}>
                <input
                  type="checkbox"
                  checked={ages.includes(age)}
                  onChange={(e) => toggleAge(age, e.target.checked)}
                />
                만 {age}세
              </label>
            ),
          )}
        </div>
      </div>
      <TextRow
        label="담임 이름"
        value={c.teacherName}
        locked={locked}
        placeholder="담임 이름을 입력해주세요"
        onChange={(teacherName) => onChange({ teacherName })}
      />
      <label className={styles.consent}>
        <input
          type="checkbox"
          checked={c.guardianConsent}
          disabled={locked}
          onChange={(e) =>
            onChange({
              guardianConsent: e.target.checked,
              childrenSkipped: e.target.checked ? false : c.childrenSkipped,
            })
          }
        />
        <span>
          이 반 모든 아동의 법정대리인 동의를 받았습니다.
          <small>동의 확인 전에는 아동 이름을 입력하지 않습니다.</small>
        </span>
      </label>
    </div>
  );
}

function TextRow({
  label,
  value,
  locked,
  placeholder,
  onChange,
}: {
  label: string;
  value: string;
  locked: boolean;
  placeholder: string;
  onChange: (value: string) => void;
}) {
  if (locked)
    return (
      <div className={styles.field}>
        {label}
        <div className={styles.locked}>
          <SettingsIcon name="lock" size={14} />
          {value}
        </div>
      </div>
    );
  return (
    <label className={styles.field}>
      {label}
      <input value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

export function KidsEditor({ onDone }: { onDone: () => void }) {
  const flow = useSettingsFlow(3, onDone);
  if (!flow.ready) return <Loading />;
  const { settings, patch, finish, busy } = flow;

  // 아동은 넣고 뺄 때마다 바로 저장된다. 「닫기」는 반 목록을 한 번 맞추고 닫는다.
  return (
    <NoteSheet
      hint="반 별로 아동의 이름을 한 명씩 등록합니다."
      actions={
        <button type="button" className={styles.btn} onClick={finish} disabled={busy}>
          닫기
        </button>
      }
    >
      {settings.classes.map((c) => (
        <KidRows
          key={c.id}
          classroom={c}
          onChange={(p) =>
            patch({ classes: settings.classes.map((x) => (x.id === c.id ? { ...x, ...p } : x)) })
          }
        />
      ))}
      <SaveState flow={flow} />
    </NoteSheet>
  );
}

/** 한 반의 아동 줄과 추가 칸. 넣고 빼는 규칙은 첫 설정 화면의 `ChildList` 와 같다. */
function KidRows({
  classroom: c,
  onChange,
}: {
  classroom: ClassroomEntry;
  onChange: (p: Partial<ClassroomEntry>) => void;
}) {
  const [draft, setDraft] = useState("");
  const [dup, setDup] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // 법정대리인 동의를 체크하지 않은 반이면 이름을 넣지 못한다.
  const locked = !c.guardianConsent;

  async function add() {
    if (busy || locked) return;
    const name = draft.trim();
    if (!name) return;
    if (c.children.some((k) => k.name === name)) {
      setDup(true);
      return;
    }
    setBusy(true);
    setError("");
    // 저장을 기다리지 않고 칸부터 비운다. 그 사이 치는 다음 이름이 앞 이름에 붙지 않게
    setDraft("");
    setDup(false);
    try {
      const child = await addServerChild(c, name);
      const children = [...c.children, child];
      onChange({ children, childIds: children.map((k) => k.id) });
    } catch (e) {
      setDraft((d) => d || name);
      setError(e instanceof Error ? e.message : "추가하지 못했어요.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    setError("");
    try {
      await removeServerChild(id);
      const children = c.children.filter((k) => k.id !== id);
      onChange({ children, childIds: children.map((k) => k.id) });
    } catch (e) {
      setError(e instanceof Error ? e.message : "삭제하지 못했어요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <p className={styles.classhead}>{c.className}</p>
      <div className={styles.kids}>
        {c.children.map((k) => (
          <div key={k.id} className={styles.kid}>
            {k.name}
            <button
              type="button"
              disabled={busy}
              aria-label={`${k.name} 삭제`}
              onClick={() => remove(k.id)}
            >
              삭제
            </button>
          </div>
        ))}
        <div className={styles.addrow}>
          <input
            value={draft}
            // 저장하는 동안에도 잠그지 않는다. 잠그면 커서가 빠지거나 그 사이 친 글자가 사라진다
            disabled={locked}
            placeholder={locked ? "반 정보에서 법정대리인 동의를 먼저 체크해주세요" : "아동 이름"}
            aria-label={`${c.className} 아동 이름`}
            aria-invalid={dup || undefined}
            onChange={(e) => {
              setDraft(e.target.value);
              setDup(false);
            }}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" &&
                !e.nativeEvent.isComposing &&
                e.nativeEvent.keyCode !== 229
              ) {
                e.preventDefault();
                void add();
              }
            }}
          />
          <button type="button" className={styles.btn} onClick={add} disabled={busy || locked}>
            추가
          </button>
        </div>
        {error && (
          <p role="alert" className={styles.err}>
            {error}
          </p>
        )}
        {dup && (
          <p className={styles.err}>
            이미 같은 이름이 등록되어 있어요. 구분이 필요하면 성을 붙여 입력해주세요.
          </p>
        )}
        <p role="status" className="sr-only">
          {busy ? "명단을 저장하고 있어요." : ""}
        </p>
      </div>
    </>
  );
}
