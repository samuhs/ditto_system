"""Endpoints for chat configs, conversation turns, and saving dialogues."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from app.core.chat.deps import ChatDeps
from app.core.chat.schemas import ChatConfigView, ChatMessage
from app.core.db.base import SessionLocal
from app.core.db.models import ChatConfig, Dialogue, DialogueMessage
from app.core.memory.manager import get_model_manager
from app.core.chat.flow_prompts import (
    FLOW_PROMPT_SPECS,
    load_flow_prompt,
    save_flow_prompt,
)
from app.core.personas import list_personas, load_persona, save_persona
from app.core.vectorstore.qdrant import QdrantStore

router = APIRouter()

# Static description of the conversation graph (structure is fixed in code).
_FLOW_NODES = [
    ("guardrail", "Guardrail", "prompt", "Verifica se a mensagem é segura e no escopo."),
    ("triage", "Triagem", "prompt", "Decide se a resposta precisa de busca (RAG) ou é direta."),
    ("rag", "RAG", "rag", "Executa a técnica de RAG escolhida na config."),
    ("memory", "Memória", "prompt", "Resume o histórico para manter a memória curta."),
    ("persona_compose", "Persona", "prompt", "Compõe a resposta final na voz da persona."),
]
_FLOW_EDGES = [
    ("guardrail", "triage", "ok"),
    ("guardrail", "persona_compose", "bloqueado"),
    ("triage", "rag", "precisa de conhecimento"),
    ("triage", "memory", "direto"),
    ("rag", "memory", ""),
    ("memory", "persona_compose", ""),
]


def get_chat_deps() -> ChatDeps:
    """Production chat dependencies."""
    return ChatDeps(store=QdrantStore(), session_factory=SessionLocal, models=get_model_manager())


class ChatConfigBody(BaseModel):
    name: str
    base: str
    chunking: str
    embedding: str
    retriever: str
    rag: str = "naive"
    llm: str
    persona: str


class ChatTurnBody(BaseModel):
    config_id: int
    messages: list[ChatMessage]


class PromptBody(BaseModel):
    text: str


@router.get("/personas")
def personas() -> dict:
    """List available persona names."""
    return {"personas": list_personas()}


@router.get("/chat/flow")
def get_flow() -> dict:
    """Return the static conversation graph plus each prompt node's current prompt."""
    nodes = []
    for node_id, label, ntype, description in _FLOW_NODES:
        node = {"id": node_id, "label": label, "type": ntype, "description": description}
        if ntype == "prompt":
            node["prompt"] = load_flow_prompt(node_id)
            node["required_placeholders"] = sorted(FLOW_PROMPT_SPECS[node_id])
        nodes.append(node)
    edges = [{"source": s, "target": t, "label": lbl} for s, t, lbl in _FLOW_EDGES]
    return {"nodes": nodes, "edges": edges}


@router.put("/chat/flow/{node}")
def update_flow_prompt(node: str, body: PromptBody) -> dict:
    """Validate placeholders and persist a node prompt."""
    if node not in FLOW_PROMPT_SPECS:
        raise HTTPException(status_code=404, detail=f"unknown flow node: {node}")
    try:
        save_flow_prompt(node, body.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"node": node, "text": body.text}


@router.get("/personas/{name}")
def get_persona(name: str) -> dict:
    """Return a persona's text."""
    try:
        text = load_persona(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown persona: {name}") from exc
    return {"name": name, "text": text}


@router.put("/personas/{name}")
def update_persona(name: str, body: PromptBody) -> dict:
    """Persist a persona's text (creates it if the name is new and valid)."""
    try:
        save_persona(name, body.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"name": name, "text": body.text}


@router.post("/chat-configs")
def create_chat_config(body: ChatConfigBody, deps: ChatDeps = Depends(get_chat_deps)) -> dict:
    """Create a saved chat configuration."""
    session = deps.session_factory()
    try:
        cfg = ChatConfig(**body.model_dump())
        session.add(cfg)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=f"chat config name already exists: {body.name}") from exc
        session.refresh(cfg)
        return {"id": cfg.id, "name": cfg.name}
    finally:
        session.close()


@router.get("/chat-configs")
def list_chat_configs(deps: ChatDeps = Depends(get_chat_deps)) -> list[dict]:
    """List saved chat configurations, most recent first."""
    session = deps.session_factory()
    try:
        rows = session.query(ChatConfig).order_by(ChatConfig.id.desc()).all()
        return [
            {
                "id": c.id, "name": c.name, "base": c.base, "chunking": c.chunking,
                "embedding": c.embedding, "retriever": c.retriever, "rag": c.rag, "llm": c.llm, "persona": c.persona,
            }
            for c in rows
        ]
    finally:
        session.close()


@router.delete("/chat-configs/{config_id}")
def delete_chat_config(config_id: int, deps: ChatDeps = Depends(get_chat_deps)) -> dict:
    """Delete a chat configuration."""
    session = deps.session_factory()
    try:
        cfg = session.get(ChatConfig, config_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail="chat config not found")
        session.delete(cfg)
        session.commit()
        return {"id": config_id, "deleted": True}
    finally:
        session.close()


@router.post("/chat")
def chat(body: ChatTurnBody, deps: ChatDeps = Depends(get_chat_deps)) -> dict:
    """Run one conversational turn (stateless: history is supplied by the caller)."""
    session = deps.session_factory()
    try:
        cfg = session.get(ChatConfig, body.config_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail="chat config not found")
        view = ChatConfigView(
            base=cfg.base, chunking=cfg.chunking, embedding=cfg.embedding,
            retriever=cfg.retriever, rag=cfg.rag, llm=cfg.llm, persona=cfg.persona,
        )
    finally:
        session.close()
    try:
        result = deps.agent_runner(view, body.messages, deps)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"reply": result.answer, "contexts": result.contexts, "difficulty": result.difficulty}


@router.post("/dialogues")
def save_dialogue(body: ChatTurnBody, deps: ChatDeps = Depends(get_chat_deps)) -> dict:
    """Persist a dialogue and its messages for later evaluation."""
    session = deps.session_factory()
    try:
        cfg = session.get(ChatConfig, body.config_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail="chat config not found")
        dialogue = Dialogue(config_snapshot={
            "name": cfg.name, "base": cfg.base, "chunking": cfg.chunking,
            "embedding": cfg.embedding, "retriever": cfg.retriever, "rag": cfg.rag, "llm": cfg.llm, "persona": cfg.persona,
        })
        dialogue.messages = [
            DialogueMessage(role=m.role, content=m.content, position=i)
            for i, m in enumerate(body.messages)
        ]
        session.add(dialogue)
        session.commit()
        session.refresh(dialogue)
        return {"id": dialogue.id}
    finally:
        session.close()


_RATED_VALUES = {"all", "rated", "unrated"}
_SORT_VALUES = {"recent", "oldest", "rating_asc", "rating_desc"}


def _dialogue_list_item(d: Dialogue) -> dict:
    """Build a list-row summary for a dialogue."""
    snapshot = d.config_snapshot or {}
    user_msgs = sorted(
        (m for m in d.messages if m.role == "user"), key=lambda m: m.position
    )
    preview = user_msgs[0].content[:80] if user_msgs else None
    return {
        "id": d.id,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "rating": d.rating,
        "name": snapshot.get("name"),
        "persona": snapshot.get("persona"),
        "message_count": len(d.messages),
        "preview": preview,
    }


@router.get("/dialogues")
def list_dialogues(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    date: str | None = Query(None),
    rated: str = Query("all"),
    sort: str = Query("recent"),
    deps: ChatDeps = Depends(get_chat_deps),
) -> dict:
    """List saved dialogues, paginated, with optional date/rated filters and sorting."""
    if rated not in _RATED_VALUES:
        raise HTTPException(status_code=422, detail=f"invalid rated filter: {rated}")
    if sort not in _SORT_VALUES:
        raise HTTPException(status_code=422, detail=f"invalid sort: {sort}")
    day_start = None
    if date is not None:
        try:
            day_start = datetime.strptime(date, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"invalid date: {date}") from exc

    session = deps.session_factory()
    try:
        query = session.query(Dialogue)
        if day_start is not None:
            query = query.filter(
                Dialogue.created_at >= day_start,
                Dialogue.created_at < day_start + timedelta(days=1),
            )
        if rated == "rated":
            query = query.filter(Dialogue.rating.is_not(None))
        elif rated == "unrated":
            query = query.filter(Dialogue.rating.is_(None))

        total = query.count()

        if sort == "recent":
            query = query.order_by(Dialogue.created_at.desc())
        elif sort == "oldest":
            query = query.order_by(Dialogue.created_at.asc())
        elif sort == "rating_asc":
            query = query.order_by(
                Dialogue.rating.is_(None), Dialogue.rating.asc(), Dialogue.created_at.desc()
            )
        else:  # rating_desc
            query = query.order_by(
                Dialogue.rating.is_(None), Dialogue.rating.desc(), Dialogue.created_at.desc()
            )

        rows = query.offset((page - 1) * page_size).limit(page_size).all()
        return {
            "items": [_dialogue_list_item(d) for d in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    finally:
        session.close()


@router.get("/dialogues/{dialogue_id}")
def get_dialogue(dialogue_id: int, deps: ChatDeps = Depends(get_chat_deps)) -> dict:
    """Return a saved dialogue with its messages in order and config snapshot."""
    session = deps.session_factory()
    try:
        d = session.get(Dialogue, dialogue_id)
        if d is None:
            raise HTTPException(status_code=404, detail="dialogue not found")
        messages = [
            {"role": m.role, "content": m.content}
            for m in sorted(d.messages, key=lambda m: m.position)
        ]
        return {
            "id": d.id,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "rating": d.rating,
            "config_snapshot": d.config_snapshot or {},
            "messages": messages,
        }
    finally:
        session.close()


class RatingBody(BaseModel):
    rating: int = Field(ge=0, le=10)


@router.put("/dialogues/{dialogue_id}/rating")
def set_dialogue_rating(
    dialogue_id: int, body: RatingBody, deps: ChatDeps = Depends(get_chat_deps)
) -> dict:
    """Set or update the human rating (0-10) for a dialogue."""
    session = deps.session_factory()
    try:
        d = session.get(Dialogue, dialogue_id)
        if d is None:
            raise HTTPException(status_code=404, detail="dialogue not found")
        d.rating = body.rating
        d.rated_at = datetime.utcnow()
        session.commit()
        return {"id": dialogue_id, "rating": body.rating}
    finally:
        session.close()
