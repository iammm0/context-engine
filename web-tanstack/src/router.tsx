import { Suspense, lazy } from "react"
import { createRootRoute, createRoute, createRouter, redirect } from "@tanstack/react-router"

import { AppShell } from "@/components/shell/app-shell"

/* eslint-disable react-refresh/only-export-components */
const ChatPlayground = lazy(() =>
  import("@/components/chat/chat-playground").then((module) => ({ default: module.ChatPlayground })),
)
const DocumentsTable = lazy(() =>
  import("@/components/documents/documents-table").then((module) => ({ default: module.DocumentsTable })),
)
const SettingsLab = lazy(() =>
  import("@/components/settings/settings-lab").then((module) => ({ default: module.SettingsLab })),
)

function RouteFallback() {
  return (
    <div className="blue-panel flex min-h-[320px] items-center justify-center rounded-2xl px-6 py-12 text-sm text-slate-600">
      正在加载 TanStack 工作区...
    </div>
  )
}

const rootRoute = createRootRoute({
  component: AppShell,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  beforeLoad: () => {
    throw redirect({ to: "/chat" })
  },
})

const chatRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/chat",
  component: () => (
    <Suspense fallback={<RouteFallback />}>
      <ChatPlayground />
    </Suspense>
  ),
})

const documentsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/documents",
  component: () => (
    <Suspense fallback={<RouteFallback />}>
      <DocumentsTable />
    </Suspense>
  ),
})

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings",
  component: () => (
    <Suspense fallback={<RouteFallback />}>
      <SettingsLab />
    </Suspense>
  ),
})

const routeTree = rootRoute.addChildren([indexRoute, chatRoute, documentsRoute, settingsRoute])

export const router = createRouter({
  routeTree,
  defaultPreload: "intent",
})

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}
