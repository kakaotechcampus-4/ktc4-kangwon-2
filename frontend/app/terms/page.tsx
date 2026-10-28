import LegalPage, { LegalSection } from "@/components/legal/LegalPage";

export const metadata = {
  title: "이용약관 · 쌤플",
  description: "쌤플이 어떤 서비스이고, 어디까지 책임지는지 적어 둔 문서입니다.",
};

export default function Page() {
  return (
    <LegalPage title="이용약관" updated="2026년 10월 27일">
      <p>
        쌤플(Ssample)은 강원대학교 카카오테크캠퍼스 4기 2팀의 교육 프로젝트입니다. 어린이집 교사가
        보육 문서 초안을 쓰는 것을 돕습니다. 이 글은 쌤플을 쓸 때의 약속입니다.
      </p>

      <LegalSection heading="1. 어떤 서비스인가요">
        <p>
          교사가 적은 일과 기록과 관찰 기록을 바탕으로 보육일지·관찰일지·계획안의{" "}
          <strong>초안</strong>을 만들어 줍니다. 만든 문서는 화면에서 고치고 확정한 뒤 한글 파일로
          내려받을 수 있습니다.
        </p>
      </LegalSection>

      <LegalSection heading="2. 초안은 초안입니다">
        <p>
          인공지능이 쓴 글은 사실과 다를 수 있습니다. 교사가 읽고 고친 뒤에 쓰세요.{" "}
          <strong>원에 제출하는 문서의 내용에 대한 책임은 교사와 어린이집에 있습니다.</strong>{" "}
          쌤플은 초안을 돕는 도구이고, 평가 결과나 제출 결과를 보장하지 않습니다.
        </p>
      </LegalSection>

      <LegalSection heading="3. 계정">
        <ul className="list-disc space-y-1 pl-5">
          <li>이메일과 비밀번호로 가입합니다. 다른 서비스의 계정을 묻지 않습니다</li>
          <li>
            <strong>다른 사이트에서 쓰는 비밀번호를 그대로 쓰지 마세요.</strong> 쌤플에서만 쓰는
            비밀번호를 정해 주세요
          </li>
          <li>계정은 교사 본인이 씁니다. 비밀번호를 남에게 알려 주지 마세요</li>
          <li>같은 원의 다른 교사는 초대 코드로 들어옵니다. 코드는 한 번 쓰면 끝입니다</li>
        </ul>
      </LegalSection>

      <LegalSection heading="4. 하지 말아야 할 것">
        <ul className="list-disc space-y-1 pl-5">
          <li>다른 사람의 계정으로 들어가거나, 다른 원의 자료를 보려고 시도하는 것</li>
          <li>서비스를 자동으로 긁어 가거나, 일부러 많은 요청을 보내 멈추게 하는 것</li>
          <li>아동·보호자에게 해가 되는 내용을 적거나 퍼뜨리는 것</li>
        </ul>
      </LegalSection>

      <LegalSection heading="5. 교사가 쓴 글은 교사의 것입니다">
        <p>
          교사가 입력한 기록과 만들어진 문서의 권리는 교사와 어린이집에 있습니다. 쌤플은 서비스를
          돌리는 데 필요한 만큼만 저장하고 보여 줍니다. 다른 곳에 공개하거나 팔지 않습니다.
        </p>
      </LegalSection>

      <LegalSection heading="6. 무료이고, 멈출 수 있습니다">
        <p>
          교육 과정에서 만드는 서비스라 요금을 받지 않습니다. 대신 교육 과정이 끝나면 운영을 멈출 수
          있고, 점검 때문에 잠시 쓸 수 없을 때도 있습니다. 중요한 문서는 한글 파일로 내려받아 따로
          보관해 주세요.
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
