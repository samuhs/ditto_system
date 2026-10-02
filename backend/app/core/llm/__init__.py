"""LLM providers package. Importing it registers all built-in providers."""
from app.core.llm import gemini, ollama  # noqa: F401  registers the built-ins
