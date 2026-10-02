import { readToken, tokenGeneration } from "./token";

let generation = 0;
export function invalidateSessionRequests() {
  generation += 1;
}

export class SessionChangedError extends Error {
  constructor() {
    super("로그인 세션이 변경되어 이전 요청의 결과를 적용하지 않았어요.");
    this.name = "SessionChangedError";
  }
}

function identity() {
  if (typeof window === "undefined") return "server";
  return JSON.stringify([
    generation,
    tokenGeneration(),
    readToken(),
    window.sessionStorage.getItem("saessak.accountEmail"),
    window.sessionStorage.getItem("saessak.demoSession"),
  ]);
}

/** 이메일이 같아도 로그아웃·재로그인한 세션에는 이전 응답을 적용하지 않는다. */
export function captureSession() {
  const key = identity();
  const isCurrent = () => identity() === key;
  return {
    key,
    isCurrent,
    assertCurrent() {
      if (!isCurrent()) throw new SessionChangedError();
    },
  };
}
