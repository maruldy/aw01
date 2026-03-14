from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from work_harness.domain.models import (
    ActivityEvent,
    ExecutionRun,
    GraphResult,
    RunStatus,
    WorkItem,
    WorkProposal,
)
from work_harness.providers.base import ChatModelProvider
from work_harness.providers.rule_based import RuleBasedChatProvider
from work_harness.services.knowledge_service import KnowledgeService


class SupervisorState(TypedDict, total=False):
    event: ActivityEvent
    route: str
    context: dict[str, Any]
    proposal_data: dict[str, Any]
    work_item: WorkItem
    run: ExecutionRun


class SupervisorService:
    def __init__(
        self,
        chat_provider: ChatModelProvider | None = None,
        connectors: dict | None = None,
        knowledge_service: KnowledgeService | None = None,
    ) -> None:
        self._chat_provider = chat_provider or RuleBasedChatProvider()
        self._connectors = connectors or {}
        self._knowledge_service = knowledge_service
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(SupervisorState)
        graph.add_node("triage", self._triage)
        graph.add_node("gather_context", self._gather_context)
        graph.add_node("build_proposal", self._build_proposal)
        graph.add_node("create_work_item", self._create_work_item)
        graph.add_edge(START, "triage")
        graph.add_edge("triage", "gather_context")
        graph.add_edge("gather_context", "build_proposal")
        graph.add_edge("build_proposal", "create_work_item")
        graph.add_edge("create_work_item", END)
        return graph.compile()

    async def _triage(self, state: SupervisorState) -> SupervisorState:
        event = state["event"]
        route_map = {
            "slack": "slack_context",
            "github": "github_change",
            "jira": "atlassian_context",
            "confluence": "atlassian_context",
        }
        return {"route": route_map.get(event.source.value, "briefing")}

    async def _gather_context(self, state: SupervisorState) -> SupervisorState:
        event = state["event"]
        connector = self._connectors.get(event.source)
        if self._knowledge_service is not None:
            context = await self._knowledge_service.gather_context(event, connector)
        else:
            context = await connector.fetch_context(event) if connector else {}
        return {"context": context}

    async def _build_proposal(self, state: SupervisorState) -> SupervisorState:
        event = state["event"]
        route = state["route"]
        context = state.get("context", {})
        prompt = (
            f"Source: {event.source.value}\n"
            f"Event type: {event.event_type}\n"
            f"Route: {route}\n"
            f"Title: {event.title}\n"
            f"Body: {event.body}\n"
            f"Context: {context}"
        )
        schema = {
            "title": "WorkProposal",
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "suggested_action": {"type": "string"},
                "priority": {"type": "string"},
                "recommended_agent": {"type": "string"},
            },
            "required": ["summary", "suggested_action", "priority", "recommended_agent"],
        }
        completion = await self._chat_provider.complete_json(prompt, schema)
        data = completion.data or {}
        data.setdefault("summary", f"Review new {event.source.value} activity.")
        data.setdefault("suggested_action", "Inspect the work item and decide next action.")
        data.setdefault("priority", "medium")
        data.setdefault("recommended_agent", route)
        return {"proposal_data": data}

    async def _create_work_item(self, state: SupervisorState) -> SupervisorState:
        event = state["event"]
        proposal_data = state["proposal_data"]
        proposal = WorkProposal(
            summary=proposal_data["summary"],
            suggested_action=proposal_data["suggested_action"],
            priority=proposal_data["priority"],
            recommended_agent=proposal_data["recommended_agent"],
            context_notes=self._build_context_notes(state),
        )
        work_item = WorkItem(
            source=event.source,
            event_type=event.event_type,
            title=event.title,
            body=event.body,
            external_id=event.external_id,
            actor=event.actor,
            proposal=proposal,
        )
        run = ExecutionRun(
            thread_id=work_item.thread_id,
            work_item_id=work_item.id,
            status=RunStatus.WAITING,
            current_step="proposal_ready",
            events=[
                {"type": "triage", "route": state["route"]},
                {"type": "proposal", "summary": proposal.summary},
            ],
        )
        return {"work_item": work_item, "run": run}

    async def handle_event(self, event: ActivityEvent) -> GraphResult:
        result = await self._graph.ainvoke({"event": event})
        return GraphResult(work_item=result["work_item"], run=result["run"])

    def _build_context_notes(self, state: SupervisorState) -> list[str]:
        notes = [f"Route selected: {state['route']}"]
        context = state.get("context", {})
        knowledge_hits = context.get("knowledge_hits", []) if isinstance(context, dict) else []
        for hit in knowledge_hits[:2]:
            notes.append(f"Similar knowledge: {hit['summary']}")
        if isinstance(context, dict) and context.get("knowledge_mode") == "remote_fallback":
            notes.append("No local knowledge hit. Used scoped remote context.")
        return notes
