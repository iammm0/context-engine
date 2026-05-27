"""Agent工作流编排 - 使用LangChain编排并行工作流"""
from typing import Dict, Any, Optional, List, AsyncGenerator
import asyncio
import time
import uuid
from utils.logger import logger

from agents.coordinator.coordinator_agent import CoordinatorAgent
from agents.experts.document_retrieval_agent import DocumentRetrievalAgent
from agents.experts.formula_analysis_agent import FormulaAnalysisAgent
from agents.experts.code_analysis_agent import CodeAnalysisAgent
from agents.experts.concept_explanation_agent import ConceptExplanationAgent
from agents.experts.example_generation_agent import ExampleGenerationAgent
from agents.experts.summary_agent import SummaryAgent
from agents.experts.exercise_agent import ExerciseAgent
from agents.experts.scientific_coding_agent import ScientificCodingAgent
from agents.experts.critic_agent import CriticAgent
from agents.experts.argument_analysis_agent import ArgumentAnalysisAgent


async def get_agent_config(agent_type: str) -> Dict[str, Optional[str]]:
    """从数据库获取 Agent 配置（兼容旧调用：含模型与提示覆盖）。"""
    from services.agent_settings import get_agent_config_from_db

    cfg = await get_agent_config_from_db(agent_type)
    return {
        "inference_model": cfg.get("inference_model"),
        "embedding_model": cfg.get("embedding_model"),
        "system_prompt": cfg.get("system_prompt"),
        "enabled": cfg.get("enabled", True),
    }


class AgentWorkflow:
    """Agent工作流编排器 - 管理多Agent协作"""
    
    # Agent类型映射
    AGENT_MAP = {
        "document_retrieval": DocumentRetrievalAgent,
        "formula_analysis": FormulaAnalysisAgent,
        "code_analysis": CodeAnalysisAgent,
        "concept_explanation": ConceptExplanationAgent,
        "example_generation": ExampleGenerationAgent,
        "summary": SummaryAgent,
        "exercise": ExerciseAgent,
        "scientific_coding": ScientificCodingAgent,
        "critic": CriticAgent,
        "argument_analysis": ArgumentAnalysisAgent,
    }
    
    def __init__(self):
        """初始化工作流编排器"""
        # Coordinator将在execute_workflow中初始化（需要异步加载配置）
        self.coordinator = None
        self.expert_agents = {}  # 专家Agent实例缓存
        self._agent_configs_cache = {}  # Agent配置缓存
        self._enabled_expert_types: List[str] = []
    
    async def _init_coordinator(self, generation_config: Optional[Dict[str, Any]] = None):
        """初始化协调型Agent（异步加载配置）"""
        if self.coordinator is None:
            from services.agent_settings import list_enabled_expert_types

            model_name = None
            if generation_config:
                model_name = generation_config.get("llm_model")

            if not model_name:
                config = await get_agent_config("coordinator")
                model_name = config.get("inference_model")

            enabled = await list_enabled_expert_types()
            if not enabled:
                logger.warning("所有专家子智能体均被禁用，回退为启用全部专家类型")
                enabled = list(self.AGENT_MAP.keys())
            self._enabled_expert_types = enabled

            coord_cfg = await get_agent_config("coordinator")
            prompt_ov = coord_cfg.get("system_prompt")

            self.coordinator = CoordinatorAgent(
                model_name=model_name,
                system_prompt_override=prompt_ov if prompt_ov else None,
                available_expert_types=enabled,
            )
    
    async def _get_expert_agent(self, agent_type: str, generation_config: Optional[Dict[str, Any]] = None):
        """获取专家Agent实例（延迟初始化，异步加载配置）"""
        if agent_type not in self.expert_agents:
            agent_class = self.AGENT_MAP.get(agent_type)
            if agent_class:
                model_name = None
                if generation_config:
                    model_name = generation_config.get("llm_model")

                if not model_name:
                    if agent_type not in self._agent_configs_cache:
                        self._agent_configs_cache[agent_type] = await get_agent_config(agent_type)

                    config = self._agent_configs_cache[agent_type]
                    model_name = config.get("inference_model")

                if agent_type not in self._agent_configs_cache:
                    self._agent_configs_cache[agent_type] = await get_agent_config(agent_type)
                cfg_full = self._agent_configs_cache[agent_type]
                prompt_ov = cfg_full.get("system_prompt")

                self.expert_agents[agent_type] = agent_class(
                    model_name=model_name,
                    system_prompt_override=prompt_ov if prompt_ov else None,
                )
            else:
                logger.warning(f"未知的Agent类型: {agent_type}")
                return None
        return self.expert_agents.get(agent_type)
    
    async def execute_workflow(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        enabled_agents: Optional[List[str]] = None,
        stream: bool = False
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行多Agent协作工作流
        
        Args:
            query: 用户问题
            context: 上下文信息
            enabled_agents: 启用的专家Agent列表（如果为None则使用所有Agent）
            stream: 是否流式输出
        
        Yields:
            包含Agent结果和状态的字典
        """
        try:
            # 0. 初始化协调型Agent（异步加载配置）
            generation_config = context.get("generation_config") if context else None
            await self._init_coordinator(generation_config)
            
            # 1. 协调Agent规划任务
            logger.info(f"AgentWorkflow: 开始规划任务 - {query[:50]}...")
            
            planning_context = context or {}
            planning_context["query"] = query
            
            selected_agents_from_coordinator = None
            agent_tasks = {}
            dependencies = {}
            parallel_groups = []
            planning_reasoning = ""
            run_id = str(uuid.uuid4())
            
            async for planning_result in self.coordinator.execute(
                task=query,
                context=planning_context,
                stream=False
            ):
                if planning_result.get("type") == "planning":
                    # 获取协调型Agent选择的Agent列表
                    selected_agents_from_coordinator = planning_result.get("selected_agents")
                    agent_tasks = planning_result.get("agent_tasks", {})
                    dependencies = planning_result.get("dependencies", {}) or {}
                    parallel_groups = planning_result.get("parallel_groups", []) or []
                    planning_reasoning = planning_result.get("reasoning", "")
                    
                    yield {
                        "type": "planning",
                        "run_id": run_id,
                        "content": planning_result.get("content", ""),
                        "agent_type": "coordinator",
                        "selected_agents": selected_agents_from_coordinator,
                        "agent_tasks": agent_tasks,
                        "dependencies": dependencies,
                        "parallel_groups": parallel_groups,
                        "reasoning": planning_reasoning
                    }
                    
                    # 发送所有Agent的初始状态（仅当前未被禁用的专家池）
                    if stream and selected_agents_from_coordinator:
                        pool = self._enabled_expert_types or list(self.AGENT_MAP.keys())
                        all_agent_types = pool
                        for agent_type in all_agent_types:
                            if agent_type in selected_agents_from_coordinator:
                                # 被选中的Agent，状态为pending（等待执行）
                                yield {
                                    "type": "agent_status",
                                    "run_id": run_id,
                                    "agent_type": agent_type,
                                    "status": "pending",
                                    "reason": "等待执行"
                                }
                            else:
                                # 未被选中的Agent，状态为skipped
                                yield {
                                    "type": "agent_status",
                                    "run_id": run_id,
                                    "agent_type": agent_type,
                                    "status": "skipped",
                                    "reason": planning_reasoning or "协调型Agent未选择此Agent"
                                }
            
            # 2. 确定要执行的专家Agent
            if enabled_agents:
                # 如果手动指定了Agent，使用指定的
                agent_types = enabled_agents
                logger.info(f"AgentWorkflow: 使用手动指定的Agent列表: {agent_types}")
            elif selected_agents_from_coordinator:
                # 使用协调型Agent选择的Agent列表
                agent_types = selected_agents_from_coordinator
                logger.info(f"AgentWorkflow: 协调型Agent选择了 {len(agent_types)} 个Agent: {agent_types}")
                logger.info(f"AgentWorkflow: 选择理由: {planning_reasoning}")
            else:
                # 后备方案：使用当前启用的全部专家
                agent_types = list(self._enabled_expert_types) if self._enabled_expert_types else list(self.AGENT_MAP.keys())
                logger.warning(f"AgentWorkflow: 协调型Agent未返回选择结果，使用启用中的专家: {agent_types}")
            
            # 验证Agent类型有效性且未被禁用
            valid_agent_types = set(self.AGENT_MAP.keys())
            allowed = set(self._enabled_expert_types or list(self.AGENT_MAP.keys()))
            agent_types = [a for a in agent_types if a in valid_agent_types and a in allowed]
            
            if not agent_types:
                logger.warning("AgentWorkflow: 没有有效的Agent类型，使用默认Agent")
                agent_types = ["concept_explanation"]

            dependencies = self._sanitize_dependencies(dependencies, agent_types)
            execution_groups = self._build_execution_groups(agent_types, dependencies, parallel_groups)
            
            logger.info(f"AgentWorkflow: 将执行 {len(agent_types)} 个专家Agent: {agent_types}")
            
            # 3. 顺序执行专家Agent（以便前端可以实时显示进度）
            expert_context = context or {}
            expert_context["query"] = query
            # 将Agent任务描述添加到上下文中
            if agent_tasks:
                expert_context["agent_tasks"] = agent_tasks
            expert_context["run_id"] = run_id
            expert_context["dependencies"] = dependencies
            
            agent_results = []
            
            # 注意：Agent的初始状态已经在planning事件中发送了
            # 这里只需要确保第一个Agent开始执行
            
            for group in execution_groups:
                group = [agent_type for agent_type in group if agent_type in agent_types]
                if not group:
                    continue

                if len(group) > 1:
                    if stream:
                        for agent_type in group:
                            yield {
                                "type": "agent_status",
                                "run_id": run_id,
                                "agent_type": agent_type,
                                "status": "running",
                                "current_step": "并行执行中...",
                                "progress": 0,
                                "started_at": int(time.time() * 1000),
                                "dependencies": dependencies.get(agent_type, []),
                            }

                    async def _run_parallel(agent_type: str) -> Dict[str, Any]:
                        agent = await self._get_expert_agent(agent_type, generation_config)
                        if not agent:
                            return {
                                "agent_type": agent_type,
                                "content": "Agent未找到",
                                "error": True,
                            }
                        ctx = dict(expert_context)
                        ctx["other_results"] = list(agent_results)
                        ctx["agent_task"] = agent_tasks.get(agent_type, query)
                        return await self._execute_expert_agent(
                            agent,
                            agent_type,
                            agent_tasks.get(agent_type, query),
                            ctx,
                            stream=False,
                        )

                    group_results = await asyncio.gather(*[_run_parallel(agent_type) for agent_type in group])
                    for result in group_results:
                        agent_results.append(result)
                        if stream:
                            status = "error" if result.get("error") else "completed"
                            yield {
                                "type": "agent_status",
                                "run_id": run_id,
                                "agent_type": result.get("agent_type"),
                                "status": status,
                                "progress": 100 if not result.get("error") else 0,
                                "completed_at": int(time.time() * 1000),
                                "details": result.get("content") if result.get("error") else None,
                                "dependencies": dependencies.get(result.get("agent_type"), []),
                            }
                            if not result.get("error"):
                                yield {
                                    "type": "agent_result",
                                    "run_id": run_id,
                                    "agent_type": result.get("agent_type"),
                                    "content": result.get("content", ""),
                                    "sources": result.get("sources", []),
                                    "evidence": result.get("evidence", []),
                                    "evidence_ids": result.get("evidence_ids", []),
                                    "claims": result.get("claims", []),
                                    "open_questions": result.get("open_questions", []),
                                    "confidence": result.get("confidence", 0.5),
                                    "dependencies": dependencies.get(result.get("agent_type"), []),
                                }
                    continue

                agent_type = group[0]
                if stream:
                    yield {
                        "type": "agent_status",
                        "run_id": run_id,
                        "agent_type": agent_type,
                        "status": "running",
                        "current_step": "开始工作...",
                        "progress": 0,
                        "started_at": int(time.time() * 1000),
                        "dependencies": dependencies.get(agent_type, []),
                    }

                try:
                    agent = await self._get_expert_agent(agent_type, generation_config)
                    if not agent:
                        logger.warning(f"AgentWorkflow: {agent_type} 未找到，跳过")
                        if stream:
                            yield {
                                "type": "agent_status",
                                "run_id": run_id,
                                "agent_type": agent_type,
                                "status": "error",
                                "details": "Agent未找到",
                            }
                        continue

                    result_content = ""
                    sources = []
                    evidence = []
                    evidence_ids = []
                    claims = []
                    open_questions = []
                    confidence = 0.5
                    progress = 0
                    ctx = dict(expert_context)
                    ctx["other_results"] = list(agent_results)
                    ctx["agent_task"] = agent_tasks.get(agent_type, query)
                    task_for_agent = agent_tasks.get(agent_type, query)

                    async for result in agent.execute(task=task_for_agent, context=ctx, stream=stream):
                        if result.get("type") == "complete":
                            result_content = result.get("content", "")
                            sources = result.get("sources", [])
                            evidence = result.get("evidence", [])
                            evidence_ids = result.get("evidence_ids", [])
                            claims = result.get("claims", [])
                            open_questions = result.get("open_questions", [])
                            confidence = result.get("confidence", 0.5)
                            progress = 100

                            if stream:
                                yield {
                                    "type": "agent_status",
                                    "run_id": run_id,
                                    "agent_type": agent_type,
                                    "status": "completed",
                                    "progress": 100,
                                    "completed_at": int(time.time() * 1000),
                                    "dependencies": dependencies.get(agent_type, []),
                                }

                                yield {
                                    "type": "agent_result",
                                    "run_id": run_id,
                                    "agent_type": agent_type,
                                    "content": result_content,
                                    "sources": sources,
                                    "evidence": evidence,
                                    "evidence_ids": evidence_ids,
                                    "claims": claims,
                                    "open_questions": open_questions,
                                    "confidence": confidence,
                                    "dependencies": dependencies.get(agent_type, []),
                                }
                        elif result.get("type") == "chunk" and stream:
                            result_content += result.get("content", "")
                            progress = min(progress + 2, 95)
                            yield {
                                "type": "agent_status",
                                "run_id": run_id,
                                "agent_type": agent_type,
                                "status": "running",
                                "current_step": result.get("current_step", "正在生成内容..."),
                                "progress": progress,
                                "dependencies": dependencies.get(agent_type, []),
                            }
                        elif result.get("type") == "status" and stream:
                            yield {
                                "type": "agent_status",
                                "run_id": run_id,
                                "agent_type": agent_type,
                                "status": result.get("status", "running"),
                                "current_step": result.get("current_step"),
                                "progress": result.get("progress", progress),
                                "details": result.get("details"),
                                "dependencies": dependencies.get(agent_type, []),
                            }

                    agent_results.append({
                        "agent_type": agent_type,
                        "content": result_content,
                        "sources": sources,
                        "evidence": evidence,
                        "evidence_ids": evidence_ids,
                        "claims": claims,
                        "open_questions": open_questions,
                        "confidence": confidence,
                        "error": False
                    })

                except Exception as e:
                    logger.error(f"AgentWorkflow: {agent_type} 执行失败: {e}", exc_info=True)
                    error_msg = f"执行失败: {str(e)}"
                    agent_results.append({
                        "agent_type": agent_type,
                        "content": error_msg,
                        "error": True
                    })
                    if stream:
                        yield {
                            "type": "agent_status",
                            "run_id": run_id,
                            "agent_type": agent_type,
                            "status": "error",
                            "details": error_msg,
                            "dependencies": dependencies.get(agent_type, []),
                        }
            
            # 5. 返回所有结果
            yield {
                "type": "complete",
                "run_id": run_id,
                "agent_results": agent_results,
                "selected_agents": agent_types,
                "dependencies": dependencies,
                "parallel_groups": execution_groups,
                "artifact": {
                    "query": query,
                    "agent_results": agent_results,
                    "dependencies": dependencies,
                    "parallel_groups": execution_groups,
                },
                "total_agents": len(agent_types),
                "successful_agents": len([r for r in agent_results if not r.get("error")])
            }
        
        except Exception as e:
            logger.error(f"AgentWorkflow: 工作流执行失败: {e}", exc_info=True)
            yield {
                "type": "error",
                "content": f"工作流执行失败: {str(e)}"
            }
    
    async def _execute_expert_agent(
        self,
        agent,
        agent_type: str,
        task: str,
        context: Dict[str, Any],
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        执行单个专家Agent任务
        
        Args:
            agent: Agent实例
            agent_type: Agent类型
            task: 任务描述
            context: 上下文信息
            stream: 是否流式输出
        
        Returns:
            Agent执行结果
        """
        try:
            result_content = ""
            sources = []
            evidence = []
            evidence_ids = []
            claims = []
            open_questions = []
            confidence = 0.5
            
            async for result in agent.execute(task=task, context=context, stream=stream):
                if result.get("type") == "complete":
                    result_content = result.get("content", "")
                    sources = result.get("sources", [])
                    evidence = result.get("evidence", [])
                    evidence_ids = result.get("evidence_ids", [])
                    claims = result.get("claims", [])
                    open_questions = result.get("open_questions", [])
                    confidence = result.get("confidence", 0.5)
                elif result.get("type") == "chunk" and stream:
                    result_content += result.get("content", "")
            
            return {
                "agent_type": agent_type,
                "content": result_content,
                "sources": sources,
                "evidence": evidence,
                "evidence_ids": evidence_ids,
                "claims": claims,
                "open_questions": open_questions,
                "confidence": confidence,
                "error": False
            }
        
        except Exception as e:
            logger.error(f"执行 {agent_type} Agent失败: {e}", exc_info=True)
            return {
                "agent_type": agent_type,
                "content": f"执行失败: {str(e)}",
                "error": True
            }

    def _sanitize_dependencies(self, dependencies: Dict[str, List[str]], agent_types: List[str]) -> Dict[str, List[str]]:
        allowed = set(agent_types)
        clean: Dict[str, List[str]] = {}
        for agent_type, deps in (dependencies or {}).items():
            if agent_type not in allowed:
                continue
            clean[agent_type] = [dep for dep in deps if dep in allowed and dep != agent_type]
        if "critic" in allowed and "critic" not in clean:
            clean["critic"] = [a for a in agent_types if a not in {"critic", "summary"}]
        if "summary" in allowed and "summary" not in clean:
            clean["summary"] = [a for a in agent_types if a != "summary"]
        return clean

    def _build_execution_groups(
        self,
        agent_types: List[str],
        dependencies: Dict[str, List[str]],
        parallel_groups: Optional[List[List[str]]] = None,
    ) -> List[List[str]]:
        pending = list(agent_types)
        completed = set()
        groups: List[List[str]] = []

        # Prefer retrieval as the first evidence-producing step whenever selected.
        if "document_retrieval" in pending:
            groups.append(["document_retrieval"])
            pending.remove("document_retrieval")
            completed.add("document_retrieval")

        while pending:
            ready = [
                agent_type
                for agent_type in pending
                if all(dep in completed for dep in dependencies.get(agent_type, []))
            ]
            if not ready:
                # Break dependency cycles gracefully by advancing one agent.
                ready = [pending[0]]

            # Keep synthesis-style agents late even if a planner forgets dependencies.
            if len(ready) > 1:
                ready = [a for a in ready if a not in {"critic", "summary"}] or ready

            groups.append(ready)
            for agent_type in ready:
                if agent_type in pending:
                    pending.remove(agent_type)
                completed.add(agent_type)

        return groups
