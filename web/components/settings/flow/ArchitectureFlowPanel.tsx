"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Node,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import ArchNode from "./ArchNode";
import { buildNodesAndEdges, type ArchNodeData } from "./buildArchitectureFlow";
import { RuntimeSettingsModals, type RuntimeModalState } from "../modals/RuntimeSettingsModals";
import DeepResearchConfigModal from "../modals/DeepResearchConfigModal";

function FitViewOnMount() {
  const { fitView } = useReactFlow();
  useEffect(() => {
    const t = window.setTimeout(() => fitView({ padding: 0.12 }), 80);
    return () => clearTimeout(t);
  }, [fitView]);
  return null;
}

function FlowCanvas({
  onRuntimeModal,
  onDeepResearch,
}: {
  onRuntimeModal: (s: RuntimeModalState) => void;
  onDeepResearch: (focusAgent: string | null) => void;
}) {
  const { nodes: n0, edges: e0 } = useMemo(() => buildNodesAndEdges(), []);
  const nodeTypes = useMemo<NodeTypes>(() => ({ arch: ArchNode }), []);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const d = node.data as ArchNodeData;
      if (d.kind === "view") {
        if (node.id === "n_user") {
          onRuntimeModal({
            kind: "view",
            title: "用户查询",
            body: "用户自然语言问题进入查询分析模块；此处无可调参数，仅表示数据流入口。",
          });
          return;
        }
        if (node.id === "n_out") {
          onRuntimeModal({
            kind: "view",
            title: "生成与回答",
            body: "检索与重排后的上下文进入大模型生成最终回答；具体模型在对话页「模型配置」中选择。",
          });
          return;
        }
      }
      if (d.kind === "presets") {
        onRuntimeModal({ kind: "presets" });
        return;
      }
      if (d.kind === "runtime-module" && d.moduleKey) {
        onRuntimeModal({ kind: "module", key: d.moduleKey });
        return;
      }
      if (d.kind === "runtime-params-embedding") {
        onRuntimeModal({ kind: "params", group: "embedding" });
        return;
      }
      if (d.kind === "runtime-params-kg") {
        onRuntimeModal({ kind: "params", group: "kg" });
        return;
      }
      if (d.kind === "runtime-params-ocr") {
        onRuntimeModal({ kind: "params", group: "ocr" });
        return;
      }
      if (d.kind === "deep-research") {
        onDeepResearch(null);
        return;
      }
      if (d.kind === "deep-agent" && d.agentType) {
        onDeepResearch(d.agentType);
      }
    },
    [onRuntimeModal, onDeepResearch]
  );

  return (
    <ReactFlow
      nodes={n0}
      edges={e0}
      nodeTypes={nodeTypes}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      panOnScroll
      zoomOnScroll
      zoomOnPinch
      minZoom={0.35}
      maxZoom={1.4}
      proOptions={{ hideAttribution: true }}
      onNodeClick={onNodeClick}
      className="bg-slate-50/90 dark:bg-gray-950/50"
    >
      <Background gap={16} size={1} className="!bg-transparent" />
      <Controls className="!bg-white dark:!bg-gray-900 !border-gray-200 dark:!border-gray-700 !shadow" />
      <MiniMap
        className="!bg-white/90 dark:!bg-gray-900/90 !border-gray-200 dark:!border-gray-700"
        maskColor="rgba(0,0,0,0.08)"
      />
      <FitViewOnMount />
    </ReactFlow>
  );
}

export default function ArchitectureFlowPanel() {
  const [runtimeModal, setRuntimeModal] = useState<RuntimeModalState>({ kind: "closed" });
  const [drOpen, setDrOpen] = useState(false);
  const [drFocus, setDrFocus] = useState<string | null>(null);

  const onDeepResearch = useCallback((focus: string | null) => {
    setDrFocus(focus);
    setDrOpen(true);
  }, []);

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden">
      <div className="px-3 py-2 border-b border-gray-100 dark:border-gray-800 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
        <div className="text-sm font-semibold text-gray-800 dark:text-gray-100">上下文引擎架构（只读画布）</div>
        <span className="text-xs text-gray-500 dark:text-gray-400">
          可缩放平移；点击节点在弹窗中配置（不可拖拽节点）
        </span>
      </div>
      <div className="h-[min(560px,70vh)] w-full">
        <ReactFlowProvider>
          <FlowCanvas onRuntimeModal={setRuntimeModal} onDeepResearch={onDeepResearch} />
        </ReactFlowProvider>
      </div>
      <p className="text-[11px] text-gray-500 dark:text-gray-400 px-3 py-2 border-t border-gray-100 dark:border-gray-800">
        左侧为入库与图谱侧参数；中间为主检索链；右侧为深度研究多智能体（协调器与 8 类专家）。「深度研究」节点打开总表；单个子 Agent 节点打开同一弹窗并定位到对应卡片。
      </p>

      <RuntimeSettingsModals state={runtimeModal} onClose={() => setRuntimeModal({ kind: "closed" })} />
      <DeepResearchConfigModal open={drOpen} onClose={() => setDrOpen(false)} focusAgentType={drFocus} />
    </div>
  );
}
