/**
 * 문서 보관함 그림. 전부 인라인 SVG 다 — 바깥 이미지를 받지 않는다.
 *
 * **문서 종류마다 다른 그림을 쓴다.** 같은 파일 모양을 돌려쓰면 교사가 지금 어느 화면에
 * 있는지 그림으로 구분할 수 없다. 시안(design-reference)의 모티프를 그대로 옮겼다.
 */

/** 폰트나 외부 에셋 없이 그리는 보관함 전용 쪽지. 다른 화면의 삽화는 그대로 둔다. */
function NoteDrawing({ tone }: { tone: "yellow" | "sage" }) {
  const yellow = tone === "yellow";
  const line = yellow ? "#c5a34d" : "#75ad92";
  return (
    <g>
      <ellipse cx="111" cy="190" rx="54" ry="7" fill="#ece3d4" />
      <g fill="none" stroke="#292820" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round">
        <path d="M72 119Q48 112 43 91m109 26q21-10 24-27M94 150q-10 19-9 35m39-34q12 15 13 34" />
        <path d="m78 186 10 1m45 0 11-1" strokeWidth="10" />
      </g>
      <circle cx="42" cy="87" r="7" fill="#292820" />
      <circle cx="177" cy="86" r="7" fill="#292820" />
      <path
        d="m66 57 83-5a3 3 0 0 1 3 3l5 82-20 21-65 2a3 3 0 0 1-3-3l-6-97a3 3 0 0 1 3-3Z"
        fill={yellow ? "#fff0aa" : "#e2f0df"}
        stroke={line}
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <path
        d="m137 158-1-20 21-1"
        fill={yellow ? "#f7d77f" : "#badac5"}
        stroke={line}
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <path d="m67 73 15-1-1-15" fill="none" stroke={line} strokeWidth="2" opacity=".7" />
      {yellow ? (
        <g fill="#292820">
          <circle cx="92" cy="97" r="3.3" />
          <circle cx="122" cy="95" r="3.3" />
        </g>
      ) : (
        <path
          d="M87 98q5-8 10 0m19-1q5-8 10 0"
          fill="none"
          stroke="#292820"
          strokeWidth="3.3"
          strokeLinecap="round"
        />
      )}
      <path
        d="M101 111q10 9 18-2"
        fill="none"
        stroke="#292820"
        strokeWidth="3.5"
        strokeLinecap="round"
      />
      <path
        d="m38 47-12-3m20-13-8-10m23 5-2-13"
        stroke="#f5bc37"
        strokeWidth="5"
        strokeLinecap="round"
      />
      <path
        d="M172 35v13m-6-6h12m10 12v10m-5-5h10"
        stroke="#aa86d0"
        strokeWidth="4"
        strokeLinecap="round"
      />
    </g>
  );
}

export function ArchiveNoteArt({
  tone = "yellow",
  className,
}: {
  tone?: "yellow" | "sage";
  className?: string;
}) {
  return (
    <svg
      className={className}
      data-art={`archive-note-${tone}`}
      viewBox="0 0 220 210"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <NoteDrawing tone={tone} />
    </svg>
  );
}

/** 반을 아직 안 골랐을 때 — 노란 쪽지가 왼쪽 반 목록을 가리킨다 (팀 포즈 "가리키기"). */
export function StartArt({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      data-art="archive-note-point"
      viewBox="0 0 220 210"
      fill="none"
      role="img"
      aria-label="왼쪽 반 목록을 가리키는 쪽지"
    >
      <ellipse cx="112" cy="190" rx="56" ry="7" fill="#ece3d4" />
      <path
        d="M72 100Q52 98 36 90M150 108q27-5 24 13-4 12-25 3M97 150l-5 31m33-31 6 31"
        stroke="#292820"
        strokeWidth="7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <g fill="#292820">
        <circle cx="30" cy="87" r="7" />
        <circle cx="150" cy="124" r="6" />
        <ellipse cx="88" cy="184" rx="10" ry="3.5" />
        <ellipse cx="135" cy="184" rx="10" ry="3.5" />
      </g>
      <path
        d="M73 50h74a3 3 0 0 1 3 3v77l-20 20H73a3 3 0 0 1-3-3V53a3 3 0 0 1 3-3Z"
        fill="#f6e7aa"
        stroke="#d5c681"
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <path
        d="M130 150v-20h20"
        fill="#e9d88e"
        stroke="#d5c681"
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <rect
        x="96"
        y="42"
        width="30"
        height="12"
        fill="#fffaf0"
        stroke="#e8dfcc"
        transform="rotate(-4 111 48)"
      />
      <circle cx="94" cy="92" r="4" fill="#292820" />
      <circle cx="120" cy="92" r="4" fill="#292820" />
      <g fill="#f5b0bb" opacity=".6">
        <ellipse cx="85" cy="105" rx="5.5" ry="3.5" />
        <ellipse cx="129" cy="105" rx="5.5" ry="3.5" />
      </g>
      <path d="M96 107q11 10 22 0" stroke="#292820" strokeWidth="3.3" strokeLinecap="round" />
      <path
        d="M15 72l-6-6m3 22H4m11 15-6 6"
        stroke="#f5bc37"
        strokeWidth="4"
        strokeLinecap="round"
      />
      <path
        d="M182 38v12m-6-6h12M198 58v9m-4.5-4.5h9"
        stroke="#aa86d0"
        strokeWidth="4"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** 문서 종류를 고르기 전 — 한 손은 허리, 다른 손과 한 발을 들어 신난 민트 쪽지. */
export function OverviewArt({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      data-art="archive-note-sage"
      viewBox="0 0 220 210"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <ellipse cx="111" cy="190" rx="54" ry="7" fill="#ece3d4" />
      <g stroke="#292820" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round">
        <path d="M66 113q-27-5-24 13 4 12 25 3m87-14q26-4 35-33M94 155q-12 19-11 31m42-31 28 23 10-10" />
        <ellipse cx="82" cy="188" rx="8" ry="2" fill="#292820" transform="rotate(6 82 188)" />
        <ellipse cx="160" cy="172" rx="7" ry="2" fill="#292820" transform="rotate(-43 160 172)" />
      </g>
      <circle cx="189" cy="79" r="7" fill="#292820" />
      <path
        d="m66 57 83-5a3 3 0 0 1 3 3l5 82-20 21-65 2a3 3 0 0 1-3-3l-6-97a3 3 0 0 1 3-3Z"
        fill="#e2f0df"
        stroke="#75ad92"
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <path
        d="m137 158-1-20 21-1"
        fill="#badac5"
        stroke="#75ad92"
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <path d="m67 73 15-1-1-15" stroke="#75ad92" strokeWidth="2" opacity=".7" />
      <circle cx="68" cy="129" r="6" fill="#292820" />
      <path
        d="m88 98 9 5-9 5m38-12-9 6 9 3"
        stroke="#292820"
        strokeWidth="3.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M101 115q10 2 20-1 0 16-10 17-10 0-10-16Z"
        fill="#f5b0bb"
        stroke="#292820"
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <path
        d="m192 50 1-14m10 19 8-10m-5 20 10-4"
        stroke="#f5bc37"
        strokeWidth="5"
        strokeLinecap="round"
      />
      <path
        d="M42 32v13m-6-6h12M23 51v13m-6-6h12"
        stroke="#aa86d0"
        strokeWidth="4"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** 관찰일지 — 돋보기와 새싹. 보육일지와 절대 같은 그림을 쓰지 않는다. */
export function ObservationArt({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 260 190" role="img" aria-label="새싹을 살펴보는 돋보기">
      <ellipse cx="125" cy="172" rx="89" ry="9" fill="#f6f8f2" />
      <path d="M54 156c-8-40 18-76 79-89 46-13 94 18 103 70v20" fill="#eef8f1" />
      <path
        d="M78 157V90m0 45q-29-17-27-33 27 2 27 33m1-16q23-28 39-17-4 20-39 36"
        fill="#a0d3b1"
      />
      <circle cx="154" cy="102" r="38" fill="#ffffff" stroke="#a6c9bb" strokeWidth="9" />
      <path
        d="m181 132 35 34"
        fill="none"
        stroke="#84b8a0"
        strokeWidth="12"
        strokeLinecap="round"
      />
      <path
        d="M144 123V93m0 15q-17-10-16-23 18 3 16 23m0-11q19-17 28-7-3 15-28 19"
        fill="#8ecfa7"
      />
      <path
        d="M105 50c-7-15-22-10-23 2-2 12 13 15 24 23 12-11 25-19 19-28-7-10-18-7-20 3"
        fill="#efd0b8"
      />
      <path
        d="m207 49 4-12m4 24 10 2m-25 3-10 8"
        stroke="#efbf79"
        strokeWidth="4"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** 보육일지 — 하루 일과(블록 · 시계 · 그릇). */
export function CareArt({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 260 190"
      role="img"
      aria-label="놀이 블록과 시계로 그린 하루 일과"
    >
      <ellipse cx="128" cy="174" rx="102" ry="9" fill="#f5f7ef" />
      <path d="M30 156C28 87 84 46 136 58c47-9 89 35 92 98" fill="#f0f8f1" />
      <rect x="90" y="116" width="63" height="48" rx="7" fill="#a4d7bc" />
      <path d="m82 116 39-34 41 34" fill="#f4b6a5" />
      <rect x="112" y="132" width="17" height="32" rx="3" fill="#f9ebd4" />
      <rect x="152" y="136" width="37" height="28" rx="5" fill="#ffdab0" />
      <rect x="161" y="125" width="17" height="14" rx="3" fill="#f8c48e" />
      <circle cx="70" cy="95" r="31" fill="#fff9ef" stroke="#efcaa6" strokeWidth="5" />
      <path d="M70 75v21l16 8" fill="none" stroke="#a9c9ad" strokeWidth="4" strokeLinecap="round" />
      <circle cx="70" cy="95" r="4" fill="#83baa0" />
      <path
        d="M35 166c-4-18 4-28 9-35m-7 17c-14-7-17-19-9-19 10 1 11 15 9 19m7-6c9-13 19-11 16-4-3 7-9 9-16 8"
        fill="#9ed4b4"
      />
      <path d="M196 157q7-23 24-21l-6 22" fill="#e9be8a" />
      <path d="M203 139q8-8 16 0" fill="none" stroke="#edc898" strokeWidth="3" />
      <circle cx="213" cy="81" r="11" fill="#ffdb9e" />
      <path d="m211 56 2-7m17 24 8-5" stroke="#f4c47e" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}

const YEAR_PALETTE = [
  ["#89c8a3", "#f3b7aa"],
  ["#9dc0e8", "#efd3a0"],
  ["#a6d9c7", "#f6d9ad"],
  ["#b6addd", "#f4c5ad"],
];

/** 연간계획안 표지 — 나무 · 새싹 · 성장. */
export function AnnualCover({ index, className }: { index: number; className?: string }) {
  const [leaf, flower] = YEAR_PALETTE[index % YEAR_PALETTE.length];
  return (
    <svg
      className={className}
      viewBox="0 0 220 88"
      preserveAspectRatio="xMidYMax meet"
      role="img"
      aria-label="나무가 자라는 연간계획 그림"
    >
      <path d="M0 81Q50 47 112 77Q175 50 220 77v11H0" fill="#d4ead6" />
      <path d="M108 78V24" stroke="#9aba92" strokeWidth="6" strokeLinecap="round" />
      <path d="M110 50Q84 26 66 42q9 25 44 20M109 40q27-34 48-11-2 28-48 24" fill={leaf} />
      <circle cx="110" cy="23" r="16" fill={flower} />
      <path d="M110 8v30M95 23h30" stroke="#fff7ed" strokeWidth="3" opacity=".8" />
      <path
        d="M56 82V62m0 8c-16-10-19-20-8-20 9 1 11 13 8 20m0-9c13-16 21-13 17-6-3 8-11 10-17 6"
        fill="#8fcc9c"
      />
      <circle cx="178" cy="63" r="8" fill="#f3d2a5" />
      <circle cx="182" cy="55" r="8" fill="#f3c1b5" />
      <circle cx="172" cy="55" r="8" fill="#f3b3ab" />
      <circle cx="178" cy="57" r="5" fill="#f3df9a" />
      <path d="m177 71 2 11" stroke="#83c3a2" strokeWidth="3" />
    </svg>
  );
}

/** 월간계획안 표지 — 그 달의 계절 풍경. */
export function MonthlyCover({ month, className }: { month: number; className?: string }) {
  const scene =
    month === 9 ? (
      <>
        <path d="M0 80Q35 55 81 77Q132 49 220 80v8H0" fill="#eecfae" />
        <path d="M103 79V35" stroke="#bf9072" strokeWidth="5" />
        <path
          d="M102 35c-39-28-48 21-20 25 14 3 16-9 20-14 24 23 52 1 39-18-12-17-31-3-39 7"
          fill="#eaaa82"
        />
        <path
          d="m160 48 13 12m-5-28 10 11m12 20 11 9"
          stroke="#f1b37d"
          strokeWidth="5"
          strokeLinecap="round"
        />
      </>
    ) : month === 8 || month === 7 ? (
      <>
        <path d="M0 62Q43 48 79 62Q117 50 157 62Q194 48 220 60V88H0" fill="#a0d8e6" />
        <path
          d="M0 75Q42 65 83 76Q121 66 164 75Q202 66 220 72"
          fill="none"
          stroke="#f6fefd"
          strokeWidth="4"
        />
        <circle cx="171" cy="23" r="17" fill="#f9d793" />
        <path d="M60 76V28" stroke="#d7aa94" strokeWidth="4" />
        <path d="M21 40q41-57 78 0Z" fill="#f0b5a1" />
        <path d="M60 40h39q-20 13-39 0" fill="#f8dcac" />
      </>
    ) : month === 6 ? (
      <>
        <path d="M0 85q55-21 105-5t115-8v16H0" fill="#cae7cb" />
        <path d="M80 80V38" stroke="#8cbd94" strokeWidth="4" />
        <path d="M80 49q-29-18-30 3 8 13 30 9m0-12q22-23 31-7-2 20-31 17" fill="#a4d9b2" />
        <circle cx="158" cy="44" r="16" fill="#ffdba2" />
        <path
          d="m157 14 0-9m27 21 8-6m-51 6-8-6"
          stroke="#f5ce86"
          strokeWidth="4"
          strokeLinecap="round"
        />
      </>
    ) : month === 5 || month === 4 ? (
      <>
        <path d="M0 82q50-25 104-6 65-19 116 0v12H0" fill="#d4ead0" />
        <path
          d="M74 82V48m0 13Q51 43 41 53q5 18 33 15m0-11q22-21 32-9-4 14-32 20"
          stroke="#8cc69c"
          strokeWidth="3"
          fill="#9fceb0"
        />
        <circle cx="72" cy="36" r="12" fill="#f4b9aa" />
        <circle cx="60" cy="42" r="12" fill="#f7d0c8" />
        <circle cx="84" cy="43" r="12" fill="#f7d0c8" />
        <circle cx="72" cy="48" r="7" fill="#f5d8a5" />
        <path d="M162 80V53" stroke="#9dccaa" strokeWidth="3" />
        <circle cx="161" cy="44" r="12" fill="#efce99" />
        <circle cx="148" cy="48" r="10" fill="#f9e9cb" />
        <circle cx="174" cy="48" r="10" fill="#f9e9cb" />
      </>
    ) : (
      <>
        <path d="M0 84Q54 51 110 79 155 59 220 77v11H0" fill="#d8ead5" />
        <path
          d="M30 72q46-88 104 0"
          fill="none"
          stroke="#f0b1a3"
          strokeWidth="9"
          strokeLinecap="round"
        />
        <path
          d="M42 72q34-66 80 0"
          fill="none"
          stroke="#f7db9f"
          strokeWidth="8"
          strokeLinecap="round"
        />
        <path
          d="M53 72q23-45 57 0"
          fill="none"
          stroke="#a2cfbe"
          strokeWidth="8"
          strokeLinecap="round"
        />
        <path
          d="M158 81V58m0 15q-16-13-20-6 4 11 20 13m0-11q17-13 21-5-3 12-21 14"
          fill="#90cba3"
        />
      </>
    );
  return (
    <svg
      className={className}
      viewBox="0 0 220 88"
      preserveAspectRatio="xMidYMax meet"
      role="img"
      aria-label={`${month}월 계절 그림`}
    >
      {scene}
    </svg>
  );
}

const WEEK_PALETTE = [
  ["#a1d3e9", "#f6b8a9"],
  ["#c8d8b9", "#f3c891"],
  ["#acc7dd", "#f7c8a1"],
  ["#bed9c9", "#b3b4de"],
  ["#b5d4a8", "#f0bdae"],
];

/** 주간계획안 표지 — 블록 · 놀이. */
export function WeeklyCover({ index, className }: { index: number; className?: string }) {
  const [a, b] = WEEK_PALETTE[index % WEEK_PALETTE.length];
  return (
    <svg
      className={className}
      viewBox="0 0 220 88"
      preserveAspectRatio="xMidYMax meet"
      role="img"
      aria-label="블록 놀이로 그린 주간계획 그림"
    >
      <path d="M0 80q55-22 109-5 58-20 111-4v17H0" fill="#e8eee1" />
      <rect x="52" y="47" width="38" height="34" rx="5" fill={a} />
      <rect x="94" y="31" width="38" height="50" rx="5" fill={b} />
      <rect x="136" y="53" width="31" height="28" rx="5" fill="#f3d5a0" />
      <rect x="62" y="39" width="18" height="10" rx="4" fill={a} />
      <rect x="104" y="24" width="18" height="9" rx="4" fill={b} />
      <path d="m158 16 12 9-12 9-12-9z" fill="#abd9c5" />
      <path
        d="M170 25q18 21 0 41"
        fill="none"
        stroke="#9dc4af"
        strokeWidth="3"
        strokeDasharray="5 6"
      />
      <path
        d="m183 14 3-7m7 16 7-1m-24 7-7 6"
        stroke="#efc38f"
        strokeWidth="4"
        strokeLinecap="round"
      />
      <circle cx="29" cy="30" r="9" fill="#f2d9a7" />
    </svg>
  );
}

/** 보육일지 헤더의 작은 해. 업무 정보와 구분되는 장식이다. */
export function CareSunArt({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <g stroke="#f2c576" strokeWidth="4" strokeLinecap="round">
        <path d="M32 5v6M32 53v6M5 32h6M53 32h6M13 13l4 4M47 47l4 4M13 51l4-4M47 17l4-4" />
      </g>
      <circle cx="32" cy="32" r="15" fill="#ffdb91" stroke="#efc478" strokeWidth="1.5" />
    </svg>
  );
}

/** 날짜 카드의 작은 새싹·하트·꽃. 상태나 평가를 나타내지 않는다. */
export function CareDayDecor({ variant, className }: { variant: number; className?: string }) {
  const ornaments = [
    <g key="sprout" fill="#bbd6ae">
      <path d="M23 42V25" fill="none" stroke="#a5c59e" strokeWidth="3" strokeLinecap="round" />
      <path d="M23 31C4 32 5 15 13 19c8 2 10 12 10 12M23 29c1-15 16-18 16-9-1 8-16 9-16 9" />
    </g>,
    <path
      key="heart"
      d="M24 39C2 26 7 10 16 15c4 2 7 7 8 9 5-16 18-17 17-4-1 8-9 15-17 19"
      fill="#f5bdb5"
    />,
    <g key="flower" fill="#f4ce86">
      <ellipse cx="24" cy="13" rx="7" ry="10" />
      <ellipse cx="34" cy="23" rx="10" ry="7" />
      <ellipse cx="28" cy="34" rx="7" ry="10" />
      <ellipse cx="14" cy="31" rx="9" ry="7" />
      <ellipse cx="12" cy="19" rx="9" ry="7" />
      <circle cx="23" cy="24" r="5" fill="#fffaf0" />
    </g>,
    <g key="leaves" fill="#b5d2aa">
      <path d="M24 43c0-11 4-23 11-31" fill="none" stroke="#a7c79f" strokeWidth="2" />
      <path d="M27 31c-19-1-23-16-14-14 8 1 14 14 14 14M28 27C23 6 40 2 39 13c0 8-11 14-11 14" />
    </g>,
    <path
      key="violet"
      d="M24 39C4 28 5 11 15 16c4 1 7 6 9 9 3-16 17-19 17-5-1 9-11 16-17 19"
      fill="#cdbde3"
    />,
  ];
  return (
    <svg className={className} viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      {ornaments[variant % ornaments.length]}
    </svg>
  );
}

/** 하단 작성 카드용 공책. 기존 인라인 SVG와 같은 파스텔 재료를 사용한다. */
export function CareNotebookArt({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 170 126" aria-hidden="true" focusable="false">
      <path
        d="M30 95C4 72 20 39 49 43c6-35 54-36 63-4 40-2 48 48 14 60-39 31-74 19-96-4"
        fill="#eef5ec"
      />
      <path
        d="M141 88V67m0 12c-17-7-17-20-10-17 9 3 10 17 10 17m0-7c3-17 17-20 17-12-1 7-17 16-17 16"
        fill="#bed8af"
      />
      <path
        d="M139 37c-15-7-16-21-8-18 4 0 6 6 7 8 4-11 12-11 11-3-1 5-5 10-10 13"
        fill="#f5c0b7"
      />
      <g transform="rotate(-9 76 68)">
        <rect
          x="42"
          y="30"
          width="67"
          height="81"
          rx="9"
          fill="#fffaf0"
          stroke="#dfc9ae"
          strokeWidth="3"
        />
        <path
          d="M52 54h40M53 70h38M53 86h27"
          stroke="#eed9ba"
          strokeWidth="3"
          strokeLinecap="round"
        />
        <path
          d="M39 45h9M39 59h9M39 73h9M39 87h9M39 101h9"
          stroke="#b7b6ab"
          strokeWidth="4"
          strokeLinecap="round"
        />
        <circle cx="67" cy="58" r="2" fill="#857764" />
        <circle cx="85" cy="58" r="2" fill="#857764" />
        <path
          d="M73 63q4 5 8 0"
          fill="none"
          stroke="#c89f8a"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </g>
      <circle cx="115" cy="93" r="22" fill="#8fc0a9" stroke="#fff" strokeWidth="3" />
      <path d="M115 82v22M104 93h22" stroke="#fff" strokeWidth="4" strokeLinecap="round" />
      <path d="M29 105c-13-7-11-16-5-13 2 1 4 4 4 5 4-11 11-9 9-3-1 4-4 8-8 11" fill="#a9cfc0" />
    </svg>
  );
}
