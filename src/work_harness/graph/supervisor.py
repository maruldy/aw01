from __future__ import annotations

import logging
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


logger = logging.getLogger("work_harness.graph.supervisor")


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
        route = route_map.get(event.source.value, "briefing")
        logger.info(
            "Triage: source=%s type=%s -> route=%s",
            event.source.value, event.event_type, route,
        )
        return {"route": route}

    async def _gather_context(self, state: SupervisorState) -> SupervisorState:
        event = state["event"]
        connector = self._connectors.get(event.source)
        logger.debug(
            "Gathering context: source=%s knowledge_svc=%s connector=%s",
            event.source.value, self._knowledge_service is not None,
            connector is not None,
        )
        if self._knowledge_service is not None:
            context = await self._knowledge_service.gather_context(event, connector)
        else:
            context = await connector.fetch_context(event) if connector else {}
        knowledge_mode = context.get("knowledge_mode") if isinstance(context, dict) else None
        logger.info(
            "Context gathered: source=%s mode=%s",
            event.source.value, knowledge_mode,
        )
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
        logger.info(
            "Proposal built: priority=%s agent=%s provider=%s",
            data["priority"], data["recommended_agent"],
            type(self._chat_provider).__name__,
        )
        return {"proposal_data": data}

    async def _create_work_item(self, state: SupervisorState) -> SupervisorState:
        event = state["event"]
        proposal_data = state["proposal_data"]
        logger.debug(
            "Creating work item: source=%s data=%s",
            event.source.value, proposal_data,
        )
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
            metadata=event.metadata,
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
        logger.info(
            "Work item created: id=%s thread=%s",
            work_item.id, work_item.thread_id,
        )
        return {"work_item": work_item, "run": run}

    async def handle_event(self, event: ActivityEvent) -> GraphResult:
        logger.info(
            "Supervisor handling: source=%s type=%s id=%s",
            event.source.value, event.event_type,
            event.external_id,
        )
        try:
            result = await self._graph.ainvoke({"event": event})
        except Exception:
            logger.exception(
                "Supervisor graph failed: source=%s type=%s",
                event.source.value, event.event_type,
            )
            raise
        logger.info("Supervisor completed: work_item_id=%s", result["work_item"].id)
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
