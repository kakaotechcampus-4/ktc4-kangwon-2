# 쌤플 연간·월간 로컬 프론트 전체

하민님과 로컬에서 만들었던 연간·월간 웹을 그대로 모았습니다. HTML·CSS·JS·폰트·기존 Luna/Sol 생성 예시를 포함합니다. 프론트 원본 24개는 복사 전후 SHA-256이 같습니다(`frontend-source-manifest.json`).

## 실행

Node만 있으면 됩니다. 저장소 루트에서:

```sh
node docs/ui-drafts/play-plans/serve.cjs
```

- 연간: http://127.0.0.1:8886/yearly/
- 월간: http://127.0.0.1:8886/monthly/?month=10
- 종료: Ctrl+C

후보 선택·드래그 배치·칸 편집·실시간 문서 반영·되돌리기·확대·인쇄 미리보기·연간/월간 전환 등 기존 로컬 동작을 그대로 확인할 수 있습니다. 연간은 Luna/Sol 예시를 전환할 수 있고, 월간의 7월·10월 Sol 실측 초안 불러오기도 포함했습니다.

## 전달 범위

기존 로컬 프론트 전체를 전달하는 자료입니다. Next.js 제품 화면으로 재개발하지 않았습니다. 프론트 팀이 디자인과 동작을 보고 기존 서비스에 옮길 수 있습니다.

키·.env·유료 LLM 실행 서버·제품 API/DB 코드는 포함하지 않았습니다. 따라서 기존 생성 결과를 불러오는 것은 가능하며 새 유료 생성은 실행되지 않습니다. 브라우저 편집값은 이 주소의 localStorage에 저장됩니다. 실제 아동·교사 개인정보는 입력하지 마세요.

원본 UI의 일부 동작은 제품 Core에서 아직 지원하지 않는 디자인 동작도 포함하므로, 서비스에 연결할 때는 승인된 계약을 따릅니다. HWPX 내보내기 서버는 포함하지 않았습니다.

## 확인

```sh
cd docs/ui-drafts/play-plans
node --test model.test.cjs yearly-bridge.test.cjs preview.test.cjs
node --check app.js
node --check yearly/app.js
```