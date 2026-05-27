"""批判性思维专家Agent"""
from typing import Dict, Any, Optional, AsyncGenerator
from agents.base.base_agent import BaseAgent
from services.rag_service import rag_service
from utils.logger import logger

class CriticAgent(BaseAgent):
    """批判性思维专家 - 负责验证信息的准确性，检查幻觉，提供反面观点"""
    
    def get_prompt(self) -> str:
        return """你是一个批判性思维专家。你的任务是审查给定的信息或观点，找出潜在的逻辑漏洞、事实错误或幻觉（Hallucination）。

请注意：
1. 你的态度应当是客观、严谨的。
2. 基于检索到的证据进行反驳或确认。
3. 如果发现信息不足以支撑结论，请指出。
4. 提供建设性的修正建议。

输出格式要求：
- **准确性评估**：可信/存疑/不可信。
- **问题点**：列出具体问题。
- **证据对比**：引用检索到的证据。
- **修正建议**：如何改进。
"""
    
    async def execute(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        stream: bool = False
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行批判性分析任务
        """
        # 1. 执行RAG检索 (获取验证素材)
        rag_context = ""
        sources = []
        evidence = []
        other_results = context.get("other_results", []) if context else []
        inherited_evidence = []
        for item in other_results:
            inherited_evidence.extend(item.get("evidence", []) or [])
        
        try:
            logger.info(f"CriticAgent: 开始检索验证素材 - {task[:50]}...")
            retrieval_result = await rag_service.retrieve_context(
                query=task,
                document_id=context.get("document_id") if context else None,
                assistant_id=context.get("assistant_id") if context else None,
                knowledge_space_ids=context.get("knowledge_space_ids") if context else None,
                embedding_model=context.get("generation_config", {}).get("embedding_model") if context else None
            )
            rag_context = retrieval_result.get("context", "")
            sources = retrieval_result.get("sources", [])
            evidence = inherited_evidence or retrieval_result.get("evidence", [])
        except Exception as e:
            logger.error(f"CriticAgent: 检索失败: {e}")
            if not other_results:
                yield {
                    "type": "error",
                    "content": f"检索失败: {str(e)}",
                    "agent_type": "critic"
                }
                return

        # 2. 生成分析
        full_response = ""
        try:
            reviewed_content = "\n\n".join(
                f"[{r.get('agent_type', 'unknown')}]\n{r.get('content', '')}"
                for r in other_results
                if r.get("content")
            )
            if not reviewed_content:
                reviewed_content = task

            evidence_context = rag_context
            if inherited_evidence and not evidence_context:
                evidence_context = "\n\n".join(
                    f"[{item.get('id')}] {item.get('text', '')}"
                    for item in inherited_evidence
                    if item.get("id") and item.get("text")
                )

            async for chunk in self.ollama_service.generate(
                prompt=(
                    "请审查以下其他Agent的结论或用户问题，逐条判断其证据状态。"
                    "输出必须包含：准确性评估、支持充分的结论、证据不足的结论、可能矛盾或需修正的结论。"
                    "每条判断请使用 supported / unsupported / contradicted / insufficient 之一标注。\n\n"
                    f"待审查内容：\n{reviewed_content}\n\n"
                    f"可用证据：\n{evidence_context}"
                ),
                context=None,
                stream=stream
            ):
                full_response += chunk
                if stream:
                    yield {
                        "type": "chunk",
                        "content": chunk,
                        "agent_type": "critic"
                    }
            
            if not stream or full_response:
                yield {
                    "type": "complete",
                    "content": full_response,
                    "agent_type": "critic",
                    "sources": sources,
                    "evidence": evidence,
                    "evidence_ids": [item.get("id") for item in evidence if item.get("id")],
                    "claims": self._build_review_claims(other_results, full_response),
                    "open_questions": []
                }
                
        except Exception as e:
            logger.error(f"CriticAgent: 生成失败: {e}")
            yield {
                "type": "error",
                "content": f"生成失败: {str(e)}",
                "agent_type": "critic"
            }

    def _build_review_claims(self, other_results, critique_text: str):
        claims = []
        for result in other_results or []:
            content = (result.get("content") or "").strip()
            if not content:
                continue
            claims.append({
                "source_agent": result.get("agent_type", "unknown"),
                "content": content[:240],
                "status": "reviewed",
            })
        if not claims and critique_text:
            claims.append({
                "source_agent": "critic",
                "content": critique_text[:240],
                "status": "reviewed",
            })
        return claims
