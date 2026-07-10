import { useQuery } from "@tanstack/react-query"
import { Background, Controls, MiniMap, ReactFlow, type Edge, type Node } from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import { useEffect, useMemo, useRef } from "react"
import Editor from "@monaco-editor/react"
import { FitAddon } from "@xterm/addon-fit"
import { Terminal } from "@xterm/xterm"
import "@xterm/xterm/css/xterm.css"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/lib/api"

const nodeStyle = {
  background: "#ffffff",
  border: "1px solid #bae6fd",
  borderRadius: 14,
  boxShadow: "0 12px 24px rgba(37, 99, 235, 0.12)",
  color: "#0f172a",
  fontWeight: 600,
}

const nodes: Node[] = [
  {
    id: "input",
    type: "input",
    position: { x: 40, y: 80 },
    data: { label: "TanStack Router" },
    style: nodeStyle,
  },
  {
    id: "query",
    position: { x: 280, y: 20 },
    data: { label: "TanStack Query" },
    style: nodeStyle,
  },
  {
    id: "zustand",
    position: { x: 280, y: 160 },
    data: { label: "Zustand" },
    style: nodeStyle,
  },
  {
    id: "ui",
    position: { x: 560, y: 90 },
    data: { label: "shadcn/ui + Tailwind v4" },
    style: nodeStyle,
  },
]

const edges: Edge[] = [
  { id: "e-input-query", source: "input", target: "query", animated: true },
  { id: "e-input-zustand", source: "input", target: "zustand" },
  { id: "e-query-ui", source: "query", target: "ui", animated: true },
  { id: "e-zustand-ui", source: "zustand", target: "ui" },
]

export function SettingsLab() {
  const terminalRef = useRef<HTMLDivElement>(null)

  const runtimeQuery = useQuery({
    queryKey: ["runtime-config"],
    queryFn: async () => {
      const result = await api.getRuntimeConfig()
      if (result.error) {
        throw new Error(result.error)
      }
      return result.data
    },
  })

  const agentsQuery = useQuery({
    queryKey: ["agent-configs"],
    queryFn: async () => {
      const result = await api.getAgents()
      if (result.error) {
        throw new Error(result.error)
      }
      return result.data
    },
  })

  const editorValue = useMemo(() => {
    return JSON.stringify(
      {
        runtime: runtimeQuery.data,
        agents: agentsQuery.data?.agents?.slice(0, 4),
      },
      null,
      2,
    )
  }, [agentsQuery.data, runtimeQuery.data])
  const requestErrors = [
    runtimeQuery.error instanceof Error ? `运行时配置加载失败：${runtimeQuery.error.message}` : null,
    agentsQuery.error instanceof Error ? `Agent 配置加载失败：${agentsQuery.error.message}` : null,
  ].filter(Boolean) as string[]

  useEffect(() => {
    if (!terminalRef.current) {
      return
    }

    const terminal = new Terminal({
      fontFamily: "Azeret Mono, monospace",
      fontSize: 12,
      theme: {
        background: "#071a2f",
        foreground: "#e0f2fe",
        cursor: "#7dd3fc",
        black: "#071a2f",
        brightBlack: "#334155",
        blue: "#38bdf8",
        brightBlue: "#bae6fd",
        cyan: "#22d3ee",
        brightCyan: "#cffafe",
        green: "#7dd3fc",
        brightGreen: "#e0f2fe",
        magenta: "#93c5fd",
        brightMagenta: "#dbeafe",
        red: "#fb7185",
        brightRed: "#fecdd3",
        white: "#e0f2fe",
        brightWhite: "#f8fafc",
        yellow: "#fde68a",
        brightYellow: "#fef3c7",
      },
    })
    const fitAddon = new FitAddon()

    terminal.loadAddon(fitAddon)
    terminal.open(terminalRef.current)
    fitAddon.fit()
    terminal.writeln("context-engine :: tanstack frontend bootstrap")
    terminal.writeln("")
    terminal.writeln(`runtime mode: ${runtimeQuery.data?.mode || "loading..."}`)
    terminal.writeln(`agents loaded: ${agentsQuery.data?.agents?.length || 0}`)
    terminal.writeln("features: router | query | table | virtual | monaco | xterm | react-flow")
    terminal.writeln("")
    terminal.writeln("$ npm run dev")
    terminal.writeln("  VITE v8 + Tailwind v4 cockpit ready.")

    let frame = 0
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => fitAddon.fit())
    })
    observer.observe(terminalRef.current)

    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      terminal.dispose()
    }
  }, [agentsQuery.data?.agents?.length, runtimeQuery.data?.mode])

  return (
    <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
      <div className="grid gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Architecture Flow</CardTitle>
            <CardDescription>React Flow 适合把设置页里的系统结构、模块开关和运行链路做成可视化编辑器。</CardDescription>
          </CardHeader>
          <CardContent>
            {requestErrors.length > 0 ? (
              <div className="mb-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {requestErrors.map((error) => (
                  <div key={error}>{error}</div>
                ))}
              </div>
            ) : null}

            <div className="h-[360px] overflow-hidden rounded-2xl border border-[var(--blue-line)] bg-[var(--surface-blue)]">
              <ReactFlow defaultEdges={edges} defaultNodes={nodes} fitView>
                <Background color="#bae6fd" gap={18} size={1} />
                <MiniMap pannable zoomable />
                <Controls />
              </ReactFlow>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Runtime JSON Editor</CardTitle>
            <CardDescription>Monaco Editor 可以继续发展成运行时配置编辑器、Prompt 调整器或 JSON schema 表单容器。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-hidden rounded-2xl border border-[var(--blue-line)] bg-white">
              <Editor
                defaultLanguage="json"
                height="420px"
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  roundedSelection: true,
                  scrollBeyondLastLine: false,
                }}
                theme="vs-light"
                value={editorValue}
              />
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4">
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle>Runtime Console</CardTitle>
              <Badge>xterm.js</Badge>
            </div>
            <CardDescription>适合后续承接日志 tail、Agent 进度、命令输出和调试面板。</CardDescription>
          </CardHeader>
          <CardContent>
            <div
              className="command-panel min-h-[220px] overflow-hidden rounded-2xl p-3"
              ref={terminalRef}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Backend State Snapshot</CardTitle>
            <CardDescription>这里先展示现有后端的运行时配置与 Agent 配置读取结果，确保设置面板的数据源已经打通。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm text-slate-700">
            <div className="space-y-2">
              <div className="font-medium text-slate-950">Runtime config</div>
              <pre className="overflow-auto rounded-2xl border border-[var(--blue-line)] bg-white p-4 text-xs leading-6">
                {JSON.stringify(runtimeQuery.data, null, 2)}
              </pre>
            </div>
            <div className="space-y-2">
              <div className="font-medium text-slate-950">Agents</div>
              <pre className="overflow-auto rounded-2xl border border-[var(--blue-line)] bg-white p-4 text-xs leading-6">
                {JSON.stringify(agentsQuery.data?.agents?.slice(0, 6), null, 2)}
              </pre>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
