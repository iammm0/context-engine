import { Link, Outlet, useRouterState } from "@tanstack/react-router"
import { Code2, Database, MessageSquareText, Settings2, Sparkles } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

const navItems = [
  { to: "/chat", label: "Chat", icon: MessageSquareText },
  { to: "/documents", label: "Documents", icon: Database },
  { to: "/settings", label: "Settings", icon: Settings2 },
] as const

export function AppShell() {
  const pathname = useRouterState({ select: (state) => state.location.pathname })

  return (
    <div className="min-h-screen">
      <div className="mx-auto flex min-h-screen max-w-[1560px] flex-col px-4 py-4 sm:px-6 lg:px-8">
        <header className="sticky top-4 z-20 mb-5 rounded-2xl border border-[var(--blue-line)] bg-white/92 px-4 py-3 shadow-[0_14px_34px_rgba(37,99,235,0.08)] backdrop-blur">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <Link className="group flex items-center gap-3" to="/chat" search={{}}>
              <div className="flex size-10 items-center justify-center rounded-xl bg-sky-950 text-white shadow-[0_10px_24px_rgba(12,74,110,0.22)]">
                <Sparkles className="size-4" />
              </div>
              <div>
                <div className="text-base font-semibold leading-5 text-slate-950">context-engine</div>
                <div className="text-xs font-medium text-sky-700">TanStack Series</div>
              </div>
            </Link>

            <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
              <nav className="flex flex-wrap items-center gap-2">
                {navItems.map((item) => {
                  const isActive = pathname.startsWith(item.to)
                  const Icon = item.icon

                  return (
                    <Link
                      key={item.to}
                      to={item.to}
                      search={{}}
                      className={cn(
                        "inline-flex h-10 items-center gap-2 rounded-xl border px-3 text-sm font-medium transition-all",
                        isActive
                          ? "border-sky-950 bg-sky-950 text-white shadow-[0_10px_22px_rgba(12,74,110,0.18)]"
                          : "border-transparent bg-transparent text-slate-600 hover:border-[var(--blue-line)] hover:bg-[var(--surface-blue)] hover:text-sky-950",
                      )}
                    >
                      <Icon className="size-4" />
                      <span>{item.label}</span>
                    </Link>
                  )
                })}
              </nav>

              <div className="hidden h-8 w-px bg-[var(--blue-line)] lg:block" />

              <div className="flex items-center gap-2 text-sm text-slate-500">
                <Code2 className="size-4" />
                <span>React + Vite + TypeScript</span>
              </div>
            </div>
          </div>
        </header>

        <section className="mb-5 grid gap-4 rounded-3xl border border-[var(--blue-line)] bg-white px-5 py-6 shadow-[0_22px_60px_rgba(37,99,235,0.08)] lg:grid-cols-[1fr_360px] lg:px-8 lg:py-8">
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              <Badge>Open workspace</Badge>
              <Badge className="bg-white text-slate-700">FastAPI compatible</Badge>
            </div>
            <div className="max-w-4xl space-y-3">
              <h1 className="text-4xl font-semibold tracking-tight text-slate-950 sm:text-5xl lg:text-6xl">
                TanStack Web That Grows With Your Context Stack.
              </h1>
              <p className="max-w-3xl text-base leading-7 text-slate-600">
                一套并列的 TanStack 前端实现，复用现有 FastAPI 接口，把 Router、Query、Table、
                Virtual、Zustand、Monaco、xterm.js、React Flow 接进同一个清爽的产品工作区。
              </p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
            <div className="command-panel rounded-2xl p-4">
              <div className="mb-3 flex items-center justify-between text-xs font-medium text-sky-100">
                <span>1. Start backend</span>
                <span>API</span>
              </div>
              <code className="block overflow-x-auto text-sm text-sky-100">uvicorn main:app --reload --port 8000</code>
            </div>
            <div className="command-panel rounded-2xl p-4">
              <div className="mb-3 flex items-center justify-between text-xs font-medium text-sky-100">
                <span>2. Run web</span>
                <span>Vite</span>
              </div>
              <code className="block overflow-x-auto text-sm text-sky-100">cd web-tanstack && npm run dev</code>
            </div>
          </div>
        </section>

        <main className="flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
