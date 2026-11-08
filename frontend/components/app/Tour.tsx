"use client";

/**
 * 처음 온 선생님에게 화면을 한 칸씩 짚어 주는 안내 (멘토 12주차 리뷰 — 튜토리얼).
 *
 * 보육 문서는 순서와 위계가 있다(기록 → 일지 → 계획안 · 평가). 그걸 모르고 들어오면
 * 「뭘 해야 하지?」에서 멈춘다. 화면마다 3~4칸만, 그 화면에서 처음 할 일을 비춘다.
 *
 * - 비출 자리는 `data-tour="…"` 로 단다. CSS 모듈 클래스 이름은 빌드마다 바뀐다.
 * - 화면에 없는 칸(기록이 아직 없어 안 그려진 칸)은 건너뛴다.
 * - 한 화면은 한 번만 뜬다. 설정의 「튜토리얼 다시 보기」로 다시 켠다.
 *   (「다시 보지 않기」 단추는 뺐다 — 한 번만 뜨니 따로 끌 까닭이 없다. 예전에 끈 기록은 그대로 따른다.)
 * - 이 브라우저에만 적는다. 실패해도 한 번 더 뜰 뿐이라 막지 않는다.
 *
 * farmguardian-FE 의 `Tour.tsx` 를 옮겨 왔다(PM 작업).
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type Ref } from "react";
import { usePathname } from "next/navigation";
import { appZoom } from "@/lib/appZoom";
import { Posty } from "./Posty";
import styles from "./Tour.module.css";

const OFF = "ssample.tour.off";
const SEEN = "ssample.tour.seen";

/**
 * 카드 본문. **한 줄에 한 문장**, 카드 폭에 한 줄로 들어가게 20자 안팎으로 쓴다(PM 점검 — 긴 글 튜토리얼을 벗어난다).
 * 글 안의 `**낱말**` 은 형광펜, 「버튼 이름」 은 버튼 모양으로 그린다(`Rich`). 「」 안에는 화면에 실제로 있는 글자만 쓴다.
 */
type Body = {
  /** 계단처럼 이어지는 흐름. 첫 줄 뒤로 › 가 붙는다. */
  flow?: string[];
  /** 번호 칩. 화면의 칸 이름 그대로. */
  steps?: string[];
  lines?: string[];
  /** 점 목록. */
  list?: string[];
  /** 몰라도 쓰는 데 지장 없는 덧붙임. 작은 글씨로 내린다. */
  tip?: string;
};

type Step = Body & {
  /** 비출 자리. `[data-tour="…"]` 의 값이다. */
  at: string;
  title: string;
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
      title: "쌤플은 기록에서 시작해요",
      flow: [
        "관찰 · 일과를 **기록**하면",
        "**보육일지**가 되고",
        "**계획안 · 평가 점검**에서 꺼내 써요",
      ],
      pad: 0,
    },
    {
      at: "home-compose",
      title: "교실에서 본 것을 기록해요",
      lines: ["있었던 일을 바로 적어 두면", "**관찰일지 · 보육일지**에 불러와 써요."],
      tip: "아이는 적은 뒤에 골라도 돼요.",
    },
    {
      at: "home-today",
      title: "오늘 남긴 기록",
      lines: ["오늘 적은 관찰 · 일과가 여기 모여요.", "다 적었으면 **보육일지**로 넘어가요."],
    },
    {
      // 칠판 세 칸을 위에서부터 — 기록 안된 아이들 · 비어 있는 날 · 한 아이, 조금 더 가까이.
      at: "home-board",
      title: "칠판이 챙겨 드려요",
      list: [
        "일주일 넘게 **관찰 기록이 없는 아이**",
        "일과를 적지 않아 **보육일지를 못 만든 날**",
        "아이마다 **가장 최근 관찰**",
      ],
    },
  ],
  "/records": [
    {
      at: "records-form",
      title: "본 장면을 그대로 적어요",
      lines: ["아이 · 날짜 · 영역을 고르고 적어요.", "판단보다 **아이의 말 · 행동**을 그대로."],
    },
    {
      at: "records-order",
      title: "이 순서로 적으면 좋아요",
      steps: ["상황", "행동", "반응", "교사 지원"],
      lines: ["순서대로 채우면 **관찰일지가 더 자세하게 작성돼요**."],
      tip: "다 안 채워도 저장돼요.",
      pad: 6,
    },
    {
      at: "records-list",
      title: "지금까지 남긴 기록",
      lines: ["이 기록으로 **관찰일지**를 만들어요."],
      tip: "한 아이 기록만 보려면 「아이별 기록」을 눌러요.",
    },
  ],
  "/routines": [
    {
      at: "journal-tabs",
      title: "보육일지는 두 쪽이에요",
      lines: [
        "여기서 일과를 적고 **오늘 보육일지**를 만들어요.",
        "한 주 일지는 「주간 보육일지」에서 만들어요.",
      ],
      pad: 6,
    },
    {
      at: "routines-calendar",
      title: "날짜를 골라요",
      lines: ["점이 찍힌 날은 **이미 적은 날**이에요.", "못 적은 날도 눌러서 적을 수 있어요."],
    },
    {
      at: "routines-board",
      title: "일과표가 미리 채워져 있어요",
      lines: ["「실제로 한 것」만 적으면 돼요.", "시간은 **시계**를 눌러 바꿔요."],
      tip: "바꾸면 시간 순서대로 다시 놓여요.",
    },
    {
      at: "routines-actions",
      title: "저장하고 보육일지로",
      lines: [
        "「오늘 일지 만들기」를 누르면 저장돼요.",
        "보육일지는 **이 화면에서 바로** 만들어요.",
      ],
      pad: 6,
    },
    {
      at: "routines-journal",
      title: "오늘 보육일지",
      lines: ["**초안**인지 **확정**됐는지 보여요.", "이어 쓰면 칠판 아래에 보육일지가 열려요."],
    },
  ],
  "/plans": [
    {
      at: "plans-theme",
      title: "월별 주제형",
      lines: ["**생활주제**를 따라 만들어요.", "연간 › 월간 › 주간 순서로 이어요."],
      tip: "연간계획안이 이미 있으면 「월간부터 시작하기」로 올려요.",
    },
    {
      at: "plans-play",
      title: "놀이 중심형",
      lines: ["**아이들 놀이**를 따라 만들어요.", "계절별 놀이로 연간 › 월간을 만들어요."],
      tip: "「연간부터 시작하기」를 누르면 만드는 순서를 먼저 보여 드려요.",
    },
    {
      at: "plans-continue",
      title: "이어서 하기",
      lines: ["확정 전 초안은 여기서 이어 써요.", "확정한 계획안은 **문서 보관함**에 모여요."],
    },
  ],
  "/documents": [
    {
      at: "archive-rail",
      title: "어느 반 문서를 볼까요",
      lines: ["**우리 반** 문서가 먼저 보여요.", "같은 원 다른 반은 **열람 요청**을 보내요."],
      tip: "담임 선생님이 승인하면 두 반이 서로 봐요.",
    },
    {
      at: "archive-types",
      title: "문서 종류를 골라요",
      lines: ["계획안 · 보육일지 · 관찰일지가", "**확정한 것도 쓰던 것도** 여기 모여요."],
      tip: "카드를 누르면 미리 보고, 열어서 이어 써요.",
    },
  ],
  "/evaluation": [
    {
      at: "eval-today",
      title: "평가 서류 도장판",
      lines: [
        "낼 서류가 **몇 칸 비었는지** 보여요.",
        "쌤플이 만들지 않는 서류는 **동그라미를 눌러** 찍어요.",
      ],
      tip: "쌤플은 서류의 개수만 세어요. 내용은 선생님께서 확인해 주세요.",
    },
    {
      at: "eval-folder",
      title: "내 컴퓨터 폴더도 찾아봐요",
      lines: ["서류를 모아 둔 폴더를 고르면", "파일 **이름만** 읽어 있는지 찾아요."],
    },
    {
      at: "eval-sheet",
      title: "채울 서류부터",
      lines: [
        "**빈 칸**인 서류가 위에 크게 나와요.",
        "도장 근거는 **쌤플확정 · 내컴퓨터 · 직접확인**으로 봐요.",
      ],
    },
  ],
  "/records/children": [
    {
      at: "child-picker",
      title: "아이를 골라요",
      lines: ["**한 아이** 관찰 기록만 모아 봐요."],
    },
    {
      at: "child-detail",
      title: "이 아이 기록 한눈에",
      lines: ["**영역마다 몇 건**인지와", "지금까지 남긴 기록이 보여요."],
      tip: "빈 영역이 있으면 다음 관찰 때 챙겨 봐요.",
    },
  ],
  // 보육일지 메뉴의 주간 탭. 「그날 기록」 칸은 제목을 되풀이하는 한 줄뿐이라 뺐다(PM 점검).
  "/weekly-records": [
    {
      at: "weekly-week",
      title: "한 주를 골라요",
      lines: ["요일마다 **일과 · 관찰 건수**가 보여요.", "점선은 아직 기록이 없는 날이에요."],
    },
    {
      at: "weekly-journal",
      title: "주간 보육일지",
      lines: ["**확정한 일일 보육일지**로 만들어요."],
      tip: "초안이 남았으면 「확정하러 가기」부터 눌러요.",
    },
    {
      at: "weekly-make",
      title: "주간 일지 만들기",
      lines: ["아직 못 만들 때 누르면", "**무엇이 모자란지** 알려 드려요."],
      pad: 6,
    },
  ],
};

type Slide = Body & { title: string };

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
        title: "요청 사항을 적고 시작해요",
        lines: [
          "반 · 연령 · 학년도는 미리 채워져 있어요.",
          "**바라는 점**을 적거나 쪽지를 눌러 넣고",
          "「연간계획안 만들기」를 눌러요.",
        ],
        tip: "같은 쪽지는 한 번만 들어가요.",
      },
      {
        title: "12달 초안이 나와요",
        lines: ["**3월부터 다음 해 2월까지**", "달마다 생활주제와 주별 소주제가 채워져요."],
        tip: "아직 초안이니 편하게 고쳐도 돼요.",
      },
      {
        title: "칸을 눌러 바로 고쳐요",
        lines: ["문서에서 칸을 누르면", "**왼쪽에** 그 달 생활주제 · 소주제가 열려요."],
        tip: "잘못 고쳤으면 되돌리기로 돌아가요.",
      },
      {
        title: "다 고쳤으면 확정해요",
        lines: [
          "「확정하기」를 누르고",
          "묻는 창에서 「확정하기」를 한 번 더 눌러요.",
          "소주제는 그 달 **주 수만큼** 있어야 확정돼요.",
        ],
        tip: "더 고칠 게 있으면 「더 다듬기」를 눌러요.",
      },
      {
        title: "내려받고 월간으로 넘어가요",
        lines: ["**PDF · 한글 파일**로 내려받아요.", "「월간계획안 만들기」로 이어 가요."],
        tip: "확정본은 여기서 못 고쳐요. 문서 보관함의 「수정하기」를 눌러요.",
      },
      {
        title: "월간은 연간을 이어받아요",
        lines: [
          "달을 고르면 **연간의 그 달 주제**로",
          "주마다 초안이 나와요.",
          "안전교육 빈칸은 「AI 후보」에서 「+」로 채워요.",
        ],
        tip: "남은 빈칸은 확정할 때 한 번 더 알려 줘요.",
      },
      {
        title: "주간은 월간을 이어받아요",
        lines: [
          "주를 고르면 요일마다 초안이 나와요.",
          "빈칸을 누르면 「AI 후보」가 떠요.",
          "「+」를 누르면 채우고 **다음 요일**로 넘어가요.",
        ],
        tip: "끌어다 놓아도 돼요. 글을 고칠 땐 「칸 편집」을 눌러요.",
      },
    ],
  },
  PLAY_PROJECT: {
    dir: "play",
    slides: [
      {
        title: "요청 사항을 적고 시작해요",
        lines: ["**바라는 놀이**를 적거나 쪽지를 눌러 넣고", "「연간계획안 만들기」를 눌러요."],
        tip: "같은 쪽지는 한 번만 들어가요.",
      },
      {
        title: "계절마다 놀이 5개를 골라요",
        lines: ["후보를 누르면 가운데에 자세히 보여요.", "「고르기」로 칠판에 **5개씩** 담아요."],
        tip: "「지금까지 고른 것으로 문서 만들기」로 먼저 볼 수도 있어요.",
      },
      {
        title: "문서에서 다듬어요",
        lines: ["칸을 눌러 「칸 편집」에서 고쳐요.", "「AI 후보」에서 놀이를 빼거나 바꿔요."],
        tip: "다른 후보를 끌어다 놓아도 바뀌어요.",
      },
      {
        title: "다 고쳤으면 확정해요",
        lines: [
          "「확정하기」를 누르고",
          "묻는 창에서 「확정하기」를 한 번 더 눌러요.",
          "**계절마다 5개**를 다 고르고 빈칸을 채워야 확정돼요.",
        ],
      },
      {
        title: "내려받고 월간으로 넘어가요",
        lines: ["**PDF · 한글 파일**로 내려받아요.", "「월간계획안 만들기」로 이어 가요."],
        tip: "다시 고치려면 문서 보관함의 「수정하기」를 눌러요.",
      },
      {
        title: "월간은 연간을 이어받아요",
        lines: ["달을 고르고, 더 집중할 놀이를 골라요.", "놀이 중심형은 **주간계획안이 없어요**."],
        tip: "놀이는 안 골라도 돼요.",
      },
      {
        title: "활동을 골라 문서로 만들어요",
        lines: ["함께 하는 활동 · 유아 예상 자유놀이를", "후보 8개 중 **5개씩** 골라요."],
        tip: "안전교육 빈칸은 「AI 후보」에서 「+」로 채우고 연간처럼 확정해요.",
      },
    ],
  },
};

/** `**낱말**` → 형광펜, 「버튼 이름」 → 버튼 모양. 그 밖은 글자 그대로. */
function Rich({ text }: { text: string }) {
  return text.split(/(\*\*[^*]+\*\*|「[^」]+」)/).map((part, i) =>
    part.startsWith("**") ? (
      <strong key={i}>{part.slice(2, -2)}</strong>
    ) : part.startsWith("「") ? (
      <span key={i} className={styles.key}>
        {part.slice(1, -1)}
      </span>
    ) : (
      part
    ),
  );
}

/** 카드 본문 — 흐름 · 번호 · 줄 · 점 목록 · TIP 순서. */
function CardBody({ body }: { body: Body }) {
  return (
    <div className={styles.body}>
      {body.flow && (
        <ol className={styles.flow}>
          {body.flow.map((line) => (
            <li key={line}>
              <Rich text={line} />
            </li>
          ))}
        </ol>
      )}
      {body.steps && (
        <ol className={styles.steps}>
          {body.steps.map((name, n) => (
            <li key={name}>
              <i>{n + 1}</i>
              {name}
            </li>
          ))}
        </ol>
      )}
      {body.lines?.map((line) => (
        <p key={line}>
          <Rich text={line} />
        </p>
      ))}
      {body.list && (
        <ul className={styles.list}>
          {body.list.map((line) => (
            <li key={line}>
              <Rich text={line} />
            </li>
          ))}
        </ul>
      )}
      {body.tip && (
        <p className={styles.tip}>
          <span>TIP</span>
          <Rich text={body.tip} />
        </p>
      )}
    </div>
  );
}

/** 몇 번째인지 · 점. 카드 맨 위 한 줄에 둔다 — 아래 줄은 버튼만 남긴다. */
function Count({ at, keys }: { at: number; keys: string[] }) {
  return (
    <div className={styles.head}>
      <p className={styles.count}>
        {at + 1} / {keys.length}
      </p>
      <span className={styles.dots} aria-hidden="true">
        {keys.map((key, n) => (
          <span key={key} data-on={n === at || undefined} />
        ))}
      </span>
    </div>
  );
}

/**
 * 카드 아래 버튼 줄 — 왼쪽 끝 SKIP, 오른쪽에 ‹ 이전 · 다음 › 한 쌍(PM 점검 안 1).
 * 이전 · 다음은 같은 크기 · 같은 보라로 붙여 짝으로 읽히게 하고, 나가기(SKIP)는 반대쪽 끝으로 뗀다.
 * SKIP 은 이 화면 안내만 닫는다. 마지막 장에는 없다.
 */
function Foot({
  at,
  total,
  done,
  onPrev,
  onNext,
  onSkip,
  nextRef,
}: {
  at: number;
  total: number;
  /** 마지막 장 버튼 글자. */
  done: string;
  onPrev: () => void;
  onNext: () => void;
  onSkip: () => void;
  nextRef: Ref<HTMLButtonElement>;
}) {
  const last = at === total - 1;
  return (
    <div className={styles.foot}>
      {last ? (
        <span className={styles.grow} />
      ) : (
        <button type="button" className={styles.skip} onClick={onSkip}>
          SKIP
        </button>
      )}
      {at > 0 && (
        <button type="button" className={styles.prev} onClick={onPrev}>
          ‹ 이전
        </button>
      )}
      <button ref={nextRef} type="button" className={styles.primary} onClick={onNext}>
        {last ? done : "다음 ›"}
      </button>
    </div>
  );
}

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

/**
 * 화면 좌표(getBoundingClientRect)를 덮개 안 style px 로 바꾼다.
 *
 * html 에 zoom(1440 기준 비례 화면)이 걸리면 getBoundingClientRect 가 그 배율을 **넣기도 하고(크롬 128+)
 * 빼기도 한다(사파리 · 옛 크롬)**. 「배율로 나눈다」고 정해 두면 빼는 브라우저에서 두 번 나눠져,
 * 구멍이 칸보다 크고 오른쪽 아래로 밀렸다(PM 점검 — 팀원 화면). 배율을 짐작하지 않고, 덮개와 같은 자리에
 * 100px 막대를 잠깐 세워 같은 자로 잰다 — 어느 브라우저든 둘이 같은 셈으로 나온다.
 */
function toLocal(box: DOMRect) {
  const ruler = document.createElement("div");
  ruler.style.cssText = "position:fixed;left:0;top:0;width:100px;height:0;visibility:hidden";
  document.body.appendChild(ruler);
  const at = ruler.getBoundingClientRect();
  ruler.remove();
  const k = at.width / 100 || 1;
  return {
    top: (box.top - at.top) / k,
    left: (box.left - at.left) / k,
    width: box.width / k,
    height: box.height / k,
  };
}

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
      const box = toLocal(el.getBoundingClientRect());
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
    // 칸 크기는 그대로인데 위쪽 내용이 늦게 그려져 칸이 밀릴 때도 따라간다.
    watch.observe(document.body);
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
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "ArrowRight") setIndex((i) => Math.min(i + 1, steps.length - 1));
      if (e.key === "ArrowLeft") setIndex((i) => Math.max(i - 1, 0));
    };
    window.addEventListener("keydown", key);
    return () => {
      document.body.style.overflow = before;
      window.removeEventListener("keydown", key);
    };
  }, [step, close, steps.length]);

  if (!step || !hole) return null;
  const last = index === steps.length - 1;

  // 칸을 가리지 않는 쪽에 둔다 — 아래 → 위 → 오른쪽 순. 다 좁으면(큰 칸) 화면 아래에 붙인다.
  const vw = window.innerWidth / appZoom();
  const vh = window.innerHeight / appZoom();
  const left = Math.min(Math.max(16, hole.left), vw - CARD - 16);
  const place =
    vh - (hole.top + hole.height) > 260
      ? { top: hole.top + hole.height + 18, left }
      : hole.top > 260
        ? { bottom: vh - hole.top + 18, left }
        : vw - (hole.left + hole.width) > CARD + 40
          ? // 위 여백은 포스티(카드 위로 40px 튀어나옴)가 화면 위에 잘리지 않을 만큼 둔다.
            { top: Math.max(52, Math.min(hole.top, vh - 300)), left: hole.left + hole.width + 24 }
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
        <Count at={index} keys={steps.map((s) => s.at)} />
        <h2 id="tour-title" className={styles.title}>
          {step.title}
        </h2>
        <CardBody body={step} />
        <Foot
          at={index}
          total={steps.length}
          done="다 봤어요"
          onPrev={() => setIndex(index - 1)}
          onNext={() => (last ? close() : setIndex(index + 1))}
          onSkip={close}
          nextRef={next}
        />
      </div>
    </div>
  );
}

/**
 * 만드는 순서를 화면 그림으로 넘겨 본다. 처음 한 번 저절로 뜨고, 「만드는 순서 보기」로 다시 연다.
 * 본 것은 위 안내와 같은 자리에 적는다(설정의 「튜토리얼 다시 보기」로 되살아난다).
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
      className={styles.corner}
      title="만드는 순서 보기"
      onClick={() => {
        setIndex(0);
        setOpen(true);
      }}
    >
      {/* 접혀 잘린 자리(책상 빛) + 접힌 종이 뒷면. 뒷면에만 그림자가 진다. */}
      <span aria-hidden="true" className={styles.cut} />
      <span aria-hidden="true" className={styles.flapShadow}>
        <span className={styles.flap}>
          <svg width="9" height="9" viewBox="0 0 24 24" className={styles.play}>
            <path d="M7 4.5v15l13-7.5-13-7.5Z" fill="currentColor" />
          </svg>
        </span>
      </span>
      <span className="sr-only">만드는 순서 보기</span>
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
          <Count at={index} keys={slides.map((s, n) => s.title + n)} />
          <h2 id="slide-title" className={styles.title}>
            {slide.title}
          </h2>
          <CardBody body={slide} />
          {/* 「다시 보지 않기」는 두지 않는다 — 계획안을 만들 때마다 순서를 다시 볼 수 있어야 한다(13주차 멘토 리뷰). */}
          <Foot
            at={index}
            total={slides.length}
            done="만들러 가기"
            onPrev={() => setIndex(index - 1)}
            onNext={() => (last ? close() : setIndex(index + 1))}
            onSkip={close}
            nextRef={next}
          />
        </div>
      </div>
    </>
  );
}
