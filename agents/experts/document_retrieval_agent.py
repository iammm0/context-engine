"""文档检索专家Agent"""
from typing import Dict, Any, Optional, AsyncGenerator
from agents.base.base_agent import BaseAgent
from services.rag_service import rag_service
from utils.logger import logger
from utils.citation import build_citation_diagnostics


class DocumentRetrievalAgent(BaseAgent):
    """文档检索专家 - 调用RAG服务检索相关文档"""
    
    def get_default_model(self) -> str:
        """获取默认模型名称"""
        return "gpt-oss:20b"
    
    def get_prompt(self) -> str:
        """获取系统提示词"""
        return """你是文档检索专家，负责从知识库中检索与用户问题相关的文档内容。

你的任务：
1. 理解用户问题的核心需求
2. 检索最相关的文档片段
3. 整理和总结检索到的信息
4. 标注信息来源"""
    
    async def execute(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        stream: bool = False
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行文档检索任务"""
        try:
            assistant_id = context.get("assistant_id") if context else None
            document_id = context.get("document_id") if context else None
            
            logger.info(f"DocumentRetrievalAgent: 开始检索 - {task[:50]}...")
            
            # 调用RAG服务检索
            retrieval_result = await rag_service.retrieve_context(
                query=task,
                document_id=document_id,
                assistant_id=assistant_id,
                knowledge_space_ids=context.get("knowledge_space_ids") if context else None,
                embedding_model=context.get("generation_config", {}).get("embedding_model") if context else None
            )
            
            context_text = retrieval_result.get("context", "")
            sources = retrieval_result.get("sources", [])
            evidence = retrieval_result.get("evidence", [])
            evidence_quality = retrieval_result.get("evidence_quality", {})
            recommended_resources = retrieval_result.get("recommended_resources", [])
            
            # 使用LLM总结检索结果
            summary_prompt = f"""基于以下检索到的文档证据，总结与问题"{task}"相关的关键信息。
请在关键事实后使用 [S1]、[S2] 这类证据编号；如果证据不足，请明确说明“资料中未找到”。

检索到的文档内容：
{context_text[:4000]}

请总结关键信息，并标注信息来源。"""
            
            summary = ""
            async for chunk in self._call_llm(prompt=self.merge_system_into_task_prompt(summary_prompt), stream=False):
                summary += chunk
            
            citation_quality = build_citation_diagnostics(summary, evidence)
            yield {
                "type": "complete",
                "content": summary,
                "agent_type": "document_retrieval",
                "sources": sources,
                "evidence": evidence,
                "evidence_quality": evidence_quality,
                "evidence_ids": [item.get("id") for item in evidence if item.get("id")],
                "citation_warnings": citation_quality.get("warnings", []),
                "citation_quality": citation_quality,
                "recommended_resources": recommended_resources,
                "confidence": 0.85,
                "raw_context": context_text
            }
        
        except Exception as e:
            logger.error(f"DocumentRetrievalAgent: 执行失败: {e}", exc_info=True)
            yield {
                "type": "error",
                "content": f"文档检索失败: {str(e)}",
                "agent_type": "document_retrieval"
            }
