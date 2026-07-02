"""Endpoints for chat configs, conversation turns, and saving dialogues."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.core.chat.deps import ChatDeps
from app.core.chat.schemas import ChatMessage
from app.core.db.base import SessionLocal
from app.core.db.models import ChatConfig, Dialogue, DialogueMessage
from app.core.llm.base import build_llm
from app.core.personas import list_personas, load_persona
from app.core.vectorstore.qdrant import QdrantStore, collection_name

router = APIRouter()


def get_chat_deps() -> ChatDeps:
    """Production chat dependencies."""
    return ChatDeps(store=QdrantStore(), session_factory=SessionLocal)


class ChatConfigBody(BaseModel):
    name: str
    base: str
    chunking: str
    embedding: str
    retriever: str
    llm: str = "gemini"
    persona: str


class ChatTurnBody(BaseModel):
    config_id: int
    messages: list[ChatMessage]


@router.get("/personas")
def personas() -> dict:
    """List available persona names."""
    return {"personas": list_personas()}


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
                "embedding": c.embedding, "retriever": c.retriever, "llm": c.llm, "persona": c.persona,
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


def _build_chat_retriever(deps: ChatDeps, cfg: ChatConfig):
    """Build the retriever tool backend from a chat config."""
    embedder = deps.embedder_factory(cfg.embedding)
    col = collection_name(cfg.base, cfg.chunking, cfg.embedding)
    kwargs = {"store": deps.store, "collection": col, "embedder": embedder}
    if cfg.retriever == "multi_query":
        # multi_query uses the Fatia A LLM interface (.generate), not the chat model.
        kwargs["llm"] = build_llm(cfg.llm)
    return deps.retriever_factory(cfg.retriever, **kwargs)


@router.post("/chat")
def chat(body: ChatTurnBody, deps: ChatDeps = Depends(get_chat_deps)) -> dict:
    """Run one conversational turn (stateless: history is supplied by the caller)."""
    session = deps.session_factory()
    try:
        cfg = session.get(ChatConfig, body.config_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail="chat config not found")
        cfg_persona, cfg_llm = cfg.persona, cfg.llm
        retriever = _build_chat_retriever(deps, cfg)
    finally:
        session.close()
    try:
        persona_text = load_persona(cfg_persona)
        chat_model = deps.chat_model_factory(cfg_llm)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = deps.agent_runner(persona_text, retriever, chat_model, body.messages)
    return {"reply": result.answer, "contexts": result.contexts}


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
            "embedding": cfg.embedding, "retriever": cfg.retriever, "llm": cfg.llm, "persona": cfg.persona,
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
