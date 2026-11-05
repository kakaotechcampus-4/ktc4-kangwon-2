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
 * 문서 보관함 · 평가 점검은 아직 화면을 고치는 중이라 넣지 않았다(PM).
 * 계획안은 첫 화면만 짚는다. 만드는 과정은 아래 `SLIDES` 로 화면 그림을 넘겨 보여 준다.
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
  "/plans": [
    {
      at: "plans-theme",
      title: "생활주제 따라 — 월별 주제형",
      body: "연간 → 월간 → 주간으로 차근차근 내려가요. 우리 원 연간계획안이 이미 있으면 「월간부터 시작하기」로 파일을 올려요.",
    },
    {
      at: "plans-play",
      title: "아이들 놀이 따라 — 놀이 중심형",
      body: "계절마다 놀이를 골라 연간을 만들고 월간으로 이어가요. 어느 방식이든 「연간부터 시작하기」를 누르면 만드는 순서를 그림으로 먼저 보여 드려요.",
    },
    {
      at: "plans-continue",
      title: "쓰다 만 계획안",
      body: "확정하지 않은 초안은 여기서 이어 써요. 확정한 계획안은 문서 보관함에 모여요.",
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

type Slide = { title: string; body: string };

/**
 * 계획안 만들기 첫 화면에 띄우는 「만드는 순서」. 실제 화면 위를 짚지 않고 미리 찍은 화면을 넘겨 본다 —
 * 만드는 도중에 덮개를 띄우면 AI 초안을 기다리는 화면 · 확정 창과 겹친다.
 * 그림은 `public/plan-guide/{dir}/01.webp…` 순서대로다. 화면이 바뀌면 그림도 다시 찍는다.
 */
const SLIDES: Record<"MONTHLY_THEME" | "PLAY_PROJECT", { dir: string; slides: Slide[] }> = {
  MONTHLY_THEME: {
    dir: "theme",
    slides: [
      {
        title: "요청 사항을 적고 만들어요",
        body: "반 · 연령 · 학년도는 미리 채워져 있어요. 바라는 것을 적거나 아래 단추로 넣고 「연간계획안 만들기」를 눌러요.",
      },
      {
        title: "12달 초안이 나와요",
        body: "3월부터 다음 해 2월까지 달마다 생활주제와 주별 소주제가 채워져요. 아직 초안이라 마음껏 고칠 수 있어요.",
      },
      {
        title: "칸을 눌러 고쳐요",
        body: "문서에서 고칠 칸을 누르면 왼쪽에서 바로 고쳐요. 되돌리기 · 다시 하기도 있어요.",
      },
      {
        title: "다 고쳤으면 확정해요",
        body: "「확정하기」를 누르고 한 번 더 확정하면 끝나요. 더 고칠 게 있으면 「더 다듬기」를 눌러요.",
      },
      {
        title: "내려받고 월간으로",
        body: "PDF · 한글 파일로 내려받을 수 있어요. 확정한 연간으로 「월간계획안 만들기 →」를 이어가요. 다시 고치려면 문서 보관함의 「수정하기」를 눌러요.",
      },
      {
        title: "월간은 연간에서 이어받아요",
        body: "달을 고르면 연간의 그 달 주제로 주마다 초안이 나와요. 고치고 확정하는 방법은 연간과 같아요.",
      },
      {
        title: "주간은 월간에서 이어받아요",
        body: "주를 고르면 초안이 나와요. 빈칸을 누르면 AI 후보가 뜨고, 「넣기」로 채워요.",
      },
    ],
  },
  PLAY_PROJECT: {
    dir: "play",
    slides: [
      {
        title: "요청 사항을 적고 만들어요",
        body: "바라는 놀이를 적거나 아래 단추로 넣고 「연간계획안 만들기」를 눌러요.",
      },
      {
        title: "계절마다 놀이를 골라요",
        body: "후보를 누르면 가운데에 자세히 보여요. 「이 놀이 고르기」로 봄 · 여름 · 가을 · 겨울마다 5개씩 골라요.",
      },
      {
        title: "문서에서 다듬어요",
        body: "다 고르면 「문서 만들기 →」. 문서의 칸을 고치거나 AI 후보에서 놀이를 빼고 넣어요.",
      },
      {
        title: "다 고쳤으면 확정해요",
        body: "「확정하기」를 누르고 한 번 더 확정하면 끝나요. 계절마다 5개를 다 골라야 확정돼요.",
      },
      {
        title: "내려받고 월간으로",
        body: "PDF · 한글 파일로 내려받을 수 있어요. 확정한 연간으로 「월간계획안 만들기 →」를 이어가요.",
      },
      {
        title: "월간은 연간에서 이어받아요",
        body: "달을 고르고, 그 달에 더 집중할 놀이를 골라요(안 골라도 돼요). 놀이 중심형은 주간이 없어요.",
      },
      {
        title: "빈칸은 후보로 채워요",
        body: "안전교육처럼 빈칸을 누르면 후보가 떠요. 「넣기」로 채우고 연간처럼 확정해요.",
      },
    ],
  },
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

/**
 * 만드는 순서를 화면 그림으로 넘겨 본다. 처음 한 번 저절로 뜨고, 「만드는 순서 보기」로 다시 연다.
 * 본 것 · 다시 보지 않기는 위 안내와 같은 자리에 적는다(설정의 「튜토리얼 다시 보기」로 되살아난다).
 */
export function SlideTour({ format }: { format: keyof typeof SLIDES }) {
  const { dir, slides } = SLIDES[format];
  const seen = `plan-guide:${format}`;
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);
  const next = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    // e2e 는 덮개에 막히지 않게 띄우지 않는다(위 안내와 같다).
    if (navigator.webdriver || isOff() || seenPaths().includes(seen)) return;
    const timer = window.setTimeout(() => setOpen(true), 300);
    return () => window.clearTimeout(timer);
  }, [seen]);

  const close = useCallback(() => {
    markSeen(seen);
    setOpen(false);
  }, [seen]);

  useEffect(() => {
    if (!open) return;
    const before = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    next.current?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "ArrowRight") setIndex((i) => Math.min(i + 1, slides.length - 1));
      if (e.key === "ArrowLeft") setIndex((i) => Math.max(i - 1, 0));
    };
    window.addEventListener("keydown", key);
    return () => {
      document.body.style.overflow = before;
      window.removeEventListener("keydown", key);
    };
  }, [open, close, slides.length]);

  const again = (
    <button
      type="button"
      className={styles.again}
      onClick={() => {
        setIndex(0);
        setOpen(true);
      }}
    >
      만드는 순서 보기
    </button>
  );
  if (!open) return again;
  const slide = slides[index];
  const last = index === slides.length - 1;
  return (
    <>
      {again}
      <div className={styles.tour} role="dialog" aria-modal="true" aria-labelledby="slide-title">
        <div className={styles.dim} />
        <div className={styles.slide}>
          <span aria-hidden="true" className={styles.tape} />
          <Posty
            pose="point"
            face="base"
            tone="note"
            size={58}
            label={null}
            className={styles.posty}
          />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            key={index}
            className={styles.shot}
            src={`/plan-guide/${dir}/${String(index + 1).padStart(2, "0")}.webp`}
            alt={`${slide.title} — 화면 예시`}
          />
          <p className={styles.count}>
            {index + 1} / {slides.length}
          </p>
          <h2 id="slide-title" className={styles.title}>
            {slide.title}
          </h2>
          <p className={styles.body}>{slide.body}</p>
          <div className={styles.foot}>
            <span className={styles.dots} aria-hidden="true">
              {slides.map((s, n) => (
                <span key={s.title + n} data-on={n === index || undefined} />
              ))}
            </span>
            {index > 0 && (
              <button type="button" className={styles.ghost} onClick={() => setIndex(index - 1)}>
                ← 이전
              </button>
            )}
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
              {last ? "만들러 가기" : "다음 →"}
            </button>
          </div>
          <button
            type="button"
            className={styles.off}
            onClick={() => {
              turnOffAll();
              setOpen(false);
            }}
          >
            다시 보지 않기
          </button>
        </div>
      </div>
    </>
  );
}
