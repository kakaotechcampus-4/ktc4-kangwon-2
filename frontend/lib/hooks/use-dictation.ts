"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useClientState } from "./use-client-state";

/**
 * 음성 받아쓰기. 브라우저가 가진 것만 쓴다 — 서버로 소리를 보내지 않는다.
 *
 * 아이 이름이 섞인 말이 녹음돼 밖으로 나가면 안 되는데, Web Speech API 는
 * 크롬 계열에서 구글 서버를 거친다. 그래서 켜는 건 교사가 버튼을 누를 때뿐이고,
 * 한 문장 받으면 바로 멈춘다. 지원하지 않는 브라우저에서는 `supported` 가 false 라
 * 화면에서 버튼 자체가 안 보인다(사파리·파이어폭스).
 *
 * **실패하면 왜 실패했는지 말한다.** 전에는 어떤 실패든 버튼만 조용히 꺼져서, 마이크를
 * 막아 둔 것인지 소리가 안 들린 것인지 교사가 알 길이 없었다 — 「그냥 안 되는 기능」으로
 * 보였다.
 */

type SpeechEvent = { results: ArrayLike<ArrayLike<{ transcript: string }>> };
type SpeechFailure = { error?: string };
type Recognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  onresult: ((event: SpeechEvent) => void) | null;
  onerror: ((event: SpeechFailure) => void) | null;
  onend: (() => void) | null;
};
type RecognitionClass = new () => Recognition;

function recognitionClass(): RecognitionClass | null {
  if (typeof window === "undefined") return null;
  // https 나 localhost 가 아니면 클래스는 있는데 `start()` 가 바로 막힌다. 눌러도 아무
  // 일이 안 일어나는 버튼을 띄우느니 안 띄운다.
  if (!window.isSecureContext) return null;
  const w = window as unknown as {
    SpeechRecognition?: RecognitionClass;
    webkitSpeechRecognition?: RecognitionClass;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/**
 * 실패 코드를 교사가 읽을 말로 바꾼다.
 *
 * `aborted` 는 교사가 멈춤 버튼을 누른 것이라 **실패가 아니다** — 빈 문자열을 준다.
 * 코드 이름은 Web Speech API 가 정한 것이고 브라우저마다 조금씩 다르므로, 모르는 코드가
 * 오면 일반 문장으로 떨어진다.
 */
export function whyFailed(code: string | undefined): string {
  if (code === "aborted") return "";
  const known: Record<string, string> = {
    "not-allowed": "마이크를 쓸 수 없어요. 주소창 자물쇠를 눌러 마이크를 허용해 주세요.",
    "service-not-allowed": "마이크를 쓸 수 없어요. 주소창 자물쇠를 눌러 마이크를 허용해 주세요.",
    "audio-capture": "마이크를 찾지 못했어요. 연결을 확인해 주세요.",
    "no-speech": "소리가 들리지 않았어요. 버튼을 다시 누르고 말해 주세요.",
    network: "인터넷이 끊겨 받아쓰기를 못 했어요.",
    "language-not-supported": "이 브라우저는 한국어 받아쓰기를 지원하지 않아요.",
  };
  return known[code ?? ""] ?? "받아쓰기를 못 했어요. 버튼을 다시 눌러 주세요.";
}

/**
 * 아직 못 읽은 말만 이어 붙인다.
 *
 * **`event.results` 는 누적이다.** 한 번 말해도 `onresult` 가 여러 번 불리는데, 그때마다
 * 지금까지 받은 것이 **전부** 다시 들어 있다. 매번 전체를 이어 붙이면 같은 말이 네댓 번
 * 적힌다. 그래서 어디까지 읽었는지 기억해 두고 그 뒤만 읽는다.
 */
export function transcriptFrom(
  results: ArrayLike<ArrayLike<{ transcript: string }>>,
  from: number,
): string {
  return Array.from({ length: Math.max(results.length - from, 0) }, (_, i) => results[from + i][0])
    .map((alternative) => alternative.transcript)
    .join(" ")
    .trim();
}

export function useDictation(onText: (text: string) => void) {
  const [supported] = useClientState(() => recognitionClass() !== null, false);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState("");
  const recognition = useRef<Recognition | null>(null);
  // 이번에 켠 뒤로 몇 개까지 읽었나.
  const read = useRef(0);
  // onText 가 매 렌더 새 함수여도 받아쓰기를 다시 만들지 않는다.
  const handler = useRef(onText);
  useEffect(() => {
    handler.current = onText;
  }, [onText]);

  useEffect(() => () => recognition.current?.stop(), []);

  const toggle = useCallback(() => {
    if (listening) {
      recognition.current?.stop();
      return;
    }
    const Recognition = recognitionClass();
    if (!Recognition) return;
    setError("");
    const instance = new Recognition();
    instance.lang = "ko-KR";
    instance.continuous = false;
    instance.interimResults = false;
    instance.onresult = (event) => {
      const said = transcriptFrom(event.results, read.current);
      read.current = event.results.length;
      if (said) handler.current(said);
    };
    instance.onerror = (event) => {
      setError(whyFailed(event?.error));
      setListening(false);
    };
    instance.onend = () => setListening(false);
    recognition.current = instance;
    read.current = 0;
    try {
      instance.start();
    } catch {
      // 이미 켜져 있는데 또 켜면 던진다. 화면 상태가 어긋난 것이라 켜지 않고 알린다.
      setError(whyFailed(undefined));
      return;
    }
    setListening(true);
  }, [listening]);

  return { supported, listening, error, toggle };
}
