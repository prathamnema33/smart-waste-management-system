import type { Role, User } from "./types";

export const demoAccounts: {
  label: string;
  role: Role;
  identifier: string;
  password: string;
}[] = [
  {
    label: "Admin Demo",
    role: "ADMIN",
    identifier: "demo_admin",
    password: "Admin@Demo2026!",
  },
  {
    label: "Monitoring Demo",
    role: "MONITOR",
    identifier: "demo_monitor",
    password: "Monitor@Demo2026!",
  },
  {
    label: "Worker Demo",
    role: "WORKER",
    identifier: "demo_worker",
    password: "Worker@Demo2026!",
  },
  {
    label: "Citizen Demo",
    role: "CITIZEN",
    identifier: "demo_citizen",
    password: "Citizen@Demo2026!",
  },
];

export function isDemoUser(user: User): boolean {
  return user.email.endsWith("@demo.invalid");
}
