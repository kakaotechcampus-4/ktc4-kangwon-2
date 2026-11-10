"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  listNotifications,
  markNotificationsRead,
  type NotificationItem,
  type NotificationKind,
} from "@/lib/api/notifications";
import { localDate, localTime } from "@/lib/workspace/model";
import { Icon } from "./icons";

/** 알림 한 줄의 첫 줄과 둘째 줄. 둘째 줄 끝의 시각은 부른 쪽이 붙인다. */
const TEXT: Record<
  NotificationKind,
  { head: (item: NotificationItem) => ReactNode; sub: (item: NotificationItem) => string }
> = {
  ACCESS_REQUESTED: {
    head: (i) => (
      <>
        {i.requester_name} 선생님이 <b>{i.class_name}</b> 열람을 요청했어요
      </>
    ),
    sub: () => "누르면 받은 요청 칸이 열려요",
  },
  ACCESS_APPROVED: {
    head: (i) => (
      <>
        <b>{i.class_name}</b> 열람 요청이 승인됐어요
      </>
    ),
    sub: (i) => `이제 ${i.class_name} 문서를 볼 수 있어요`,
  },
  ACCESS_REJECTED: {
    head: (i) => (
      <>
        <b>{i.class_name}</b> 열람 요청이 거절됐어요
      </>
    ),
    sub: () => "다시 요청할 수 있어요",
  },
  ACCESS_REVOKED: {
    head: (i) => (
      <>
        <b>{i.class_name}</b> 열람 승인이 취소됐어요
      </>
    ),
    sub: () => "다시 요청할 수 있어요",
  },
};

/** 받은 쪽은 받은 요청 칸으로, 보낸 쪽은 그 반 칸으로 간다. */
const hrefOf = (item: NotificationItem) =>
  `/documents?foreign=${item.kind === "ACCESS_REQUESTED" ? "received" : item.class_id}`;

const timeOf = (item: NotificationItem) =>
  `${localDate(item.created_at)} ${localTime(item.created_at)}`;

/**
 * 상단바 종. 같은 원 열람 요청이 오가면 여기 쌓인다.
 *
 * 알림은 서버에만 둔다 — 브라우저 저장소에는 아무것도 넣지 않는다(ADR-013).
 * 덤이라 못 받아도 화면은 그대로 쓴다: 오류는 삼키고 마지막으로 받은 목록을 둔다.
 */
export default function NotificationBell() {
  const router = useRouter();
  const pathname = usePathname() ?? "/";
  const panelId = useId();
  const panel = useRef<HTMLElement>(null);
  const [items, setItems] = useState<NotificationItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  // 늦게 온 옛 응답이 읽음 처리한 숫자를 되살리지 않게 요청마다 번호를 매긴다.
  const latest = useRef(0);

  const load = useCallback(() => {
    const turn = ++latest.current;
    listNotifications()
      .then(({ items: next }) => {
        if (turn !== latest.current) return;
        setItems(next);
        setFailed(false);
      })
      .catch(() => {
        if (turn === latest.current) setFailed(true);
      });
  }, []);

  // 마운트 · 화면 이동 · 창으로 돌아올 때 다시 받는다. 주소의 검색값은 일부러 뺐다 —
  // 검색값이 바뀔 때마다 부르면 토큰이 깨진 구간(e2e routines)에서 401 이 난다.
  useEffect(() => {
    load();
    const visible = () => {
      if (document.visibilityState === "visible") load();
    };
    window.addEventListener("focus", load);
    document.addEventListener("visibilitychange", visible);
    return () => {
      window.removeEventListener("focus", load);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [pathname, load]);

  const unread = items?.filter((item) => item.read_at === null) ?? [];

  /** 숫자는 바로 줄이고, 서버가 받은 뒤 다시 받는다. 보내지 못해도 화면은 계속 쓴다. */
  async function markRead(ids: number[]) {
    latest.current += 1;
    const now = new Date().toISOString();
    setItems(
      (list) =>
        list?.map((item) =>
          ids.includes(item.id) && item.read_at === null ? { ...item, read_at: now } : item,
        ) ?? null,
    );
    await markNotificationsRead(ids).catch(() => {});
    load();
  }

  async function go(item: NotificationItem) {
    panel.current?.hidePopover();
    await markRead([item.id]);
    // 쿼리만 바뀌는 이동은 Next 가 화면을 다시 세우지 않는다 — 보관함에 있을 때만 통째로 옮긴다.
    if (pathname === "/documents") window.location.assign(hrefOf(item));
    else router.push(hrefOf(item));
  }

  function body() {
    if (items === null)
      return (
        <p className="px-4 py-5 text-[13px] text-ink-soft">
          {failed ? "알림을 불러오지 못했어요" : "알림을 불러오고 있어요"}
        </p>
      );
    if (!items.length) return <Empty onLeave={() => panel.current?.hidePopover()} />;
    return (
      <>
        <ul>
          {items.map((item) => (
            <li key={item.id} className="border-b border-shell">
              <button
                type="button"
                onClick={() => go(item)}
                data-unread={item.read_at === null || undefined}
                className="flex min-h-11 w-full gap-[10px] px-4 py-3 text-left text-ink-soft data-[unread]:bg-ivory data-[unread]:font-medium data-[unread]:text-ink"
              >
                <span
                  aria-hidden="true"
                  className={`mt-[7px] h-2 w-2 flex-none rounded-full ${item.read_at === null ? "bg-primary" : ""}`}
                />
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="text-[14px]">{TEXT[item.kind].head(item)}</span>
                  <span className="text-[12px] font-normal text-ink-soft">
                    {TEXT[item.kind].sub(item)} · {timeOf(item)}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
        <p className="px-4 pb-3 pt-[10px] text-[12px] text-ink-soft">
          최근 30개까지 보여요. 화면을 옮기거나 창으로 돌아올 때 새로 불러와요.
        </p>
      </>
    );
  }

  return (
    <>
      <button
        type="button"
        popoverTarget={panelId}
        aria-label={unread.length ? `알림 ${unread.length}건 안 읽음` : "알림, 안 읽은 알림 없음"}
        aria-expanded={open}
        className="relative inline-flex h-11 w-11 flex-none items-center justify-center rounded-[10px] bg-primary-tint text-primary-deep"
      >
        <Icon name="bell" className="h-5 w-5" />
        {unread.length > 0 && (
          <span
            aria-hidden="true"
            className="absolute right-1 top-[5px] h-[18px] min-w-[18px] rounded-full bg-primary px-[5px] text-center text-[11px] font-bold leading-[18px] text-white"
          >
            {unread.length}
          </span>
        )}
      </button>
      {/* popover 라 맨 위 층에 선다 — 상단바(z-20)나 하단 메뉴(z-30)에 깔리지 않는다.
          자리는 CSS 만으로 정한다(html zoom 때문에 좌표를 재지 않는다). 바깥을 누르거나 Esc 면 브라우저가 닫는다.
          display 는 건드리지 않는다 — 닫힌 패널은 UA 규칙이 감춘다. */}
      <section
        id={panelId}
        ref={panel}
        popover="auto"
        aria-label="알림 목록"
        onToggle={(e) => setOpen(e.nativeEvent.newState === "open")}
        className="fixed inset-auto left-0 right-0 top-[60px] m-0 w-full max-h-[calc(100*var(--app-dvh)-76px)] overflow-y-auto overscroll-contain rounded-b-[14px] border border-[color:var(--pg-line-strong)] bg-paper p-0 text-ink shadow-pg backdrop:bg-black/30 lg:left-auto lg:right-6 lg:top-[66px] lg:max-h-[calc(100*var(--app-dvh)-82px)] lg:w-[340px] lg:rounded-xl lg:backdrop:bg-transparent"
      >
        <div className="flex items-center justify-between border-b border-shell px-4 pb-2 pt-3 lg:pb-[10px] lg:pt-[14px]">
          <h2 className="text-[15px] font-bold">알림</h2>
          <button
            type="button"
            disabled={!unread.length}
            onClick={() => markRead(unread.map((item) => item.id))}
            className="min-h-11 text-[13px] font-medium text-primary-deep disabled:text-ink-hint lg:min-h-8"
          >
            모두 읽음
          </button>
        </div>
        {body()}
      </section>
    </>
  );
}

/** 알림이 하나도 없을 때. 무엇이 알림을 만드는지 말해 준다. */
function Empty({ onLeave }: { onLeave: () => void }) {
  return (
    <div className="flex flex-col gap-[10px] px-4 pb-[18px] pt-5">
      <p className="text-[14px] font-medium">아직 알림이 없어요.</p>
      <p className="text-[13px] text-ink-soft">
        같은 원 선생님이 우리 반 문서 열람을 요청하거나, 내가 보낸 요청이 승인 · 거절되면 여기에
        떠요.
      </p>
      <Link
        href="/documents"
        onClick={onLeave}
        className="text-[13px] font-medium text-primary-deep underline underline-offset-2"
      >
        문서 보관함에서 같은 원 반 보기
      </Link>
    </div>
  );
}
