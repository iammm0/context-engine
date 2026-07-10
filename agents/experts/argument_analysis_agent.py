"""Argument analysis expert agent."""

from typing import Any, AsyncGenerator, Dict, List, Optional

from agents.base.base_agent import BaseAgent
from utils.logger import logger


class ArgumentAnalysisAgent(BaseAgent):
    """Analyze assumptions, reasoning chains, and argument structure."""

    def get_default_model(self) -> str:
        return "gpt-oss:20b"

    def get_prompt(self) -> str:
        return """你是论证分析专家，负责拆解复杂问题中的核心命题、隐含假设、推理链和证据缺口。

你的输出需要聚焦：
1. 明确核心结论或待证明命题。
2. 拆解支持该结论的关键前提和推理步骤。
3. 标注哪些环节依赖证据，哪些环节只是推测。
4. 给出可能的反例、边界条件和待验证问题。
5. 用结构化小标题组织结果，避免泛泛而谈。"""

    async def execute(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        try:
            other_results = context.get("other_results", []) if context else []
            evidence_ids: List[str] = []
            for item in other_results:
                evidence_ids.extend(item.get("evidence_ids", []) or [])

            prompt = f"""请对下面的问题或已有研究结果做论证分析。

原始问题：
{task}

已有研究结果：
{self._format_other_results(other_results)}

请输出：
- 核心命题
- 关键假设
- 推理链
- 证据支撑与证据缺口
- 可能反例或边界条件
- 后续需要验证的问题
"""

            content = ""
            async for chunk in self._call_llm(prompt=self.merge_system_into_task_prompt(prompt), stream=stream):
                content += chunk
                if stream:
                    yield {
                        "type": "chunk",
                        "content": chunk,
                        "agent_type": "argument_analysis",
                    }

            if content:
                yield {
                    "type": "complete",
                    "content": content,
                    "agent_type": "argument_analysis",
                    "evidence_ids": list(dict.fromkeys(evidence_ids)),
                    "claims": [
                        {
                            "source_agent": "argument_analysis",
                            "content": content[:240],
                            "status": "analyzed",
                        }
                    ],
                    "open_questions": self._extract_open_questions(content),
                    "confidence": 0.75,
                }

        except Exception as exc:
            logger.error("ArgumentAnalysisAgent failed: %s", exc, exc_info=True)
            yield {
                "type": "error",
                "content": f"论证分析失败: {str(exc)}",
                "agent_type": "argument_analysis",
            }

    def _format_other_results(self, results: List[Dict[str, Any]]) -> str:
        if not results:
            return "暂无其他 Agent 结果，请直接分析原始问题。"

        formatted = []
        for result in results:
            agent_type = result.get("agent_type", "unknown")
            content = str(result.get("content") or "").strip()
            if content:
                formatted.append(f"[{agent_type}]\n{content[:800]}")
        return "\n\n".join(formatted) if formatted else "暂无可用内容。"

    def _extract_open_questions(self, content: str) -> List[str]:
        questions = []
        for line in content.splitlines():
            text = line.strip().lstrip("-*0123456789.、 ")
            if text.endswith(("?", "？")):
                questions.append(text)
        return questions[:5]
