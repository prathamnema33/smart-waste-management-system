"use client";

import { useRouter } from "next/navigation";
import LoginForm from "@/components/LoginForm";
import type { User } from "@/lib/types";
import "../dashboard.css";

export default function MonitorLoginPage() {
  const router = useRouter();

  function handleLogin(user: User) {
    if (user.role === "ADMIN") {
      router.replace("/admin");
    } else if (user.role === "MONITOR") {
      router.replace("/monitoring");
    } else {
      router.replace("/");
    }
  }

  return <LoginForm mode="operations" onLogin={handleLogin} />;
}
