/**
 * 화면 뒤 벽에 연필로 끄적인 포스티 낙서(시안 캔버스 「⑧ 포스티 낙서」 · 칠판 바깥 벽).
 *
 * 화면 전체에 고정해 두고 z-index 를 음수로 둔다 — body 의 크림 바탕(캔버스) 바로 위, 모든 본문 아래.
 * 그래서 카드 · 사이드바 · 칠판처럼 제 바탕을 칠한 것 뒤로 숨고, 크림 바탕이 드러난 곳에서만 보인다.
 * 화면 틀(AppLayout 등)이 바탕을 다시 칠하면 가려지므로 틀에서는 bg-cream 을 뺐다(body 가 이미 크림이다).
 * 폭 · 높이는 --app-vw · --app-vh 로 잡는다 — 1440 비례 화면(zoom)에서도 창을 꽉 채운다.
 */
export default function PostyDoodles() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed left-0 top-0 -z-10 h-[calc(100*var(--app-vh))] w-[calc(100*var(--app-vw))] print:hidden"
    >
      <svg
        className="postyDoodles h-full w-full"
        viewBox="0 0 1920 1080"
        preserveAspectRatio="xMidYMid slice"
      >
        <filter id="posty-doodle-pencil" x="-5%" y="-5%" width="110%" height="110%">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.05"
            numOctaves={2}
            seed={3}
            result="w"
          />
          <feDisplacementMap
            in="SourceGraphic"
            in2="w"
            scale={2.5}
            xChannelSelector="R"
            yChannelSelector="G"
            result="wob"
          />
          <feTurbulence
            type="fractalNoise"
            baseFrequency="1.6"
            numOctaves={1}
            seed={6}
            result="g"
          />
          <feColorMatrix
            in="g"
            type="matrix"
            values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 -1.6 1.6"
            result="m"
          />
          <feComposite in="wob" in2="m" operator="in" />
        </filter>
        <g className="dd">
          <g transform="translate(300 240) rotate(-8) scale(1.6) translate(-24 -30)">
            <Note tone="s3" />
            <path d="M7 28L2.8 41M41 28Q47.3 20 45.6 12M18 43L17 53M30 43L31 53" />
            <circle className="f1" cx="2.8" cy="41" r="3" />
            <circle className="f1" cx="45.6" cy="12" r="3" />
            <ellipse className="f1" cx="13" cy="54" rx="4.5" ry="2.6" />
            <ellipse className="f1" cx="35" cy="54" rx="4.5" ry="2.6" />
            <Eyes />
            <path className="thin" d="M18.4 25q5.6 3.4 11.2 0" />
          </g>
          <g transform="translate(405 520) rotate(10) scale(1.8) translate(-24 -30)">
            <Note tone="s2" />
            <path d="M7 28Q1.3 23 1.6 18M41 28Q46.7 23 46.4 18M18 43L14.2 52M30 43L33.8 52" />
            <circle className="f1" cx="1.6" cy="18" r="3" />
            <circle className="f1" cx="46.4" cy="18" r="3" />
            <ellipse className="f1" cx="10.5" cy="53" rx="4.5" ry="2.6" />
            <ellipse className="f1" cx="37.5" cy="53" rx="4.5" ry="2.6" />
            <Eyes />
            <path className="thin" d="M18 24q6 4.6 12 0" />
          </g>
          <g transform="translate(290 730)">
            <path
              className="thin"
              d="M-40 -24h80q8 0 8 8v24q0 8 -8 8h-50l-12 12l2 -12h-20q-8 0 -8 -8v-24q0 -8 8 -8z"
            />
            <text className="k5 mid" y="6">
              안녕!
            </text>
          </g>
          <g transform="translate(320 905) rotate(-6) scale(1.1) translate(-24 -30)">
            <Note tone="s3" />
            <path d="M7 28L3 40M41 28L45 40M18 43L17 53M30 43L31 53" />
            <circle className="f1" cx="3" cy="40" r="3" />
            <circle className="f1" cx="45" cy="40" r="3" />
            <ellipse className="f1" cx="13" cy="54" rx="4.5" ry="2.6" />
            <ellipse className="f1" cx="35" cy="54" rx="4.5" ry="2.6" />
            <path className="thin" d="M16.4 19.4q2.2 2 4.4 0M27.2 19.4q2.2 2 4.4 0M21 26h6" />
          </g>
          <text className="k6" x="352" y="868">
            z
          </text>
          <text className="k5" x="364" y="852">
            Z
          </text>
          <g transform="translate(1610 250) rotate(6) scale(1.5) translate(-24 -30)">
            <Note tone="s2" />
            <path d="M7 28Q1.3 23 1.6 18M41 28Q46.7 23 46.4 18M18 43L14.2 52M30 43L33.8 52" />
            <circle className="f1" cx="1.6" cy="18" r="3" />
            <circle className="f1" cx="46.4" cy="18" r="3" />
            <ellipse className="f1" cx="10.5" cy="53" rx="4.5" ry="2.6" />
            <ellipse className="f1" cx="37.5" cy="53" rx="4.5" ry="2.6" />
            <Eyes />
            <path className="thin" d="M18 24q6 4.6 12 0" />
          </g>
          <g transform="translate(1515 545) rotate(-10) scale(1.8) translate(-24 -30)">
            <Note tone="s3" />
            <path d="M7 28L2.8 41M41 28Q47.3 20 45.6 12M18 43L17 53M30 43L31 53" />
            <circle className="f1" cx="2.8" cy="41" r="3" />
            <circle className="f1" cx="45.6" cy="12" r="3" />
            <ellipse className="f1" cx="13" cy="54" rx="4.5" ry="2.6" />
            <ellipse className="f1" cx="35" cy="54" rx="4.5" ry="2.6" />
            <Eyes />
            <path className="thin" d="M18.4 25q5.6 3.4 11.2 0" />
          </g>
          <Heart className="s4" transform="translate(1620 740)" />
          <path className="thin" d="M1660 712v14M1653 719h14M1586 770v10M1581 775h10" />
          <g className="f1">
            <ellipse cx="1540" cy="972" rx="4" ry="2.4" />
            <ellipse cx="1556" cy="962" rx="4" ry="2.4" />
            <ellipse cx="1574" cy="974" rx="4" ry="2.4" />
            <ellipse cx="1590" cy="964" rx="4" ry="2.4" />
            <ellipse cx="1608" cy="976" rx="4" ry="2.4" />
            <ellipse cx="1624" cy="966" rx="4" ry="2.4" />
          </g>
          <path className="dash" d="M520 994q40 -22 92 -12" />
          <g transform="translate(650 962) rotate(4) translate(-24 -30)">
            <Note tone="s3" />
            <path d="M7 28L2.8 41M41 28L45 40M18 43L12 52M30 43L35 52" />
            <Eyes />
            <path className="thin" d="M18.4 25q5.6 3.4 11.2 0" />
          </g>
          <Heart className="s4" transform="translate(985 978)" />
          <Heart className="s4" transform="translate(1022 966) scale(0.7)" />
          <g transform="translate(1330 975) scale(1.1) translate(-24 -30)">
            <Note tone="s2" />
            <path d="M7 28Q14 22 18 14M41 28Q34 22 30 14M18 43L17 53M30 43L31 53" />
            <Eyes />
            <path className="thin" d="M18 24q6 4.6 12 0" />
          </g>
          <Heart className="s4" transform="translate(1330 928) scale(0.6)" />
          <Heart className="s4 thin" transform="translate(1100 124) scale(0.5)" />
          <g transform="translate(130 150) rotate(-10) scale(1.2) translate(-24 -30)">
            <Note tone="s2" />
            <path d="M7 28L2.8 41M41 28Q47.3 20 45.6 12M18 43L17 53M30 43L31 53" />
            <Eyes />
            <path className="thin" d="M18.4 25q5.6 3.4 11.2 0" />
          </g>
          <Heart className="s4" transform="translate(160 440) rotate(-10) scale(1.15)" />
          <g transform="translate(120 800)">
            <path
              className="thin"
              d="M-34 -20h68q7 0 7 7v20q0 7 -7 7h-42l-10 10l2 -10h-18q-7 0 -7 -7v-20q0 -7 7 -7z"
            />
            <text className="k5 mid" y="5">
              최고!
            </text>
          </g>
          <Star className="s3" transform="translate(220 1010)" />
          <g transform="translate(1800 140) rotate(8) scale(1.2) translate(-24 -30)">
            <Note tone="s3" />
            <path d="M7 28Q1.3 23 1.6 18M41 28Q46.7 23 46.4 18M18 43L14.2 52M30 43L33.8 52" />
            <Eyes />
            <path className="thin" d="M18 24q6 4.6 12 0" />
          </g>
          <Sparkle transform="translate(1770 450)" />
          <g transform="translate(1830 806) rotate(12) translate(-24 -30)">
            <Note tone="s2" />
            <path d="M7 28L3 40M41 28L45 40M18 43L17 53M30 43L31 53" />
            <path className="thin" d="M16.4 19.4q2.2 2 4.4 0M27.2 19.4q2.2 2 4.4 0M21 26h6" />
          </g>
          <Heart className="s4" transform="translate(1712 1020) scale(0.85)" />
          <Heart className="s4" transform="translate(1746 1012) scale(0.6)" />
          <path className="dash" d="M540 62q30 -18 60 -6t60 -4" />
          <Star className="s3" transform="translate(1390 48) scale(0.8)" />
          <g transform="translate(600 680) rotate(-6) scale(1.3) translate(-24 -30)">
            <Note tone="s3" />
            <path d="M7 28L2.8 41M41 28Q47.3 20 45.6 12M18 43L17 53M30 43L31 53" />
            <Eyes />
            <path className="thin" d="M18.4 25q5.6 3.4 11.2 0" />
          </g>
          <Heart className="s4" transform="translate(870 770)" />
          <Heart className="s4" transform="translate(910 758) scale(0.7)" />
          <g transform="translate(1090 640) rotate(8) translate(-24 -30)">
            <Note tone="s2" />
            <path d="M7 28Q1.3 23 1.6 18M41 28Q46.7 23 46.4 18M18 43L14.2 52M30 43L33.8 52" />
            <Eyes />
            <path className="thin" d="M18 24q6 4.6 12 0" />
          </g>
          {/* 관찰 기록 「쌓인 기록」 제목과 겹쳐 위로 올렸다 */}
          <Sparkle transform="translate(1040 150)" />
          <g transform="translate(1300 232)">
            <path
              className="thin"
              d="M-34 -20h68q7 0 7 7v20q0 7 -7 7h-42l-10 10l2 -10h-18q-7 0 -7 -7v-20q0 -7 7 -7z"
            />
            <text className="k5 mid" y="5">
              안녕!
            </text>
          </g>
          <Heart className="s4" transform="translate(1450 736) scale(0.8)" />
          <Heart className="s4" transform="translate(1474 718) scale(0.5)" />
        </g>
      </svg>
    </div>
  );
}

/** 포스티 쪽지 몸 — 네모와 접힌 귀. */
function Note({ tone }: { tone: "s2" | "s3" }) {
  return (
    <>
      <path className={tone} d="M7 5H41V34L31 43H7Z" />
      <path className={tone} d="M41 34H31V43" />
    </>
  );
}

function Eyes() {
  return (
    <>
      <circle className="f1" cx="18.6" cy="19" r="2" />
      <circle className="f1" cx="29.4" cy="19" r="2" />
    </>
  );
}

function Heart({ className, transform }: { className: string; transform: string }) {
  return (
    <path
      className={className}
      transform={transform}
      d="M0 12C-26 -7 -12 -26 0 -12C12 -26 26 -7 0 12Z"
    />
  );
}

function Star({ className, transform }: { className: string; transform: string }) {
  return (
    <path
      className={className}
      transform={transform}
      d="M0 -16L4.7 -5.4L16 -4.7L7.3 2.9L10.2 14.6L0 8L-10.2 14.6L-7.3 2.9L-16 -4.7L-4.7 -5.4Z"
    />
  );
}

function Sparkle({ transform }: { transform: string }) {
  return (
    <path
      className="thin"
      transform={transform}
      d="M0 -20Q3 -3 20 0Q3 3 0 20Q-3 3 -20 0Q-3 -3 0 -20Z"
    />
  );
}
