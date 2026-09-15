"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { accountName } from "@/lib/auth/local-account";
export default function TeacherMenu({ compact = false }: { compact?: boolean }) {
  const [name, setName] = useState("선생님");
  useEffect(() => { const saved = accountName(); if (saved) setName(`${saved} 선생님`); }, []);
  return <details className="relative" onKeyDown={event => { if (event.key === "Escape") event.currentTarget.open = false; }}>
    <summary className="flex cursor-pointer list-none items-center gap-2.5 rounded-xl p-2 hover:bg-cream [&::-webkit-details-marker]:hidden" aria-label={`${name} 계정 메뉴`}>
      <span className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-sage-tint text-sage-ink font-bold text-sm shrink-0">{name.slice(0, 1)}</span>
      <span className="min-w-0"><span className="block text-sm font-bold text-ink truncate">{name}</span></span>
      <span aria-hidden="true" className="ml-auto text-ink-soft">⌄</span>
    </summary>
    <div className={`absolute z-50 min-w-40 rounded-xl border border-line bg-paper p-2 shadow-lg ${compact ? "right-0 top-full mt-2" : "bottom-full left-0 right-0 mb-2"}`}>
      <Link href="/logout" className="block rounded-lg px-3 py-3 text-sm hover:bg-sage-tint">로그아웃</Link>
    </div>
  </details>;
}
