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
 */

type SpeechEvent = { results: ArrayLike<ArrayLike<{ transcript: string }>> };
type Recognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  onresult: ((event: SpeechEvent) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
};
type RecognitionClass = new () => Recognition;

function recognitionClass(): RecognitionClass | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: RecognitionClass;
    webkitSpeechRecognition?: RecognitionClass;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function useDictation(onText: (text: string) => void) {
  const [supported] = useClientState(() => recognitionClass() !== null, false);
  const [listening, setListening] = useState(false);
  const recognition = useRef<Recognition | null>(null);
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
    const instance = new Recognition();
    instance.lang = "ko-KR";
    instance.continuous = false;
    instance.interimResults = false;
    instance.onresult = (event) => {
      const said = Array.from({ length: event.results.length }, (_, i) => event.results[i][0])
        .map((alternative) => alternative.transcript)
        .join(" ")
        .trim();
      if (said) handler.current(said);
    };
    instance.onerror = () => setListening(false);
    instance.onend = () => setListening(false);
    recognition.current = instance;
    instance.start();
    setListening(true);
  }, [listening]);

  return { supported, listening, toggle };
}
