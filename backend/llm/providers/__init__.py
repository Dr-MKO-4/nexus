"""Implémentations spécifiques à chaque fournisseur LLM (Groq, Together AI, Mistral, Fireworks AI, vLLM, Ollama)."""

from backend.llm.providers import fireworks, groq, mistral, ollama, together, vllm

# Table de dispatch nom de provider -> module, utilisée par litellm_config.py
# pour assembler le model_list complet sans lister chaque import à la main.
PROVIDER_MODULES = {
    "groq": groq,
    "together_ai": together,
    "mistral": mistral,
    "fireworks_ai": fireworks,
    "vllm": vllm,
    "ollama": ollama,
}

__all__ = [
    "groq",
    "together",
    "mistral",
    "fireworks",
    "vllm",
    "ollama",
    "PROVIDER_MODULES",
]
