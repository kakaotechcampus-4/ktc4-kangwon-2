/** 원 양식 등록 · 목록 · 삭제 (docs/api-spec.md §8). */
import { apiRequest } from "./client";
import type { ApiForm } from "./types";

/** 서버가 받는 확장자. 다른 형식은 `UNSUPPORTED_FILE_TYPE` 400 이다. */
export const FORM_EXTENSIONS = [".hwp", ".hwpx"];

/** 파싱에 성공해야 저장된다. 표가 하나도 없으면 422 다. */
export const registerForm = (centerId: number, file: File) => {
  const form = new FormData();
  form.append("file", file);
  // Content-Type 을 직접 넣지 않는다 — 브라우저가 multipart 경계값을 붙여야 서버가 읽는다.
  return apiRequest<ApiForm>("/api/centers/" + centerId + "/forms", {
    method: "POST",
    body: form,
  });
};

/** 정렬은 서버가 `created_at` 내림차순으로 고정한다. */
export const getForms = (centerId: number) =>
  apiRequest<{ items: ApiForm[] }>("/api/centers/" + centerId + "/forms");

/** 204 No Content. 수정은 없다 — 지우고 다시 올린다. */
export const deleteForm = (id: number) =>
  apiRequest<void>("/api/forms/" + id, { method: "DELETE" });
