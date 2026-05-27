"""协调型Agent - 分析用户问题，规划研究任务，分发给专家Agent"""
from typing import Dict, Any, Optional, List, AsyncGenerator
from agents.base.base_agent import BaseAgent
from utils.logger import logger
from models.rag import AgentPlan


class CoordinatorAgent(BaseAgent):
    """协调型Agent - 负责任务规划和分发"""
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        system_prompt_override: Optional[str] = None,
        available_expert_types: Optional[List[str]] = None,
    ):
        """初始化协调型Agent。available_expert_types 为当前允许调度的专家（未禁用的子智能体）。"""
        super().__init__(
            model_name=model_name or "deepseek-r1:8b",
            base_url=base_url,
            system_prompt_override=system_prompt_override,
        )
        self.expert_agents = {}  # 专家Agent实例缓存
        if available_expert_types is not None:
            self._available_expert_types = list(available_expert_types)
        else:
            from agents.workflow.agent_workflow import AgentWorkflow

            self._available_expert_types = list(AgentWorkflow.AGENT_MAP.keys())
    
    def get_default_model(self) -> str:
        """获取默认模型名称"""
        return "deepseek-r1:8b"
    
    def get_prompt(self) -> str:
        """获取系统提示词"""
        return """你是一个研究任务协调者，负责分析用户问题并智能选择需要的专家Agent。

你的职责：
1. 分析用户问题的复杂度和需求
2. 判断需要哪些专家Agent参与（只选择必要的，不要选择所有Agent）
3. 为每个选中的Agent分配具体任务
4. 说明选择每个Agent的理由

可用的专家Agent：
- document_retrieval: 文档检索专家（当问题涉及文档、资料、知识库查询时使用）
- formula_analysis: 公式分析专家（当问题涉及数学表达式、统计公式、指标计算、符号推导时使用）
- code_analysis: 代码分析专家（当问题涉及代码理解、代码解释、代码逻辑分析时使用）
- concept_explanation: 概念解释专家（当问题需要深入解释概念、方法、机制、理论时使用）
- example_generation: 示例生成专家（当问题需要实际应用示例、案例、实例时使用）
- exercise: 练习设计专家（当问题需要生成练习、题目、演练过程时使用）
- scientific_coding: 实现方案专家（当问题需要脚本、自动化、数据处理或原型代码时使用）
- critic: 批判性分析专家（当需要检查漏洞、反例、证据不足、潜在幻觉时使用）
- argument_analysis: 论证分析专家（当需要拆解复杂问题、明确假设和推理链时使用）
- summary: 总结专家（当需要总结和归纳多个Agent的研究结果时使用，通常最后调用）

**重要原则**：
- 默认优先围绕 RAG 主链路组织工作：文档检索 -> 论证分析/概念解释 -> 批判性校验 -> 总结归纳
- 只选择真正需要的Agent，不要选择所有Agent
- 如果问题很简单，可能只需要1-2个Agent
- 如果问题很复杂，可能需要3-5个Agent
- 必须返回JSON格式的结果，包含选中的Agent列表

请以JSON格式返回规划结果：
{
    "selected_agents": ["agent_type1", "agent_type2", ...],
    "agent_tasks": {
        "agent_type1": "具体任务描述1",
        "agent_type2": "具体任务描述2"
    },
    "reasoning": "选择这些Agent的理由"
}"""
    
    async def execute(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        stream: bool = False
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行协调任务
        
        Args:
            task: 用户问题
            context: 上下文信息
            stream: 是否流式输出
        
        Yields:
            包含任务规划结果的字典
        """
        try:
            # 1. 分析问题并规划任务
            logger.info(f"CoordinatorAgent: 开始分析问题 - {task[:50]}...")
            
            allowed_lines = "\n".join([f"- {a}" for a in self._available_expert_types])
            base_instructions = self.get_effective_prompt()
            planning_prompt = f"""{base_instructions}

---

用户问题：{task}

请分析这个问题，智能选择需要的专家Agent（只选择必要的，不要选择所有Agent），并说明每个Agent的具体任务。

请严格按照以下JSON格式返回（不要添加任何其他文本）：
{{
    "selected_agents": ["agent_type1", "agent_type2"],
    "agent_tasks": {{
        "agent_type1": "具体任务描述1",
        "agent_type2": "具体任务描述2"
    }},
    "dependencies": {{
        "summary": ["document_retrieval", "critic"]
    }},
    "parallel_groups": [["concept_explanation", "argument_analysis"], ["critic"], ["summary"]],
    "reasoning": "选择这些Agent的理由"
}}

当前允许使用的 agent_type（必须且仅能从中选择，不要发明新类型）：
{allowed_lines}

请只返回JSON，不要添加任何解释性文字。"""
            
            planning_result = ""
            plan = None
            for attempt in range(2):
                planning_result = ""
                async for chunk in self._call_llm(prompt=planning_prompt, stream=False):
                    planning_result += chunk
                plan = self._parse_agent_plan(planning_result)
                if plan is not None:
                    break
                logger.warning(f"CoordinatorAgent: 规划JSON解析失败，尝试重试 {attempt + 1}/2")

            if plan is None:
                selected_agents = self._fallback_agent_selection(task)
                plan = AgentPlan(
                    selected_agents=selected_agents,
                    agent_tasks={a: task for a in selected_agents},
                    dependencies=self._default_dependencies(selected_agents),
                    parallel_groups=self._default_parallel_groups(selected_agents),
                    reasoning="JSON解析失败，使用默认选择逻辑",
                )

            selected_agents = plan.selected_agents
            agent_tasks = plan.agent_tasks
            reasoning = plan.reasoning
            
            # 验证选中的Agent是否有效且未被禁用
            valid_agents = set(self._available_expert_types)
            selected_agents = [a for a in selected_agents if a in valid_agents]
            
            # 如果解析失败或没有选中任何Agent，使用默认选择
            if not selected_agents:
                logger.warning("CoordinatorAgent: 未选中任何Agent，使用默认选择")
                selected_agents = self._fallback_agent_selection(task)
                plan.selected_agents = selected_agents
                plan.agent_tasks = {a: task for a in selected_agents}

            plan.selected_agents = selected_agents
            plan.dependencies = self._sanitize_dependencies(plan.dependencies, selected_agents)
            plan.parallel_groups = self._sanitize_parallel_groups(plan.parallel_groups, selected_agents)
            if not plan.parallel_groups:
                plan.parallel_groups = self._default_parallel_groups(selected_agents)
            
            logger.info(f"CoordinatorAgent: 任务规划完成，选中 {len(selected_agents)} 个Agent: {selected_agents}")
            
            # 2. 返回规划结果
            yield {
                "type": "planning",
                "content": planning_result,
                "agent_type": "coordinator",
                "selected_agents": selected_agents,
                "agent_tasks": plan.agent_tasks,
                "dependencies": plan.dependencies,
                "parallel_groups": plan.parallel_groups,
                "reasoning": reasoning
            }
            
            # 3. 后续会由工作流编排器执行具体的专家Agent任务
            # 这里只负责规划，不执行具体任务
        
        except Exception as e:
            logger.error(f"CoordinatorAgent: 规划失败: {e}", exc_info=True)
            yield {
                "type": "error",
                "content": f"任务规划失败: {str(e)}",
                "agent_type": "coordinator"
            }

    def _parse_agent_plan(self, planning_text: str) -> Optional[AgentPlan]:
        import json
        import re

        try:
            json_match = re.search(r'\{[\s\S]*\}', planning_text)
            payload = json_match.group(0) if json_match else planning_text
            parsed = json.loads(payload)
            return AgentPlan.model_validate(parsed)
        except Exception as e:
            logger.warning(f"CoordinatorAgent: AgentPlan 校验失败: {e}")
            return None

    def _sanitize_dependencies(self, dependencies: Dict[str, List[str]], selected_agents: List[str]) -> Dict[str, List[str]]:
        selected = set(selected_agents)
        clean: Dict[str, List[str]] = {}
        for agent, deps in (dependencies or {}).items():
            if agent not in selected:
                continue
            clean[agent] = [d for d in deps if d in selected and d != agent]
        return clean

    def _default_dependencies(self, selected_agents: List[str]) -> Dict[str, List[str]]:
        selected = set(selected_agents)
        deps: Dict[str, List[str]] = {}
        if "critic" in selected:
            deps["critic"] = [a for a in selected_agents if a not in {"critic", "summary"}]
        if "summary" in selected:
            deps["summary"] = [a for a in selected_agents if a != "summary"]
        return deps

    def _default_parallel_groups(self, selected_agents: List[str]) -> List[List[str]]:
        selected = list(selected_agents)
        groups: List[List[str]] = []
        if "document_retrieval" in selected:
            groups.append(["document_retrieval"])
        middle = [a for a in selected if a not in {"document_retrieval", "critic", "summary"}]
        if middle:
            groups.append(middle)
        if "critic" in selected:
            groups.append(["critic"])
        if "summary" in selected:
            groups.append(["summary"])
        return groups or [selected]

    def _sanitize_parallel_groups(self, parallel_groups: List[List[str]], selected_agents: List[str]) -> List[List[str]]:
        selected = set(selected_agents)
        clean: List[List[str]] = []
        placed = set()
        for group in parallel_groups or []:
            valid = [a for a in group if a in selected and a not in placed]
            if valid:
                placed.update(valid)
                clean.append(valid)
        missing = [a for a in selected_agents if a not in placed]
        if missing:
            clean.extend(self._default_parallel_groups(missing))
        return clean
    
    def _fallback_agent_selection(self, task: str) -> List[str]:
        """
        后备Agent选择逻辑（当JSON解析失败时使用）
        
        Args:
            task: 用户问题
        
        Returns:
            选中的Agent类型列表
        """
        task_lower = task.lower()
        selected = []

        # 默认优先：复杂问题先做检索与理解
        if any(kw in task_lower for kw in ["文档", "资料", "知识库", "检索", "查询", "根据材料", "结合资料", "总结文档"]):
            selected.append("document_retrieval")
        if any(kw in task_lower for kw in ["分析", "拆解", "论证", "假设", "前提", "框架", "思路", "复杂", "研究"]):
            selected.append("argument_analysis")
        if any(kw in task_lower for kw in ["概念", "理论", "原理", "解释", "是什么", "为什么", "机制", "方法"]):
            selected.append("concept_explanation")
        if any(kw in task_lower for kw in ["质疑", "漏洞", "反驳", "幻觉", "校验", "验证", "是否可靠", "证据", "风险", "局限"]):
            selected.append("critic")

        # 根据关键词选择Agent
        if any(kw in task_lower for kw in ["公式", "表达式", "推导", "计算", "数学", "统计", "指标", "equation", "="]):
            selected.append("formula_analysis")

        if any(kw in task_lower for kw in ["代码", "程序", "编程", "算法"]):
            selected.append("code_analysis")

        if any(kw in task_lower for kw in ["示例", "例子", "案例", "应用"]):
            selected.append("example_generation")

        if any(kw in task_lower for kw in ["习题", "题目", "练习", "解题", "训练", "演练"]):
            selected.append("exercise")

        if any(kw in task_lower for kw in ["python", "javascript", "js", "sql", "脚本", "自动化", "代码实现", "原型", "接口", "api", "数据处理", "可视化"]):
            selected.append("scientific_coding")

        if "argument_analysis" not in selected and any(kw in task_lower for kw in ["分析思路", "推理链"]):
            selected.append("argument_analysis")
        
        # 如果问题比较复杂，添加总结Agent
        if len(selected) > 2 and "summary" in self._available_expert_types:
            selected.append("summary")
        
        # 如果什么都没选中，至少选择概念解释（若仍启用）
        if not selected:
            if "concept_explanation" in self._available_expert_types:
                selected = ["concept_explanation"]
            elif self._available_expert_types:
                selected = [self._available_expert_types[0]]
        
        return [a for a in selected if a in self._available_expert_types]
    
    def parse_planning_result(self, planning_text: str) -> List[Dict[str, Any]]:
        """
        解析规划结果，提取需要调用的专家Agent列表
        
        Args:
            planning_text: LLM返回的规划文本
        
        Returns:
            专家Agent任务列表
        """
        import json
        import re
        
        try:
            json_match = re.search(r'\{[\s\S]*\}', planning_text)
            if json_match:
                json_str = json_match.group(0)
                parsed = json.loads(json_str)
                selected_agents = parsed.get("selected_agents", [])
                agent_tasks = parsed.get("agent_tasks", {})
                
                return [
                    {
                        "type": agent_type,
                        "task": agent_tasks.get(agent_type, f"{agent_type}的任务"),
                        "priority": i + 1
                    }
                    for i, agent_type in enumerate(selected_agents)
                ]
        except Exception as e:
            logger.warning(f"解析规划结果失败: {e}")
        
        # 后备方案
        return [
            {"type": "concept_explanation", "task": "解释核心概念", "priority": 1},
        ]
