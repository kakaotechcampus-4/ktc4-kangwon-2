"use client";

import { useRef, useState } from "react";

/**
 * 한글 파일(hwpx) 내려받기 버튼의 진행 상태와 결과 문구.
 * 무엇을 받을지(`fetchFile`)와 문구를 띄울 곳(`onMessage`)만 화면이 넘긴다.
 */
export function useHwpxDownload(onMessage: (message: string) => void) {
  const [exporting, setExporting] = useState(false);
  // 상태 갱신 전에 두 번 눌러도 요청이 한 번만 나가게 한다.
  const running = useRef(false);

  async function download(fetchFile: () => Promise<void>) {
    if (running.current) return;
    running.current = true;
    setExporting(true);
    onMessage("");
    try {
      await fetchFile();
      onMessage("한글 파일(hwpx)로 내려받았어요.");
    } catch (e) {
      onMessage(e instanceof Error ? e.message : "내려받지 못했어요.");
    } finally {
      running.current = false;
      setExporting(false);
    }
  }

  return { exporting, download };
}
