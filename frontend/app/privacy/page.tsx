import LegalPage, { LegalSection } from "@/components/legal/LegalPage";

export const metadata = {
  title: "개인정보처리방침 · 쌤플",
  description: "쌤플이 무엇을 저장하고, 어디로 보내고, 어떻게 지우는지 적어 둔 문서입니다.",
};

export default function Page() {
  return (
    <LegalPage title="개인정보처리방침" updated="2026년 10월 27일">
      <p>
        쌤플(Ssample)은 강원대학교 카카오테크캠퍼스 4기 2팀이 만드는 교육 프로젝트입니다. 어린이집
        교사가 보육 문서 초안을 쓰는 데 쓰입니다. 아래는 쌤플이 무엇을 저장하고, 어디로 보내고, 언제
        지우는지 적은 것입니다.
      </p>

      <LegalSection heading="1. 무엇을 저장하나요">
        <ul className="list-disc space-y-1 pl-5">
          <li>교사 계정 — 이메일, 이름, 비밀번호(원문이 아니라 scrypt 해시로만 저장합니다)</li>
          <li>기관 정보 — 어린이집 이름, 반 이름, 원장·담임 이름처럼 문서 결재란에 들어가는 값</li>
          <li>아동 정보 — 아동 이름과 반 소속</li>
          <li>교사가 적은 기록 — 일과 기록, 관찰 기록, 만들어진 보육일지·관찰일지·계획안</li>
        </ul>
        <p>주민등록번호, 연락처, 주소, 아동 사진은 받지 않습니다. 결제 정보도 받지 않습니다.</p>
      </LegalSection>

      <LegalSection heading="2. 아동 이름은 AI 에 보내지 않습니다">
        <p>
          문서 초안은 외부 인공지능 모델로 만듭니다. 이때{" "}
          <strong>아동 실명은 나가지 않습니다.</strong> 반 안에서만 통하는 가명(예: 「가온」)으로
          바꿔 보내고, 돌아온 글을 화면에 보여 줄 때 다시 실제 이름으로 되돌립니다. 실명은 쌤플의
          데이터베이스 밖으로 나가지 않습니다.
        </p>
        <p>
          초안 생성에는 엘리스클라우드(Elice Cloud)의 ML API 를 씁니다. 교사가 적은 기록 글과 가명이
          그곳으로 전송됩니다.
        </p>
      </LegalSection>

      <LegalSection heading="3. 왜 저장하나요">
        <p>
          로그인, 문서 초안 만들기, 만든 문서를 다시 열어 보기 — 서비스를 쓰는 데 필요한 만큼만
          씁니다. 광고에 쓰지 않고, 다른 곳에 팔거나 넘기지 않습니다.
        </p>
      </LegalSection>

      <LegalSection heading="4. 얼마나 보관하나요">
        <p>
          계정이 살아 있는 동안 보관합니다. 교사가 계정이나 기록을 지워 달라고 하면 지웁니다. 이
          프로젝트는 교육 과정이 끝나면 운영을 멈출 수 있고, 그때는 저장된 자료를 모두 삭제합니다.
        </p>
      </LegalSection>

      <LegalSection heading="5. 어떻게 지키나요">
        <ul className="list-disc space-y-1 pl-5">
          <li>사이트 전 구간을 HTTPS 로만 주고받습니다</li>
          <li>비밀번호는 해시로만 저장해, 저장된 값으로는 원래 비밀번호를 알 수 없습니다</li>
          <li>교사는 자기 어린이집의 자료만 볼 수 있습니다. 다른 원의 자료에는 닿지 않습니다</li>
          <li>같은 원의 교사를 들이는 초대 코드는 한 번 쓰면 끝이고 7일이면 만료됩니다</li>
        </ul>
      </LegalSection>

      <LegalSection heading="6. 아동 정보에 대한 책임">
        <p>
          아동 이름은 교사가 직접 입력합니다. 어린이집이 보호자에게 받은 동의 범위 안에서만 입력해
          주세요. 쌤플은 보호자에게 직접 정보를 받지 않습니다.
        </p>
      </LegalSection>

      <LegalSection heading="7. 문의">
        <p>
          강원대학교 카카오테크캠퍼스 4기 2팀. 저장소의 Issues 로 남겨 주시면 확인합니다 —{" "}
          <a
            href="https://github.com/kakaotechcampus-4/ktc4-kangwon-2/issues"
            target="_blank"
            rel="noreferrer"
            className="underline"
          >
            github.com/kakaotechcampus-4/ktc4-kangwon-2
          </a>
        </p>
      </LegalSection>
    </LegalPage>
  );
}
