"use client";

import { useRouter } from "next/navigation";
import LoginForm from "@/components/LoginForm";
import type { User } from "@/lib/types";
import "../dashboard.css";

export default function MonitorLoginPage() {
  const router = useRouter();

  function handleLogin(user: User) {
    if (user.role === "ADMIN" || user.role === "MONITOR") {
      router.replace("/monitoring");
    }
  }

  return <LoginForm mode="operations" onLogin={handleLogin} />;
}
