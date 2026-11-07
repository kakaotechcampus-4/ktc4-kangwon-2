import type { DragEvent } from "react";
import { appZoom } from "@/lib/appZoom";

/**
 * 계획안 문서 안에서 끌어 순서 바꾸기(놀이 중심형 ⑤ · 월별 주제형 연간 공통).
 * 브라우저 기본 끌기 그림은 가장자리가 흐려져서, 빈 그림을 쓰고 끄는 칸을 또렷하게 복사해 마우스를 따라 옮긴다
 * — 줄은 위아래(`y`), 월간 안전교육 칸처럼 한 줄 안에서 옮기는 칸은 좌우(`x`).
 */
const BLANK =
  typeof window === "undefined"
    ? null
    : Object.assign(new Image(), {
        src: "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7",
      });

let active: { stop: () => void; cells: HTMLElement[] } | null = null;

/** 끌기 시작 — `cells`(한 줄의 칸들)를 복사해 띄우고 원래 칸에는 `data-dragging` 을 붙인다. */
export function liftCells(
  event: DragEvent<HTMLElement>,
  cells: HTMLElement[],
  key: string,
  axis: "x" | "y" = "y",
) {
  event.dataTransfer.setData("text/plain", key);
  event.dataTransfer.effectAllowed = "move";
  if (BLANK) event.dataTransfer.setDragImage(BLANK, 0, 0);
  dropCells();
  const rects = cells.map((cell) => cell.getBoundingClientRect());
  // 문서 배율(zoom)을 복사본에도 준다 — 글자 크기가 같아 보이게.
  // 복사본은 body 에 붙어 화면 전체 배율(app)도 받으므로, 화면 좌표 · 크기를 그만큼 나눠 넣는다.
  const app = appZoom();
  const sheet = cells[0].closest<HTMLElement>('[style*="zoom"]');
  const docZoom = Number(sheet?.style.zoom) || 1;
  // 칸 크기는 문서 안에서 잰 배율로 되돌린다 — 화면 배율 × 문서 배율을 곱해 짐작하지 않는다.
  const zoom = sheet ? appZoom(sheet) : app;
  const offset = axis === "y" ? event.clientY - rects[0].top : event.clientX - rects[0].left;
  const table = document.createElement("table");
  table.className = cells[0].closest("table")?.className ?? "";
  const row = document.createElement("tr");
  cells.forEach((cell, i) => {
    const copy = cell.cloneNode(true) as HTMLElement;
    copy.removeAttribute("rowspan");
    copy.querySelectorAll("[draggable]").forEach((el) => el.remove());
    copy.style.width = `${rects[i].width / zoom}px`;
    copy.style.height = `${rects[i].height / zoom}px`;
    row.append(copy);
  });
  table.append(row);
  Object.assign(table.style, {
    zoom: String(docZoom),
    width: `${rects.reduce((w, r) => w + r.width, 0) / zoom}px`,
    background: "#fff",
  });
  const box = document.createElement("div");
  box.append(table);
  Object.assign(box.style, {
    position: "fixed",
    left: `${rects[0].left / app}px`,
    top: `${rects[0].top / app}px`,
    boxShadow: "0 12px 28px rgba(60,40,100,.28)",
    outline: "2px solid #7053a0",
    pointerEvents: "none",
    zIndex: "60",
    transform: "scale(1.02)",
  });
  document.body.append(box);
  const move = (e: globalThis.DragEvent) => {
    if (axis === "y" && e.clientY) box.style.top = `${(e.clientY - offset) / app}px`;
    if (axis === "x" && e.clientX) box.style.left = `${(e.clientX - offset) / app}px`;
  };
  document.addEventListener("dragover", move);
  cells.forEach((cell) => (cell.dataset.dragging = ""));
  active = {
    cells,
    stop: () => {
      document.removeEventListener("dragover", move);
      box.remove();
    },
  };
}

/** 놓거나 취소했을 때 — 복사본을 지운다. */
export function dropCells() {
  active?.stop();
  active?.cells.forEach((cell) => delete cell.dataset.dragging);
  active = null;
}

/** 옮긴 칸이 새 자리에서 한 번 떠올랐다 내려앉는다. 움직임을 줄인 환경에서는 하지 않는다. */
export function settle(selector: string) {
  if (
    typeof window === "undefined" ||
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  )
    return;
  // 상태가 바뀌어 다시 그린 뒤의 칸을 잡는다.
  requestAnimationFrame(() =>
    requestAnimationFrame(() =>
      document.querySelectorAll<HTMLElement>(selector).forEach((el) =>
        el.animate(
          [
            { backgroundColor: "#e9ddf7", transform: "translateY(-6px)" },
            { backgroundColor: "#f6f1fb", transform: "translateY(0)", offset: 0.6 },
            { backgroundColor: "transparent", transform: "translateY(0)" },
          ],
          { duration: 520, easing: "cubic-bezier(.2,.8,.2,1)" },
        ),
      ),
    ),
  );
}
