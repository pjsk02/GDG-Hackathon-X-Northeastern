"""HTTP surface for the agent. Run: make api  ->  http://127.0.0.1:8000/docs"""

import logging
import mimetypes
import threading
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.pipeline import Agent
from api import a2ui
from sentinel import ticket_store
from sentinel.outage import OutageTracker
from sentinel.pipeline import SentinelAgent
from shared.contracts import AgentAnswer, AskRequest, RetrievedChunk, SentinelResult, TicketInput

A2UI_PAGE = Path(__file__).parent / "static" / "a2ui.html"
SENTINELDESK_PAGE = Path(__file__).parent / "static" / "sentineldesk.html"
PROVIDERS = ["extractive", "ollama", "gemini"]

log = logging.getLogger("uvicorn.error")
WARM_UP: dict[str, str] = {}  # component -> "pending" | "ok" | error; shown on /health
_OUTAGE_TRACKER = OutageTracker()


@lru_cache
def get_agent() -> Agent:
    return Agent()


@lru_cache
def get_sentinel_agent() -> SentinelAgent:
    try:
        agent = SentinelAgent()
        agent.warm_up()
        return agent
    except FileNotFoundError:
        from agent.llm_router import LLMRouter
        from memory.embedder import HashEmbedder
        from memory.store import VectorStore
        from shared.settings import Settings
        from ui.shared import _DemoTriageModel

        settings = Settings(llm_provider="extractive", llm_fallback="", warm_up=False)
        store = VectorStore(":memory:", HashEmbedder())
        return SentinelAgent(
            settings=settings,
            store=store,
            router=LLMRouter(settings),
            triage_model=_DemoTriageModel(),
        )


def _warm_up() -> None:
    WARM_UP["status"] = "pending"
    result = get_agent().warm_up()
    WARM_UP.clear()
    WARM_UP.update(result or {"status": "nothing to warm"})
    log.info("warm-up: %s", WARM_UP)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # In a background thread so the server accepts requests immediately; a question asked
    # during warm-up simply waits on the same model load instead of hitting a cold 500.
    if get_agent().settings.warm_up:
        threading.Thread(target=_warm_up, name="warm-up", daemon=True).start()
    yield


app = FastAPI(title="Grounded Agent API", version="0.1.0", lifespan=lifespan)
# No wildcard CORS (audit M1): with "*", any website open in the browser could read /search and
# /ask from this unauthenticated local API. The A2UI page is same-origin and needs no CORS.
# Add specific dev origins here (e.g. a separate React dev server) only if one is used.
CORS_ORIGINS: list[str] = []
if CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"])

# Vendored A2UI renderer (tools/vendor_a2ui.py). Browsers refuse ES modules unless served as JS,
# and Windows' registry often has no type for .mjs.
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/javascript", ".js")
VENDOR_DIR = Path(__file__).parent / "static" / "vendor"
if VENDOR_DIR.is_dir():
    app.mount("/vendor", StaticFiles(directory=VENDOR_DIR), name="vendor")


@app.get("/health")
def health() -> dict:
    agent = get_agent()
    return {
        "status": "ok",
        "chunks": agent.store.count(),
        "embedder": agent.store.embedder.name,
        "provider": agent.settings.llm_provider,
        "model": agent.router.model_name(),
        "fallback_chain": agent.provider_chain(),
        "cooling_down": agent.cooling_down(),
        "warm_up": WARM_UP,
    }


@app.post("/ask", response_model=AgentAnswer)
def ask(req: AskRequest) -> AgentAnswer:
    return get_agent().ask(req.question, k=req.k, provider=req.provider, fallback=req.fallback)


class CustomerTriageResponse(BaseModel):
    """Customer-safe triage response: status and approved reply only."""

    ticket_id: str
    status: Literal["Received", "In progress", "Replied"]
    reply: str | None = None


@app.post("/triage", response_model=SentinelResult | CustomerTriageResponse)
def triage_ticket(
    req: TicketInput,
    x_role: str = Header(default="customer", alias="X-Role"),
) -> SentinelResult | CustomerTriageResponse:
    role = x_role.strip().lower()
    if role not in ("customer", "agent", "manager"):
        raise HTTPException(422, f"Invalid X-Role {x_role!r}; expected customer, agent, or manager")

    agent = get_sentinel_agent()
    result = agent.triage(req.subject, req.body, k=req.k, provider=req.provider, fallback=req.fallback)
    ticket_id = ticket_store.add_ticket(req.subject, req.body, source="api")
    ticket_store.save_result(ticket_id, result)
    _OUTAGE_TRACKER.observe(result)

    if role == "customer":
        approved = result.tier == "AUTO_DRAFT" and result.grounded and bool(result.draft_reply)
        if approved:
            ticket_store.set_status(ticket_id, "replied")
            return CustomerTriageResponse(ticket_id=ticket_id, status="Replied", reply=result.draft_reply)
        return CustomerTriageResponse(ticket_id=ticket_id, status="In progress", reply=None)

    return result


@app.get("/tickets")
def list_stored_tickets(x_role: str = Header(default="customer", alias="X-Role")) -> list[dict[str, Any]]:
    """List tickets from ticket_store, filtered by caller role."""
    role = x_role.strip().lower()
    if role not in ("customer", "agent", "manager"):
        raise HTTPException(422, f"Invalid X-Role {x_role!r}; expected customer, agent, or manager")
    records = ticket_store.list_tickets()
    if role == "customer":
        out: list[dict[str, Any]] = []
        for r in records:
            if r.status in ("new", "queued", "processing"):
                c_status = "Received"
            elif r.status == "triaged":
                c_status = "In progress"
            else:
                c_status = "Replied"
            reply = r.result.draft_reply if (c_status == "Replied" and r.result) else None
            out.append(
                {
                    "ticket_id": r.ticket_id,
                    "subject": r.subject,
                    "body": r.body,
                    "status": c_status,
                    "created_at": r.created_at,
                    "reply": reply,
                }
            )
        return out
    return [r.model_dump() for r in records]


class TicketActionRequest(BaseModel):
    status: Literal["replied", "closed"]


@app.post("/tickets/{ticket_id}/action")
def update_ticket_status(ticket_id: str, req: TicketActionRequest) -> dict[str, Any]:
    """Approve/close a ticket in ticket_store."""
    rec = ticket_store.get_ticket(ticket_id)
    if rec is None:
        raise HTTPException(404, f"Ticket {ticket_id!r} not found")
    ticket_store.set_status(ticket_id, req.status)
    updated = ticket_store.get_ticket(ticket_id)
    return updated.model_dump() if updated else {"ticket_id": ticket_id, "status": req.status}


@app.get("/outage")
def get_outage_status() -> dict[str, Any]:
    """Return active OutageTracker burst alert if present."""
    alert = _OUTAGE_TRACKER.check()
    if not alert:
        return {"active": False}
    return {
        "active": True,
        "headline": alert.headline,
        "ticket_count": alert.ticket_count,
        "shared_precedents": alert.shared_precedents,
        "subjects": alert.subjects,
        "since_seconds": alert.since_seconds,
    }


@app.get("/desk", include_in_schema=False)
@app.get("/user", include_in_schema=False)
@app.get("/admin", include_in_schema=False)
def sentineldesk_page() -> FileResponse:
    return FileResponse(SENTINELDESK_PAGE)


@app.get("/search", response_model=list[RetrievedChunk])
def search(q: str, k: int = 6) -> list[RetrievedChunk]:
    return get_agent().store.search(q, k)


@app.get("/sources", response_model=list[str])
def sources() -> list[str]:
    return get_agent().store.sources()


# --- A2UI (agent -> UI protocol, v1.0) -------------------------------------------------


class A2UIRequest(BaseModel):
    """Either a typed question (`prompt`) or a renderer action (`message` = {version, action})."""

    prompt: str | None = None
    provider: str | None = None
    k: int | None = None
    message: dict[str, Any] | None = None


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/a2ui")


@app.get("/a2ui", include_in_schema=False)
def a2ui_page() -> FileResponse:
    return FileResponse(A2UI_PAGE)


@app.post("/a2ui/agent")
def a2ui_agent(req: A2UIRequest) -> list[dict[str, Any]]:
    """Returns a list of A2UI v1.0 agent->renderer messages (createSurface, updateComponents)."""
    agent = get_agent()
    if req.prompt is not None:
        if not req.prompt.strip():
            raise HTTPException(422, "prompt is empty")
        ans = agent.ask(req.prompt.strip(), k=req.k, provider=req.provider)
        return a2ui.answer_messages(ans, PROVIDERS)

    action = (req.message or {}).get("action")
    if not isinstance(action, dict):
        raise HTTPException(422, "send either `prompt` or `message` with an A2UI `action`")
    ctx = action.get("context") or {}
    name = action.get("name")
    if name == "reask" and ctx.get("question"):
        provider = ctx.get("provider") if ctx.get("provider") in PROVIDERS else None
        return a2ui.answer_messages(agent.ask(ctx["question"], provider=provider), PROVIDERS)
    if name == "show_source" and ctx.get("chunk_id"):
        return a2ui.source_messages(agent.store.get(ctx["chunk_id"]), ctx["chunk_id"])
    return a2ui.notice_messages(f"Unknown action {name!r}.")
