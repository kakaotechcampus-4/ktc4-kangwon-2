/** 아이별 모아보기 전용 그림. 사진이나 아동 정보가 아닌 장식용 SVG다. */
export type ChildPortraitVariant = "neutral" | "boy" | "girl";
type HairStyle = "curly" | "crop" | "pigtails";

/** 성별 판정이 아닌 교사가 고르는 그림 프리셋. 머리 모양·옷 색은 별도로 바꿀 수 있다. */
const CHARACTER_PRESETS: Record<
  ChildPortraitVariant,
  { hair: HairStyle; shirt: string; background: string }
> = {
  neutral: { hair: "curly", shirt: "#b7d6bd", background: "#eaf2e8" },
  boy: { hair: "crop", shirt: "#f4cd85", background: "#fbf0dc" },
  girl: { hair: "pigtails", shirt: "#b8d6d5", background: "#faeae2" },
};

function ChildFigure({
  variant = "neutral",
  shirt,
  hair,
}: {
  variant?: ChildPortraitVariant;
  shirt?: string;
  hair?: HairStyle;
}) {
  const preset = CHARACTER_PRESETS[variant];
  const hairstyle = hair ?? preset.hair;
  return (
    <g>
      <path d="M17 70 11 88m42-18 8 18" stroke="#f5c6a4" strokeWidth="9" strokeLinecap="round" />
      <path d="M23 84 19 99m25-15 5 15" stroke="#a1c7d7" strokeWidth="10" strokeLinecap="round" />
      <path d="M16 97h10m17 0h10" stroke="#fffaf0" strokeWidth="8" strokeLinecap="round" />
      <path d="M15 90V72q2-17 20-17t20 17v18" fill={shirt ?? preset.shirt} />
      {hairstyle === "pigtails" && (
        <g>
          <circle cx="9" cy="36" r="10" fill="#815b47" />
          <circle cx="60" cy="36" r="10" fill="#815b47" />
          <path d="m7 30 5 5m44-3 5-3" stroke="#f0c87f" strokeWidth="3" strokeLinecap="round" />
        </g>
      )}
      <circle cx="34" cy="35" r="28" fill="#8e6450" />
      <ellipse cx="35" cy="40" rx="24" ry="23" fill="#ffdab8" />
      {hairstyle === "pigtails" && (
        <g>
          <path d="M10 35q0-32 28-28 24 4 23 30-13-2-21-17-7 16-30 15" fill="#956c54" />
          <path d="m30 11-6 15m17-14 5 13" stroke="#b68b69" strokeWidth="3" strokeLinecap="round" />
        </g>
      )}
      {hairstyle === "crop" && (
        <g>
          <path
            d="M8 34C4 13 20 4 34 9c10-8 29 5 29 22l-12-6-8 5-7-11-8 10-9-4-9 12"
            fill="#89614c"
          />
          <path d="m29 11 8-4m6 6 5 3" stroke="#ae8665" strokeWidth="3" strokeLinecap="round" />
        </g>
      )}
      {hairstyle === "curly" && (
        <g fill="#967052">
          <circle cx="15" cy="24" r="9" />
          <circle cx="24" cy="15" r="10" />
          <circle cx="37" cy="13" r="10" />
          <circle cx="49" cy="18" r="10" />
          <circle cx="56" cy="28" r="8" />
          <path d="M11 32q-6-18 11-19l33 10 6 15-9-7-7 3-9-8-8 5-8-4z" />
          <path d="m22 13 4-2m12 0 4 2" stroke="#bd9470" strokeWidth="3" strokeLinecap="round" />
        </g>
      )}
      <circle cx="26" cy="40" r="2.1" fill="#624c3f" />
      <circle cx="44" cy="40" r="2.1" fill="#624c3f" />
      <ellipse cx="19" cy="48" rx="5" ry="3.5" fill="#f6a5a0" />
      <ellipse cx="51" cy="48" rx="5" ry="3.5" fill="#f6a5a0" />
      <path d="M30 49q5 9 11 0" fill="#d77f73" />
      <path d="m25 66 10 7 10-7" fill="none" stroke="#fff8e9" strokeWidth="3" />
      <circle cx="35" cy="81" r="3" fill="#fff6e0" />
    </g>
  );
}

function Flower({ x, y, color = "#f4cb79" }: { x: number; y: number; color?: string }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <path d="M0 0v30" stroke="#8fb99b" strokeWidth="3" strokeLinecap="round" />
      <path d="M0 21q-17 0-15-11 13-1 15 11m0 5q1-16 15-15 1 11-15 15" fill="#a8cfac" />
      <g fill={color}>
        <ellipse cy="-7" rx="5" ry="7" />
        <ellipse cx="7" rx="7" ry="5" />
        <ellipse cy="7" rx="5" ry="7" />
        <ellipse cx="-7" rx="7" ry="5" />
      </g>
      <circle r="4" fill="#fff5cf" />
    </g>
  );
}

export function FlowerMeadow({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 220 88" aria-hidden="true" focusable="false">
      <path
        d="M0 88V58q10-12 24 0 12-25 30-9 14-20 30-4 22-10 33 13 18-7 28 10 23-6 36 10 24-2 39 10"
        fill="#e4edcc"
      />
      <path d="M0 88V70q21-13 39 0 13-16 30-6 20-9 35 8 26-7 39 9 29-10 45 7" fill="#cddfac" />
      <path d="M24 64V15m0 23Q-2 36 5 18q20-1 19 20m0-9Q25 4 44 6q4 19-20 23" fill="#a2c8a0" />
      <path d="M24 63V24" stroke="#80b18a" strokeWidth="2" strokeLinecap="round" />
      <Flower x={81} y={43} />
      <Flower x={117} y={63} color="#f2b8a6" />
      <Flower x={149} y={71} color="#b9d9e8" />
      <path d="M58 81V55m0 15q-17-6-15-16 15 1 15 16m0 8q2-15 14-15 0 10-14 15" fill="#accda4" />
    </svg>
  );
}

export function TrackingHeaderArt({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 460 126" aria-hidden="true" focusable="false">
      <path
        d="M0 126q9-18 29-14 8-24 30-12 17-20 34-4 27-8 33 16 21-3 32 14m143 0q13-21 30-12 15-22 35-7 22-16 38 5 30-6 56 14"
        fill="#d5e4b5"
      />
      <path d="M41 112V67m0 21Q13 87 19 68q22 0 22 20m0-10q4-25 24-19 0 17-24 19" fill="#a6c98d" />
      <path d="M41 110V74" stroke="#86b084" strokeWidth="2" />
      <g stroke="#efc66f" strokeWidth="3" strokeLinecap="round">
        <path d="M124 8v6m0 44v6M96 36h6m44 0h6M104 16l5 5m30 30 5 5m-40 0 5-5m30-30 5-5" />
      </g>
      <circle cx="124" cy="36" r="17" fill="#ffe1a0" />
      <circle cx="119" cy="35" r="1.5" fill="#c79f53" />
      <circle cx="130" cy="35" r="1.5" fill="#c79f53" />
      <path
        d="M120 41q5 5 9 0"
        fill="none"
        stroke="#d4a15b"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <path d="M285 27q-9-11 1-17 8-8 17 1 8-13 18-5 14 0 13 12 7 11-11 13h-30" fill="#dceef5" />
      <path
        d="M182 62c-18-9-19-25-10-24 6-1 9 7 9 7 9-15 22-9 17 3-3 7-10 10-16 14"
        fill="#f7b5a1"
      />
      <g transform="translate(202 16) scale(1.04)">
        <ChildFigure variant="girl" shirt="#f7ca76" />
      </g>
      <Flower x={162} y={96} color="#f3b0a9" />
      <Flower x={324} y={91} />
      <Flower x={357} y={113} color="#eeb8a8" />
      <path d="m87 70 3-6m8 13 6-1" stroke="#e6c27c" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function ChildPortrait({
  className,
  variant = "neutral",
}: {
  className?: string;
  variant?: ChildPortraitVariant;
}) {
  return (
    <svg className={className} viewBox="0 0 90 90" aria-hidden="true" focusable="false">
      <circle cx="45" cy="45" r="44" fill={CHARACTER_PRESETS[variant].background} />
      <g transform="translate(13 9) scale(.9)">
        <ChildFigure variant={variant} />
      </g>
    </svg>
  );
}

/** 영역 이름은 서버 값이다. 그림은 기록 수나 발달 수준에 따라 변하지 않는다. */
export function DomainIllustration({ tone }: { tone: string }) {
  return (
    <svg viewBox="0 0 76 76" aria-hidden="true" focusable="false">
      {tone === "play" && (
        <g>
          <ellipse cx="38" cy="66" rx="36" ry="8" fill="#dfedcc" opacity=".7" />
          <rect x="24" y="27" width="20" height="25" rx="3" fill="#ffdda8" />
          <path d="m20 28 14-19 15 19z" fill="#f5b7a8" />
          <path d="m34 9 15 19h-8L29 16z" fill="#efaa9c" />
          <rect x="10" y="46" width="16" height="18" rx="3" fill="#f9d38a" />
          <path d="m10 46 5-4h16l-5 4z" fill="#ffe7b7" />
          <rect x="36" y="43" width="17" height="20" rx="3" fill="#a5cde7" />
          <path d="m36 43 5-4h17l-5 4z" fill="#c8e2f1" />
          <path d="m53 43 5-4v20l-5 4z" fill="#8fb9d8" />
          <rect x="61" y="52" width="11" height="13" rx="2" fill="#9ecdb0" />
          <path d="m61 52 4-3 10 2-3 2z" fill="#bddfc7" />
          <path d="M62 22c-12-7-7-16 0-10 7-8 14 0 0 10" fill="#f4baa8" />
          <path d="M6 60V47m0 7q-9-1-7-8 8 0 7 8m0-5q1-8 8-7 0 6-8 7" fill="#a1cda7" />
        </g>
      )}
      {tone === "life" && (
        <g>
          <ellipse cx="38" cy="65" rx="36" ry="8" fill="#f8e8bd" opacity=".7" />
          <path d="M18 37v24m14-24v24" stroke="#f4c775" strokeWidth="5" strokeLinecap="round" />
          <ellipse cx="18" cy="29" rx="6" ry="10" fill="#ffda8e" />
          <path
            d="M27 21v9q0 8 5 8t5-8v-9m-5 0v13"
            fill="none"
            stroke="#ffda8e"
            strokeWidth="3"
            strokeLinecap="round"
          />
          <path d="M47 38h20v16q0 10-10 10T47 54z" fill="#f5b4b1" />
          <ellipse cx="57" cy="38" rx="10" ry="3" fill="#ffd4ca" />
          <path d="M67 42h3q8 0 5 9-2 5-8 4" fill="none" stroke="#f5b4b1" strokeWidth="4" />
          <path d="M54 50v-4m7 4v-4" stroke="#fff6e9" strokeWidth="3" strokeLinecap="round" />
          <ellipse cx="57.5" cy="54" rx="5" ry="4" fill="#fff6e9" />
          <circle cx="56" cy="53" r=".7" fill="#ca9691" />
          <circle cx="59" cy="53" r=".7" fill="#ca9691" />
          <path d="M58 18c-12-7-7-16 0-10 7-8 14 0 0 10" fill="#f4baa8" />
          <path d="M6 60V47m0 7q-9-1-7-8 8 0 7 8m0-5q1-8 8-7 0 6-8 7" fill="#b2cf93" />
        </g>
      )}
      {tone === "body" && (
        <g transform="translate(12 2) rotate(-9 30 38) scale(.72)">
          <path
            d="m2 43-8 2m10-11-12 1m17 25-11 3"
            stroke="#b9d9c5"
            strokeWidth="3"
            strokeLinecap="round"
          />
          <ChildFigure shirt="#a0d1cf" />
        </g>
      )}
      {tone === "talk" && (
        <g>
          <path
            d="M44 27c0 14-12 23-27 21L8 56l2-14C-6 21 8 8 23 8c13 0 21 7 21 19"
            fill="#a8c6f3"
          />
          <path
            d="M29 43c0-11 11-18 22-18s21 8 21 18c0 9-8 17-19 18l-1 8-9-10c-8-2-14-8-14-16"
            fill="#f4afbd"
          />
          <g fill="#fff">
            <circle cx="13" cy="26" r="2" />
            <circle cx="23" cy="26" r="2" />
            <circle cx="33" cy="26" r="2" />
            <circle cx="42" cy="43" r="2" />
            <circle cx="51" cy="43" r="2" />
            <circle cx="60" cy="43" r="2" />
          </g>
        </g>
      )}
      {tone === "social" && (
        <g>
          <g transform="translate(0 10) scale(.54)">
            <ChildFigure variant="boy" shirt="#b3d8b6" />
          </g>
          <g transform="translate(35 7) scale(.54)">
            <ChildFigure variant="girl" shirt="#edb7a7" />
          </g>
          <path d="M35 66c-14-8-8-18 0-11 8-9 16 0 0 11" fill="#efb998" />
        </g>
      )}
      {tone === "art" && (
        <g>
          <path
            d="M42 10C9 1-3 36 12 56c9 13 29 15 33 4 3-8-11-12-5-18 5-6 17 7 25-1 13-13-7-26-23-31"
            fill="#f8d29f"
          />
          <circle cx="20" cy="27" r="6" fill="#f2a2a5" />
          <circle cx="36" cy="20" r="6" fill="#b4c6ec" />
          <circle cx="52" cy="27" r="5" fill="#a6ceb2" />
          <circle cx="18" cy="44" r="5" fill="#f8ecb5" />
          <path d="m45 62 19-38 5 3-17 40" fill="#a7c7c4" />
          <path d="M64 26q-2-14 9-17 4 13-5 19" fill="#bb8b6a" />
          <path d="M45 62q-6 3-5 10 8 1 12-5" fill="#eeb6a6" />
        </g>
      )}
      {tone === "nature" && (
        <g>
          <path d="m47 47 19 20" stroke="#8caaa6" strokeWidth="11" strokeLinecap="round" />
          <circle cx="30" cy="29" r="23" fill="#f3fbf7" stroke="#a7ccbc" strokeWidth="6" />
          <circle cx="30" cy="29" r="18" fill="#dcefe6" />
          <path d="M30 43V24m0 9Q11 31 17 19q13 0 13 14m0-6q2-15 15-13 1 12-15 13" fill="#8fbd91" />
          <path d="m15 18 7-5" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
        </g>
      )}
      {tone === "etc" && (
        <g fill="#d9c49b">
          <path d="m38 7 7 21 22 1-18 14 6 22-17-13-18 13 6-22L8 29l23-1z" />
          <circle cx="31" cy="36" r="2" fill="#8a7653" />
          <circle cx="45" cy="36" r="2" fill="#8a7653" />
        </g>
      )}
    </svg>
  );
}

/** 문서 보관함의 장식. 기존 어린이 그림을 함께 배치하며 아동 프로필과는 연결하지 않는다. */
export function ClassFriendsArt({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 220 164" aria-hidden="true" focusable="false">
      <path d="M18 159q7-44 53-40 29-35 62-3 49-5 63 43" fill="#f0f6df" />
      <path d="M145 32q-7-14 7-18 9-10 18 1 10-14 21-3 14 0 12 13 10 10-6 13h-43" fill="#deeff3" />
      <g stroke="#f0cc86" strokeWidth="3" strokeLinecap="round">
        <path d="M32 27v-8m0 48v-8M8 43h8m32 0h8M16 27l5 5m22 22 5 5m-32 0 5-5m22-22 5-5" />
      </g>
      <circle cx="32" cy="43" r="11" fill="#ffe3a4" />
      <g transform="translate(29 58) scale(.94)">
        <ChildFigure variant="boy" shirt="#afd8c7" />
      </g>
      <g transform="translate(111 58) scale(.94)">
        <ChildFigure variant="girl" shirt="#f7d48b" />
      </g>
      <path d="M105 72c-12-8-7-17 0-10 7-8 15 1 0 10" fill="#f2c0b1" />
      <path d="m15 103 4-5m172 45 7 1" stroke="#efd290" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
