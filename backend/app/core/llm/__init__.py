"""LLM package. Importing it registers the one LLM implementation (a LangChain chat model)."""
from app.core.llm import chat_model  # noqa: F401  registers ChatModelLLM
