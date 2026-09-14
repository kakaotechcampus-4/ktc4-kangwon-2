"""개발용 Harness.

**제품 코드가 아니다.** AI Lead가 로컬에서 Planning Core를 직접 실행해 보기 위한
CLI Harness와 그 Composition Root만 둔다. 제품 FE나 HTTP Adapter로 발전시키지
않는다.

이 패키지는 Application Use Case만 호출하며 Domain Aggregate를 직접 변경하지
않는다. 상태 변경은 전부 다음 4개 Use Case를 통해서만 일어난다.

    GenerateYearlyPlan
    EditYearlyPlanItem
    RegenerateYearlyPlanItem
    ConfirmYearlyPlan
"""
