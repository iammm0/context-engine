"""总结专家Agent"""
from typing import Dict, Any, Optional, AsyncGenerator, List
from agents.base.base_agent import BaseAgent
from utils.logger import logger


class SummaryAgent(BaseAgent):
    """总结专家 - 总结和归纳信息"""
    
    def get_default_model(self) -> str:
        """获取默认模型名称"""
        return "gpt-oss:20b"
    
    def get_prompt(self) -> str:
        """获取系统提示词"""
        return """你是总结专家，专门总结和归纳信息。

你的任务：
1. 总结关键信息
2. 归纳主要观点
3. 提炼核心概念
4. 组织信息结构"""
    
    async def execute(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        stream: bool = False
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行总结任务"""
        try:
            # 获取其他Agent的结果（如果有）
            other_results = context.get("other_results", []) if context else []
            evidence_ids = []
            for item in other_results:
                evidence_ids.extend(item.get("evidence_ids", []) or [])
            
            summary_prompt = f"""请总结以下信息：

问题：{task}

相关信息：
{self._format_other_results(other_results)}

请提供：
1. 核心要点总结
2. 关键概念归纳
3. 重要结论
4. 后续建议或下一步行动"""
            
            result = ""
            async for chunk in self._call_llm(prompt=self.merge_system_into_task_prompt(summary_prompt), stream=stream):
                result += chunk
                if stream:
                    yield {
                        "type": "chunk",
                        "content": chunk,
                        "agent_type": "summary"
                    }
            
            if result:
                yield {
                    "type": "complete",
                    "content": result,
                    "agent_type": "summary",
                    "evidence_ids": list(dict.fromkeys(evidence_ids)),
                    "claims": [{
                        "source_agent": "summary",
                        "content": result[:240],
                        "status": "synthesized",
                    }],
                    "confidence": 0.9
                }
        
        except Exception as e:
            logger.error(f"SummaryAgent: 执行失败: {e}", exc_info=True)
            yield {
                "type": "error",
                "content": f"总结失败: {str(e)}",
                "agent_type": "summary"
            }
    
    def _format_other_results(self, results: List[Dict[str, Any]]) -> str:
        """格式化其他Agent的结果"""
        if not results:
            return "暂无其他信息"
        
        formatted = []
        for result in results:
            agent_type = result.get("agent_type", "unknown")
            content = result.get("content", "")
            formatted.append(f"[{agent_type}]: {content[:500]}")  # 限制长度
        
        return "\n\n".join(formatted)
