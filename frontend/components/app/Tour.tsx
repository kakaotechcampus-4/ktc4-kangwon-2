"use client";

/**
 * 처음 온 선생님에게 화면을 한 칸씩 짚어 주는 안내 (멘토 12주차 리뷰 — 튜토리얼).
 *
 * 보육 문서는 순서와 위계가 있다(기록 → 일지 → 계획안 · 평가). 그걸 모르고 들어오면
 * 「뭘 해야 하지?」에서 멈춘다. 화면마다 3~4칸만, 그 화면에서 처음 할 일을 비춘다.
 *
 * - 비출 자리는 `data-tour="…"` 로 단다. CSS 모듈 클래스 이름은 빌드마다 바뀐다.
 * - 화면에 없는 칸(기록이 아직 없어 안 그려진 칸)은 건너뛴다.
 * - 한 화면은 한 번만 뜬다. 「다시 보지 않기」면 전부 끈다. 설정에서 다시 켠다.
 * - 이 브라우저에만 적는다. 실패해도 한 번 더 뜰 뿐이라 막지 않는다.
 *
 * farmguardian-FE 의 `Tour.tsx` 를 옮겨 왔다(PM 작업).
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { Posty } from "./Posty";
import styles from "./Tour.module.css";

const OFF = "ssample.tour.off";
const SEEN = "ssample.tour.seen";

type Step = {
  /** 비출 자리. `[data-tour="…"]` 의 값이다. */
  at: string;
  title: string;
  body: string;
  /** 구멍을 자리보다 얼마나 넓게 뚫을지. 기본 8px. */
  pad?: number;
};

/**
 * 화면마다 따로. 위에서 아래로 짚어야 구멍이 튀지 않는다.
 * 계획안 · 문서 보관함 · 평가 점검은 아직 화면을 고치는 중이라 넣지 않았다(PM).
 */
const TOURS: Record<string, Step[]> = {
  "/": [
    {
      at: "nav",
      title: "쌤플은 이 순서로 흘러가요",
      body: "관찰 · 일과를 기록하면 → 보육일지가 되고 → 계획안과 평가 점검에서 꺼내 써요. 메뉴가 그 순서대로 놓여 있어요.",
      pad: 0,
    },
    {
      at: "home-compose",
      title: "본 것을 한 줄로",
      body: "교실에서 본 장면을 바로 적어요. 누구 이야기인지는 적고 나서 골라요. 쌓인 한 줄이 관찰일지와 보육일지가 돼요.",
    },
    {
      at: "home-today",
      title: "오늘 쪽지",
      body: "오늘 남긴 기록과 일과가 여기에 모여요. 다 모이면 여기서 오늘 일지로 넘어가요.",
    },
    {
      at: "home-board",
      title: "놓친 것을 알려 줘요",
      body: "오늘 기록이 없는 아이, 기록이 없어 일지를 못 만든 지난 날을 칠판에 붙여 둬요.",
    },
  ],
  "/records": [
    {
      at: "records-form",
      title: "오늘 본 것 적기",
      body: "아이 · 날짜 · 영역을 고르고 본 대로 적어요. 판단보다 본 장면 그대로가 좋아요.",
    },
    {
      at: "records-order",
      title: "이 순서면 일지가 잘 나와요",
      body: "상황 → 행동 → 반응 → 교사 지원. 다 적지 않아도 저장돼요.",
      pad: 6,
    },
    {
      at: "records-list",
      title: "쌓인 기록",
      body: "날짜별로 모여요. 이 기록으로 관찰일지를 만들어요. 한 아이만 모아 보려면 위의 「아이별 기록」을 눌러요.",
    },
  ],
  "/routines": [
    {
      at: "routines-calendar",
      title: "날을 골라요",
      body: "점이 찍힌 날은 일과를 적은 날이에요. 밀린 날도 눌러서 바로 적어요.",
    },
    {
      at: "routines-board",
      title: "하루가 미리 깔려 있어요",
      body: "「실제로 한 것」만 채우면 돼요. 시간은 시계를 눌러 고치고, 시간순으로 저절로 줄을 서요.",
    },
    {
      at: "routines-actions",
      title: "저장하고 일지로",
      body: "「오늘 일지 만들기」를 누르면 저장하고, 이 화면에서 일일 보육일지를 만들어요.",
      pad: 6,
    },
    {
      at: "routines-journal",
      title: "오늘 일지는 여기서",
      body: "초안인지 확정했는지가 보여요. 이어서 쓰면 칠판 밑에 일지가 펼쳐져요.",
    },
  ],
  "/weekly-records": [
    {
      at: "weekly-week",
      title: "한 주를 펴 봐요",
      body: "날마다 일과 · 관찰이 몇 건인지 보여요. 점선은 아직 빈 날이에요.",
    },
    {
      at: "weekly-board",
      title: "그날 기록",
      body: "고른 날의 일과 쪽지와 관찰 카드가 칠판에 붙어요.",
    },
    {
      at: "weekly-journal",
      title: "주간 보육일지",
      body: "그 주에 확정한 일일 보육일지로 만들어요. 초안인 일지는 「확정하러 가기」로 데려가 줘요.",
    },
    {
      at: "weekly-make",
      title: "주간 일지 만들기",
      body: "못 만드는 때면 눌렀을 때 왜 안 되는지 알려 줘요.",
      pad: 6,
    },
  ],
};

const target = (at: string) => document.querySelector<HTMLElement>(`[data-tour="${at}"]`);

function isOff() {
  try {
    return localStorage.getItem(OFF) === "1";
  } catch {
    return false;
  }
}

function seenPaths(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(SEEN) ?? "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

function markSeen(path: string) {
  try {
    const seen = seenPaths();
    if (!seen.includes(path)) localStorage.setItem(SEEN, JSON.stringify([...seen, path]));
  } catch {
    /* 못 적으면 다음에 한 번 더 뜰 뿐이다 */
  }
}

function turnOffAll() {
  try {
    localStorage.setItem(OFF, "1");
  } catch {
    /* 못 적어도 이번에는 닫힌다 */
  }
}

/** 설정의 「튜토리얼 다시 보기」. 끈 것도 본 것도 되살린다. */
export function resetTour() {
  try {
    localStorage.removeItem(OFF);
    localStorage.removeItem(SEEN);
  } catch {
    /* 못 지우면 다시 뜨지 않을 뿐이다 */
  }
}

type Hole = { top: number; left: number; width: number; height: number };

/** 안내 카드 너비. 칸 옆에 붙일 자리를 셀 때 쓴다 — CSS 의 `.card` 와 같다. */
const CARD = 340;

export default function Tour() {
  const path = usePathname();
  // 어느 화면의 안내인지 같이 둔다. 화면이 바뀌면 지난 화면 안내는 저절로 빈 것이 된다.
  const [open, setOpen] = useState<{ path: string; steps: Step[] }>({ path: "", steps: [] });
  const steps = open.path === path ? open.steps : [];
  const [index, setIndex] = useState(0);
  const [hole, setHole] = useState<Hole | null>(null);
  const next = useRef<HTMLButtonElement>(null);

  const shut = useCallback(() => {
    setOpen({ path: "", steps: [] });
    setHole(null);
  }, []);
  const close = useCallback(() => {
    markSeen(path);
    shut();
  }, [path, shut]);
  const turnOff = useCallback(() => {
    turnOffAll();
    shut();
  }, [shut]);

  // 화면이 바뀌면 그 화면 안내를 새로 연다. 지난 화면 안내는 `open.path` 가 달라 이미 닫혀 있다.
  useEffect(() => {
    const tour = TOURS[path];
    // 자동화 브라우저(e2e)에는 띄우지 않는다. 덮개가 화면을 막아 모든 시나리오가 첫 화면에서 멈춘다.
    if (!tour || navigator.webdriver || isOff() || seenPaths().includes(path)) return;
    // 서버에서 기록을 받아 오는 동안은 칸이 없다. 하나라도 생겨야 세기 시작한다.
    let alive = true;
    let tries = 0;
    const look = () => {
      if (!alive) return;
      if (!tour.some((step) => target(step.at))) {
        if (++tries < 15) window.setTimeout(look, 400);
        return;
      }
      // 나머지 칸이 따라 그려질 틈을 준다.
      window.setTimeout(() => {
        if (!alive) return;
        setOpen({ path, steps: tour.filter((step) => target(step.at)) });
        setIndex(0);
      }, 500);
    };
    window.setTimeout(look, 300);
    return () => {
      alive = false;
    };
  }, [path]);

  const step = steps[index];

  // 칸을 화면 안으로 끌어온 뒤 잰다. 칸 크기가 바뀌면 구멍도 따라간다.
  useLayoutEffect(() => {
    if (!step) return;
    const el = target(step.at);
    if (!el) return;
    el.scrollIntoView({ block: "center" });
    const pad = step.pad ?? 8;
    const measure = () => {
      const box = el.getBoundingClientRect();
      setHole({
        top: box.top - pad,
        left: box.left - pad,
        width: box.width + pad * 2,
        height: box.height + pad * 2,
      });
    };
    measure();
    const watch = new ResizeObserver(measure);
    watch.observe(el);
    window.addEventListener("resize", measure);
    return () => {
      watch.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [step]);

  // 안내가 떠 있는 동안은 뒤 화면이 굴러가지 않게 막는다. 구멍이 어긋난다.
  useEffect(() => {
    if (!step) return;
    const before = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    next.current?.focus();
    const key = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", key);
    return () => {
      document.body.style.overflow = before;
      window.removeEventListener("keydown", key);
    };
  }, [step, close]);

  if (!step || !hole) return null;
  const last = index === steps.length - 1;

  // 칸을 가리지 않는 쪽에 둔다 — 아래 → 위 → 오른쪽 순. 다 좁으면(큰 칸) 화면 아래에 붙인다.
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const left = Math.min(Math.max(16, hole.left), vw - CARD - 16);
  const place =
    vh - (hole.top + hole.height) > 260
      ? { top: hole.top + hole.height + 18, left }
      : hole.top > 260
        ? { bottom: vh - hole.top + 18, left }
        : vw - (hole.left + hole.width) > CARD + 40
          ? { top: Math.max(16, Math.min(hole.top, vh - 300)), left: hole.left + hole.width + 24 }
          : undefined;

  return (
    <div className={styles.tour} role="dialog" aria-modal="true" aria-labelledby="tour-title">
      {/* 덮개 겸 클릭 막이. 구멍 밖을 눌러도 뒤 화면이 반응하지 않는다. */}
      <div className={styles.veil} />
      <div className={styles.hole} style={hole} />

      <div key={index} className={`${styles.card} ${place ? "" : styles.pinned}`} style={place}>
        <span aria-hidden="true" className={styles.tape} />
        {/* 포스티가 카드 모서리에서 짚어 준다. 움직이지 않는다. */}
        <Posty
          pose="point"
          face="base"
          tone="note"
          size={58}
          label={null}
          className={styles.posty}
        />
        <p className={styles.count}>
          {index + 1} / {steps.length}
        </p>
        <h2 id="tour-title" className={styles.title}>
          {step.title}
        </h2>
        <p className={styles.body}>{step.body}</p>

        <div className={styles.foot}>
          <span className={styles.dots} aria-hidden="true">
            {steps.map((s, n) => (
              <span key={s.at} data-on={n === index || undefined} />
            ))}
          </span>
          {!last && (
            <button type="button" className={styles.ghost} onClick={close}>
              건너뛰기
            </button>
          )}
          <button
            ref={next}
            type="button"
            className={styles.primary}
            onClick={() => (last ? close() : setIndex(index + 1))}
          >
            {last ? "다 봤어요" : "다음 →"}
          </button>
        </div>
        <button type="button" className={styles.off} onClick={turnOff}>
          다시 보지 않기
        </button>
      </div>
    </div>
  );
}
