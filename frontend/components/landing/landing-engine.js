/**
 * 소개 화면(/welcome)의 움직임 — 스크롤 진행에 따라 칠판 쪽지 · 하루 장면 · 계획안이 바뀐다.
 *
 * 화면 뼈대는 InteractiveLanding.tsx 가 그리고, 여기서는 그 위의 글자 · 표시만 바꾼다.
 * 스크롤마다 React 상태를 바꾸면 화면 전체가 다시 그려지므로, 바뀌는 칸만 직접 고친다.
 * 「움직임 줄이기」를 켠 사람에게는 완성된 상태를 바로 보여 준다.
 *
 * @returns {() => void} 화면을 떠날 때 부르는 정리 함수
 */
export function startLanding() {
  // 다시 붙을 때(개발 모드의 두 번 실행, 화면 재진입) 앞에서 만든 칸이 겹치지 않게 비운다.
  document.querySelectorAll(".lp [data-pad]").forEach((pad) => {
    pad.querySelectorAll(".pad-top, .keys").forEach((el) => el.remove());
  });
  ["kDots", "marks", "clock"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.replaceChildren();
  });
  document.querySelector(".lp #annualTable tbody")?.replaceChildren();
  document.querySelectorAll(".lp #areas label").forEach((el) => el.remove());

  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

  const ICON = {
    obs: '<svg viewBox="0 0 30 30" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 23l3-1 12-12-2-2L7 20z"/><path d="M17 9l2 2"/><path d="M6 26h18"/></svg>',
    routine:
      '<svg viewBox="0 0 30 30" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="15" cy="15" r="10"/><path d="M15 9v6l4 3"/></svg>',
    journal:
      '<svg viewBox="0 0 30 30" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M8 4h10l5 5v17H8z"/><path d="M12 14h7M12 18h7M12 22h4"/></svg>',
    eval: '<svg viewBox="0 0 30 30" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 9l2 2 4-4M6 19l2 2 4-4"/><path d="M15 9h9M15 19h9"/></svg>',
    plan: '<svg viewBox="0 0 30 30" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="5" y="7" width="20" height="18" rx="3"/><path d="M5 12h20M10 4v5M20 4v5M10 17h3M17 17h3M10 21h3"/></svg>',
  };
  const KEYS = [
    {
      id: "obs",
      name: "관찰 기록",
      sub: "본 대로 한 줄",
      peek: '<span class="pk-hand">도토리를 크기별로<br>줄 세웠다.</span>',
    },
    {
      id: "routine",
      name: "일과 기록",
      sub: "칠판에 쪽지로",
      peek: '<span class="pk-list"><span><i>09:20</i>실내놀이</span><span><i>11:00</i>바깥놀이</span></span>',
    },
    {
      id: "journal",
      name: "보육일지",
      sub: "적은 기록으로 초안",
      peek: '<span class="pk-lock">적은 그대로</span><span class="pk-lines"><i></i><i></i></span>',
    },
    {
      id: "eval",
      name: "평가 점검",
      sub: "서류를 한 장에",
      peek: '<span class="pk-bars"><span>보육일지<i style="--w:76%"></i></span><span>계획안<i style="--w:100%"></i></span><span>관찰<i style="--w:45%"></i></span></span>',
    },
    {
      id: "plan",
      name: "계획안",
      sub: "연간 → 월간 → 주간",
      wide: true,
      peek: '<span class="pk-months"><i>3월 우리 원과 친구</i><i>4월 따뜻한 봄</i><i>5월 소중한 나와 가족</i></span>',
    },
  ];
  document.querySelectorAll("[data-pad]").forEach((pad) => {
    pad.insertAdjacentHTML(
      "beforeend",
      '<div class="pad-top" aria-hidden="true"><b>Ssample<i>.</i></b><span class="pad-holes"><span></span><span></span><span></span></span></div><div class="keys"></div>',
    );
    const keys = pad.querySelector(".keys");
    const decorative = pad.id === "miniPad";
    KEYS.forEach((k) => {
      const b = document.createElement(decorative ? "div" : "button");
      if (!decorative) {
        b.type = "button";
        b.setAttribute("aria-label", `${k.name} 설명으로 이동`);
      }
      b.className = `key k-${k.id}${k.wide ? " wide" : ""}`;
      b.dataset.key = k.id;
      b.innerHTML = `<span class="k-head"><span><b>${k.name}</b><small>${k.sub}</small></span>${ICON[k.id]}</span><span class="k-peek">${k.peek}</span>`;
      keys.appendChild(b);
    });
  });

  /* 첫 화면: 실제 화면 두 대가 포인터를 따라 살짝 기운다 */
  const hero = document.getElementById("hero");
  const heroPad = document.getElementById("heroDevices");
  if (!reduce) {
    hero.addEventListener("pointermove", (e) => {
      if (e.pointerType !== "mouse") return;
      const r = hero.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5,
        y = (e.clientY - r.top) / r.height - 0.5;
      heroPad.style.setProperty("--ry", `${x * 4}deg`);
      heroPad.style.setProperty("--rx", `${-y * 3}deg`);
    });
    hero.addEventListener("pointerleave", () => {
      heroPad.style.removeProperty("--ry");
      heroPad.style.removeProperty("--rx");
    });
  }
  /* 고정 구간 안의 한 지점으로 스크롤한다 (frac 0~1) */
  function jump(el, frac) {
    const top = el.offsetTop + (el.offsetHeight - innerHeight) * frac + 2;
    scrollTo({ top, behavior: reduce ? "auto" : "smooth" });
  }

  const progressOf = (el) => {
    const r = el.getBoundingClientRect();
    return clamp(-r.top / (el.offsetHeight - innerHeight), 0, 1);
  };

  /* 2. 쪽지 다섯 장 */
  const STEPS = [
    {
      key: "obs",
      no: "1 · 관찰 기록",
      title: "본 대로,<br>한 줄이면 충분해요.",
      text: "아이와 영역을 고르고 본 장면을 적어요. 손이 바쁠 땐 말로 적어도 돼요.",
    },
    {
      key: "routine",
      no: "2 · 일과 기록",
      title: "오늘 일과는<br>칠판에 쪽지로.",
      text: "시간을 바꾸면 순서대로 정리되고, 겹치는 시간은 저장하기 전에 알려 줘요.",
    },
    {
      key: "journal",
      no: "3 · 보육일지",
      title: "사실은 그대로,<br>문장은 초안으로.",
      text: "선생님이 적은 문장은 고치지 않고 그대로 넣어요. 쌤플은 나머지 칸만 초안으로 채워요.",
    },
    {
      key: "plan",
      no: "4 · 계획안",
      title: "연간이 월간을,<br>월간이 주간을.",
      text: "확정한 계획이 다음 계획의 재료가 돼요. 한글 파일로 바로 내려받아요.",
    },
    {
      key: "eval",
      no: "5 · 평가 점검",
      title: "평가 받을 서류,<br>지금 몇 장인지.",
      text: "지표별로 모인 서류와 부족한 서류를 확인해요. 개수만 세고 내용은 확인하지 않아요.",
    },
  ];
  const kNo = document.getElementById("kNo"),
    kTitle = document.getElementById("kTitle"),
    kText = document.getElementById("kText");
  const keysSec = document.getElementById("keys");
  const keyFrac = (i) => 0.06 + ((i + 0.5) / 5) * 0.94;
  const kDotsBox = document.getElementById("kDots");
  const STEP_KEYS = ["obs", "routine", "journal", "plan", "eval"];
  STEPS.forEach((s, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("aria-label", `${s.no} 단계로 이동`);
    b.innerHTML = "<i></i>";
    b.addEventListener("click", () => jump(keysSec, keyFrac(i)));
    kDotsBox.appendChild(b);
  });
  const kDots = [...kDotsBox.children];
  const jumpKey = (key) => jump(keysSec, keyFrac(STEP_KEYS.indexOf(key)));
  document.getElementById("boardPad").addEventListener("click", (e) => {
    const k = e.target.closest(".key");
    if (k) jumpKey(k.dataset.key);
  });
  const boardKeys = [...document.querySelectorAll("#boardPad .key")];
  const chips = [...document.querySelectorAll(".chip")];
  let kIdx = -2,
    kTimer;
  function setKeyStep(i) {
    if (i === kIdx) return;
    kIdx = i;
    const s = STEPS[i];
    [kTitle, kText].forEach((el) => el.classList.add("out"));
    clearTimeout(kTimer);
    kTimer = setTimeout(
      () => {
        kNo.textContent = s ? s.no : "쪽지 다섯 장";
        kTitle.innerHTML = s ? s.title : "한 장마다,<br>하는 일이 하나씩.";
        kText.textContent = s ? s.text : "스크롤하면 쪽지가 한 장씩 앞으로 나와요.";
        [kTitle, kText].forEach((el) => el.classList.remove("out"));
      },
      reduce ? 0 : 220,
    );
    kDots.forEach((d, j) => d.classList.toggle("on", j === i));
    boardKeys.forEach((k) => k.classList.toggle("on", !!s && k.dataset.key === s.key));
    chips.forEach((c) => {
      c.classList.toggle("lit", !!s && c.dataset.for === s.key);
      c.classList.toggle("dim", !!s && c.dataset.for !== s.key);
    });
  }

  /* 3. 하루 */
  const SCENES = [
    {
      t: "0850",
      ampm: "am",
      scene: "등원 · 바깥놀이",
      sub: "수요일 아침",
      key: "obs",
      cap: "누름 · 관찰 기록",
      title: "관찰 기록",
      quote: "도토리를 크기별로 줄 세우네. 잊기 전에 한 줄만 적어 두자.",
      bg: "#fffdf8",
      night: false,
    },
    {
      t: "1040",
      ampm: "am",
      scene: "오전 간식 · 일과 정리",
      sub: "같은 날",
      key: "routine",
      cap: "누름 · 일과 기록",
      title: "일과 기록",
      quote: "오늘 일과는 어제랑 거의 같으니까, 기본 하루를 불러오면 되겠다.",
      bg: "#eef4ee",
      night: false,
    },
    {
      t: "0120",
      ampm: "pm",
      scene: "낮잠 시간",
      sub: "40분의 틈",
      key: "journal",
      cap: "누름 · 보육일지",
      title: "보육일지 초안",
      quote: "낮잠 시간 40분. 오늘 일지 초안부터 열어 보자.",
      bg: "#f1ebf6",
      night: false,
    },
    {
      t: "0330",
      ampm: "pm",
      scene: "오후 놀이 뒤",
      sub: "한 아이씩 돌아보기",
      key: "journal",
      cap: "누름 · 관찰일지",
      title: "관찰일지",
      quote: "이번 달 아이 A 기록이 세 건 모였네. 관찰일지로 묶어 보자.",
      bg: "#fbf3df",
      night: false,
    },
    {
      t: "0540",
      ampm: "pm",
      scene: "하원 뒤",
      sub: "퇴근 전 30분",
      key: "journal",
      cap: "확정 · 한글 파일",
      title: "보육일지 · 확정",
      quote: "사실 칸은 내가 적은 그대로네. 두 줄만 고치고 확정.",
      bg: "#3a3631",
      night: true,
    },
    {
      t: "0400",
      ampm: "pm",
      scene: "금요일 오후",
      sub: "한 주 마무리",
      key: "routine",
      cap: "누름 · 주간 기록",
      title: "주간 기록",
      quote: "이번 주는 빈 날이 없네. 주간 일지도 바로 만들자.",
      bg: "#2b332e",
      night: true,
    },
  ];
  const clock = document.getElementById("clock");
  const digits = [];
  const mkDigit = () => {
    const d = document.createElement("span");
    d.className = "digit";
    const col = document.createElement("span");
    for (let n = 0; n < 10; n++) {
      const b = document.createElement("b");
      b.textContent = n;
      col.appendChild(b);
    }
    d.appendChild(col);
    clock.appendChild(d);
    digits.push(col);
  };
  mkDigit();
  mkDigit();
  clock.insertAdjacentHTML("beforeend", '<span class="colon">:</span>');
  mkDigit();
  mkDigit();
  const ampm = document.createElement("span");
  ampm.className = "ampm";
  clock.appendChild(ampm);
  const day = document.getElementById("day");
  const scene = document.getElementById("scene"),
    typed = document.getElementById("typed"),
    rest = document.getElementById("rest");
  const views = [...document.querySelectorAll(".view")];
  const winTitle = document.getElementById("winTitle"),
    miniCap = document.getElementById("miniCap"),
    trackDot = document.getElementById("trackDot");
  const miniKeys = [...document.querySelectorAll("#miniPad .key")];
  const obsLine = document.getElementById("obsLine");
  const OBS = "바깥놀이에서 도토리를 크기별로 줄 세웠다. 친구가 와서 같이 세웠다.";
  const slips = [...document.querySelectorAll("#chalk .slip")];
  const gen1 = document.getElementById("gen1"),
    gen2 = document.getElementById("gen2"),
    stamp = document.getElementById("stamp");
  const weekDays = [...document.querySelectorAll("#week div")];
  const ojPicks = [...document.querySelectorAll("#ojPicks span")];
  const oj1 = document.getElementById("oj1"),
    oj2 = document.getElementById("oj2");
  const dayLabel = document.getElementById("dayLabel");
  const daySec = document.getElementById("day");
  const MARKS = ["08:50", "10:40", "1:20", "3:30", "5:40", "금 4:00"];
  const marksBox = document.getElementById("marks");
  MARKS.forEach((m, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = m;
    b.setAttribute("aria-label", `${m} 장면으로 이동`);
    b.addEventListener("click", () => jump(daySec, (i + 0.82) / SCENES.length));
    marksBox.appendChild(b);
  });
  const marks = [...marksBox.children];
  let sIdx = -1;
  function setScene(i) {
    if (i === sIdx) return;
    sIdx = i;
    const s = SCENES[i];
    [...s.t].forEach((c, j) => {
      digits[j].style.transform = `translateY(${-Number(c)}em)`;
    });
    ampm.textContent = s.ampm;
    scene.innerHTML = `${s.scene}<small>${s.sub}</small>`;
    day.style.setProperty("--bg", s.bg);
    day.classList.toggle("night", s.night);
    trackDot.style.setProperty("--tp", `${(i / (SCENES.length - 1)) * 100}%`);
    views.forEach((v) => v.classList.toggle("on", Number(v.dataset.view) === i));
    winTitle.textContent = s.title;
    miniCap.textContent = s.cap;
    miniKeys.forEach((k) => k.classList.toggle("on", k.dataset.key === s.key));
    dayLabel.textContent = `${i + 1} / ${SCENES.length} · 하루 예시 · 시간을 누르면 그 장면으로 가요`;
    marks.forEach((m, j) => m.classList.toggle("on", j === i));
  }
  function sceneProgress(i, lp) {
    const s = SCENES[i];
    const n = reduce ? s.quote.length : Math.round(clamp(lp * 1.8, 0, 1) * s.quote.length);
    typed.textContent = s.quote.slice(0, n);
    rest.textContent = s.quote.slice(n);
    const a = reduce ? 1 : clamp((lp - 0.2) * 1.6, 0, 1);
    if (i === 0) obsLine.textContent = OBS.slice(0, Math.round(a * OBS.length));
    if (i === 1) slips.forEach((sl, j) => sl.classList.toggle("in", a > j / slips.length));
    if (i === 2) {
      gen1.classList.toggle("in", a > 0.3);
      gen2.classList.toggle("in", a > 0.7);
    }
    if (i === 3) {
      ojPicks.forEach((pk, j) => pk.classList.toggle("in", a > j * 0.12));
      oj1.classList.toggle("in", a > 0.45);
      oj2.classList.toggle("in", a > 0.75);
    }
    if (i === 4) stamp.classList.toggle("in", a > 0.35);
    if (i === 5)
      weekDays.forEach((d, j) => {
        const on = a > j / weekDays.length;
        d.classList.toggle("fill", on);
        d.querySelector("em").textContent = on ? `일과 6 · 관찰 ${[2, 2, 2, 1, 2][j]}` : "기록 전";
      });
  }

  /* 4. 계획안 — 테스트 계정에서 실제로 만든 2026학년도 연간계획안 */
  const ANNUAL = [
    [3, "우리 원과 친구", "우리 반 공간과 놀잇감 · 함께 지내는 선생님과 친구 · 우리 원의 하루"],
    [4, "따뜻한 봄", "봄 날씨와 옷차림 · 새싹과 봄꽃 · 봄에 만나는 작은 동물"],
    [
      5,
      "소중한 나와 가족",
      "나의 몸과 움직임 · 내가 좋아하는 것과 나의 마음 · 우리 가족의 다양한 모습",
    ],
    [
      6,
      "우리가 사는 동네",
      "우리 동네의 길과 건물 · 물건을 사고파는 가게 · 함께 이용하는 동네 공간",
    ],
    [7, "더운 여름", "여름 날씨와 생활 · 여름의 식물과 동물 · 물과 함께하는 놀이"],
    [8, "여러 가지 탈것", "땅에서 다니는 탈것 · 물에서 다니는 탈것 · 하늘을 나는 탈것"],
    [
      9,
      "우리나라와 세계 여러 나라",
      "우리나라의 옷과 음식 · 전통 놀이와 가락 · 세계 여러 나라의 집과 음식",
    ],
    [10, "가을과 자연", "가을 날씨와 생활 · 가을 나뭇잎의 색과 모양 · 가을 열매와 곡식"],
    [11, "우리 주변 환경과 생활", "생활 속 물과 흙 · 주변의 공기와 바람 · 우리 주변의 빛과 소리"],
    [12, "추운 겨울", "겨울 날씨와 풍경 · 따뜻한 옷과 겨울용품 · 눈과 얼음의 모습"],
    [
      1,
      "생활 속 여러 도구",
      "먹고 씻을 때 쓰는 도구 · 청소와 정리를 돕는 도구 · 소식을 전하는 도구",
    ],
    [
      2,
      "한 뼘 더 자란 우리",
      "어릴 때와 지금의 나 · 스스로 할 수 있는 일 · 새로운 반에서 궁금한 것",
    ],
  ];
  const tbody = document.querySelector("#annualTable tbody");
  ANNUAL.forEach(([m, th, sub]) =>
    tbody.insertAdjacentHTML(
      "beforeend",
      `<tr><td class="m">${m}월</td><td class="th">${th}</td><td>${sub}</td></tr>`,
    ),
  );
  const aRows = [...tbody.querySelectorAll("tr")];
  const planSec = document.getElementById("plan");
  const PHASES = [
    {
      id: "annual",
      no: "계획안 · 1 / 3",
      title: "누르면,<br><em>1년 계획</em>이<br>채워져요.",
      sub: "월별 주제형과 놀이 중심형 중에서 고르면 연간 계획안 초안이 만들어져요.",
      prompt: "2026학년도 · 햇살반 · 월별 주제형",
      go: "연간 계획안 만들기",
      head: "2026학년도 연간 보육계획안",
      checks: [
        "반 정보 읽기 · 만 4세",
        "달마다 생활주제 고르기",
        "주별 소주제 채우기",
        "법정 교육 · 칸 검사",
        "초안 완성, 읽고 고친 뒤 확정",
      ],
    },
    {
      id: "monthly",
      no: "계획안 · 2 / 3",
      title: "연간을 이어받아<br><em>한 달</em>이<br>채워져요.",
      sub: "확정한 연간 11월 주제를 바탕으로 주별 놀이를 채우고, 안전교육도 함께 계획해요.",
      prompt: "11월 · 햇살반 · 연간에서 이어받기",
      go: "11월 월간계획안 만들기",
      head: "11월 월간계획안 · 초안",
      checks: [
        "연간 11월 주제 이어받기",
        "주별 바깥놀이 채우기",
        "법정 안전교육 후보 8개 고르기",
        "후보를 주별로 놓기",
        "초안 완성, 칸을 눌러 고치기",
      ],
    },
    {
      id: "weekly",
      no: "계획안 · 3 / 3",
      title: "월간을 이어받아<br><em>요일마다</em><br>채워져요.",
      sub: "확정한 월간 계획안의 한 주를 이어받아 월요일부터 금요일까지 내용을 채워요. 마음에 들지 않는 요일은 다시 만들어요.",
      prompt: "11월 1주 · 월~금",
      go: "주간 계획안 만들기",
      head: "11월 1주 주간계획안 · 예시",
      checks: [
        "월간 1주 이어받기",
        "요일마다 놀이 활동",
        "요일별로 다시 만들기",
        "한글 파일로 내려받기",
      ],
    },
  ];
  const pNo = document.getElementById("pNo"),
    pTitle = document.getElementById("pTitle"),
    pSub = document.getElementById("pSub");
  const pPrompt = document.getElementById("pPrompt"),
    pGo = document.getElementById("pGo"),
    checksBox = document.getElementById("checks");
  const titleWrap = document.getElementById("plan-title");
  const planViews = {
    annual: document.getElementById("annualView"),
    monthly: document.getElementById("monthlyView"),
    weekly: document.getElementById("weeklyView"),
    real: document.getElementById("realView"),
  };
  const segBtns = [...document.querySelectorAll(".seg button")];
  const sheetTitle = document.getElementById("sheetTitle");
  const chain = {
    annual: document.getElementById("chA"),
    monthly: document.getElementById("chM"),
    weekly: document.getElementById("chW"),
  };
  const BOUNDS = [0, 0.36, 0.72, 1];
  let phase = -1,
    showReal = false,
    pTimer;
  function showView(id) {
    Object.entries(planViews).forEach(([k, v]) => {
      v.hidden = k !== id;
    });
    segBtns.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.plan === id)));
    if (id === "real") {
      const monthly = PHASES[phase] && PHASES[phase].id !== "annual";
      document.getElementById("realAnnual").hidden = monthly;
      document.getElementById("realMonthly").hidden = !monthly;
      document.getElementById("realCap").textContent =
        `테스트 계정에서 실제로 만든 ${monthly ? "11월 월간" : "연간"} 계획안 화면이에요.${PHASES[phase] && PHASES[phase].id === "weekly" ? " 주간 실제 화면은 아직 없어 월간을 보여 드려요." : ""}`;
      sheetTitle.textContent = `실제 화면 · ${monthly ? "월간" : "연간"} 계획안`;
      return;
    }
    sheetTitle.textContent = PHASES.find((x) => x.id === id).head;
  }
  function setPhase(i) {
    if (i === phase) return;
    phase = i;
    const ph = PHASES[i];
    [titleWrap, pSub].forEach((el) => el.classList.add("out"));
    clearTimeout(pTimer);
    pTimer = setTimeout(
      () => {
        pNo.textContent = ph.no;
        pTitle.innerHTML = ph.title;
        pSub.textContent = ph.sub;
        pPrompt.textContent = ph.prompt;
        pGo.textContent = ph.go;
        checksBox.innerHTML = ph.checks.map((c) => `<div>${c}</div>`).join("");
        [titleWrap, pSub].forEach((el) => el.classList.remove("out"));
      },
      reduce ? 0 : 200,
    );
    Object.entries(chain).forEach(([k, el]) => el.classList.toggle("on", k === ph.id));
    showReal = false;
    showView(ph.id);
  }
  const typeCells = (root, a) => {
    const cells = [...root.querySelectorAll("[data-type]")];
    cells.forEach((c, j) => {
      const s = c.dataset.type,
        start = (j / cells.length) * 0.75,
        k = clamp((a - start) / 0.25, 0, 1);
      c.textContent = s.slice(0, Math.round(k * s.length));
    });
  };
  const slots = [...document.querySelectorAll("#monthlyView .slot")];
  const cands = [...document.querySelectorAll("#pool [data-cand]")];
  function planProgress(p) {
    const i = p < BOUNDS[1] ? 0 : p < BOUNDS[2] ? 1 : 2;
    setPhase(i);
    const a = reduce ? 1 : clamp(((p - BOUNDS[i]) / (BOUNDS[i + 1] - BOUNDS[i])) * 1.3, 0, 1);
    [...checksBox.children].forEach((c, j, all) =>
      c.classList.toggle("done", a > (j + 0.5) / all.length),
    );
    if (showReal) return;
    if (i === 0)
      aRows.forEach((r, j) => r.classList.toggle("in", a > 0.1 + (j / aRows.length) * 0.8));
    if (i === 1) {
      document.querySelector("#monthlyView .inherit").classList.toggle("in", a > 0.08);
      typeCells(document.getElementById("monthlyView"), clamp(a * 1.8, 0, 1));
      slots.forEach((s, j) => {
        const on = a > 0.6 + j * 0.09;
        s.classList.toggle("filled", on);
        s.textContent = on ? cands[j].lastChild.textContent : "";
        cands[j].classList.toggle("used", on);
      });
    }
    if (i === 2) typeCells(document.getElementById("weeklyView"), a);
  }
  segBtns.forEach((b) =>
    b.addEventListener("click", () => {
      const v = b.dataset.plan;
      if (v === "real") {
        showReal = !showReal;
        showView(showReal ? "real" : PHASES[phase].id);
        if (!showReal) planProgress(progressOf(planSec));
        return;
      }
      const i = PHASES.findIndex((x) => x.id === v);
      showReal = false;
      jump(planSec, BOUNDS[i] + (BOUNDS[i + 1] - BOUNDS[i]) * 0.85);
    }),
  );

  /* 5. 비교 토글 */
  const compare = document.getElementById("compare"),
    toggle = document.getElementById("toggle");
  toggle.querySelectorAll("button").forEach((b) =>
    b.addEventListener("click", () => {
      const ours = b.dataset.side === "b";
      toggle
        .querySelectorAll("button")
        .forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      toggle.classList.toggle("right", ours);
      compare.classList.toggle("ours", ours);
    }),
  );

  /* 직접 써 보기 — 서버도 AI 도 부르지 않는다. 초안 두 줄은 영역마다 정해 둔 예시다 */
  const AREAS = [
    [
      "신체운동·건강",
      "몸을 움직여 스스로 방법을 찾아보는 모습이 나타났다.",
      "바깥놀이 시간에 같은 움직임을 다시 해 볼 수 있도록 공간을 마련한다.",
    ],
    [
      "의사소통",
      "자신의 생각을 말로 표현하고 친구의 말에 귀 기울이는 모습을 보였다.",
      "그림책과 이야기 나누기로 말한 내용을 이어 가도록 지원한다.",
    ],
    [
      "사회관계",
      "친구와 함께 놀이하며 차례와 양보를 경험하는 모습을 보였다.",
      "함께 해결하는 놀이를 이어 갈 수 있도록 모둠 자리를 마련한다.",
    ],
    [
      "예술경험",
      "색과 소리, 움직임을 자기 방식으로 표현해 보는 모습이 나타났다.",
      "다양한 재료를 더 준비해 표현을 넓혀 갈 수 있도록 한다.",
    ],
    [
      "자연탐구",
      "주변 사물과 자연을 살펴보며 차이를 비교하고 탐색하는 모습을 보였다.",
      "같은 재료로 다른 방법을 시도해 볼 수 있도록 준비한다.",
    ],
  ];
  const areasBox = document.getElementById("areas"),
    tryLine = document.getElementById("tryLine");
  const tryFact = document.getElementById("tryFact"),
    tryPlay = document.getElementById("tryPlay"),
    tryNext = document.getElementById("tryNext");
  AREAS.forEach(([name], i) =>
    areasBox.insertAdjacentHTML(
      "beforeend",
      `<label><input type="radio" name="area" value="${i}"${i === 4 ? " checked" : ""}>${name}</label>`,
    ),
  );
  function renderTry() {
    const fact = tryLine.value.trim();
    tryFact.textContent = fact || "적은 문장이 여기에 그대로 들어가요";
    tryFact.style.color = fact ? "" : "var(--ink-soft)";
  }
  let tryPlayRef = tryPlay,
    tryNextRef = tryNext;
  tryLine.addEventListener("input", renderTry);
  areasBox.addEventListener("change", () => {
    renderDraftRefs();
  });
  function renderDraftRefs() {
    const [name, play, next] = AREAS[Number(areasBox.querySelector("input:checked").value)];
    [
      [tryPlayRef, `초안 예시 · ${name}`, play, "p"],
      [tryNextRef, "초안 예시", next, "n"],
    ].forEach(([row, tag, text, which]) => {
      const fresh = row.cloneNode(true);
      fresh.querySelector("span").innerHTML = `<em>${tag}</em>${text}`;
      row.replaceWith(fresh);
      if (which === "p") tryPlayRef = fresh;
      else tryNextRef = fresh;
    });
  }
  document.getElementById("tryForm").addEventListener("submit", (e) => e.preventDefault());
  renderTry();
  renderDraftRefs();

  /* 머리 메뉴: 지금 보고 있는 구간 */
  const navLinks = [...document.querySelectorAll(".nav-links a")];
  const phones = document.getElementById("phones");
  const secs = navLinks.map((a) => document.getElementById(a.dataset.sec));

  /* 스크롤 한 번에 전부 갱신 */
  const pins = [...document.querySelectorAll("[data-pin]")];
  const progress = document.getElementById("progress"),
    nav = document.getElementById("nav");
  let ticking = false;
  function update() {
    ticking = false;
    const max = document.documentElement.scrollHeight - innerHeight;
    progress.style.setProperty("--sp", (scrollY / max).toFixed(4));
    nav.classList.toggle("solid", scrollY > 20);
    let darkNav = false;
    pins.forEach((el) => {
      const r = el.getBoundingClientRect();
      const under = r.top <= 30 && r.bottom >= 30;
      const p = progressOf(el);
      if (el.dataset.pin === "keys") {
        if (under) darkNav = true;
        setKeyStep(p < 0.06 ? -1 : Math.min(4, Math.floor(((p - 0.06) / 0.94) * 5)));
      }
      if (el.dataset.pin === "day") {
        const f = p * SCENES.length;
        const i = Math.min(SCENES.length - 1, Math.floor(f));
        setScene(i);
        sceneProgress(i, f - i);
        if (under && SCENES[i].night) darkNav = true;
      }
      if (el.dataset.pin === "plan") {
        planProgress(p);
        if (under) darkNav = true;
      }
    });
    nav.classList.toggle("dark", darkNav);
    const pr = phones.getBoundingClientRect();
    phones.style.setProperty(
      "--fan",
      reduce ? 1 : clamp((innerHeight - pr.top) / (innerHeight * 0.8), 0, 1).toFixed(3),
    );
    const mid = innerHeight * 0.4;
    navLinks.forEach((a, j) => {
      const r = secs[j].getBoundingClientRect();
      a.classList.toggle("on", r.top <= mid && r.bottom > mid);
    });
  }
  const onScroll = () => {
    if (!ticking) {
      ticking = true;
      requestAnimationFrame(update);
    }
  };
  addEventListener("scroll", onScroll, { passive: true });
  addEventListener("resize", update);
  update();
  return () => {
    removeEventListener("scroll", onScroll);
    removeEventListener("resize", update);
    clearTimeout(kTimer);
    clearTimeout(pTimer);
  };
}
