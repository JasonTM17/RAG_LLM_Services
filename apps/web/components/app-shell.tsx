"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BookOpenCheck,
  Database,
  Files,
  MessageSquareText,
  Network,
} from "lucide-react";
import type { ReactNode } from "react";

const navItems = [
  { href: "/chat", label: "Chat", icon: MessageSquareText },
  { href: "/documents", label: "Documents", icon: Files },
  { href: "/knowledge-bases", label: "Knowledge", icon: Database },
  { href: "/study", label: "Study", icon: BookOpenCheck },
  { href: "/system-status", label: "Status", icon: Activity },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="app-shell">
      <aside className="side-nav" aria-label="Primary">
        <Link href="/chat" className="brand-lockup" aria-label="RAG LLM Services chat">
          <span className="brand-mark" aria-hidden="true">
            <Network size={20} />
          </span>
          <span>
            <strong>RAG LLM</strong>
            <small>Learning OS</small>
          </span>
        </Link>

        <nav className="nav-list">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={active ? "nav-item is-active" : "nav-item"}
                aria-label={item.label}
                aria-current={active ? "page" : undefined}
              >
                <Icon size={18} aria-hidden="true" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </aside>
      <main className="app-main">{children}</main>
    </div>
  );
}
