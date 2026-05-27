# Multi-Agent Workflow

The deep research flow uses a coordinator plus expert agents. The coordinator
returns a validated `AgentPlan` with selected agents, concrete tasks,
dependencies, parallel groups, and reasoning.

## Default Execution

1. `document_retrieval` runs first when selected.
2. Independent analysis agents run in parallel when dependencies allow it.
3. `critic` reviews prior agent outputs and evidence.
4. `summary` consumes `other_results` and synthesizes the final result.

## Agent Context

Expert agents receive:

- `task`: the concrete task for that agent.
- `agent_task`: the same task stored explicitly in context.
- `evidence`: evidence available from prior retrieval steps when present.
- `other_results`: completed upstream agent results.
- `conversation_history`: recent chat history.

## SSE Compatibility

The existing `planning`, `agent_status`, `agent_result`, `html`, and `done`
events remain. New fields include `run_id`, `dependencies`, `claims`,
`evidence_ids`, and `artifact`.
