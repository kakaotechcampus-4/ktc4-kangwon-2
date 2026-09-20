"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { hasDemoSession } from "@/lib/auth/demo-session";
import { onboardingDestination } from "@/lib/auth/local-account";
export default function Page() {
  const router = useRouter();
  useEffect(() => {
    router.replace(hasDemoSession() ? onboardingDestination() : "/login");
  }, [router]);
  return null;
}
