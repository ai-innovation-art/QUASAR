"""
AI Agent Configuration

Centralized configuration for:
- Model names per provider
- Task-to-model mappings
- Default settings

Easy to modify for new models.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class ModelConfig:
    """Configuration for a single model."""
    name: str
    provider: str
    temperature: float = 0.7
    max_tokens: int = 4096
    

@dataclass
class ProviderConfig:
    """Configuration for a provider."""
    name: str
    enabled: bool = True
    base_url: Optional[str] = None
    models: Dict[str, ModelConfig] = field(default_factory=dict)


class AgentConfig:
    """
    Centralized agent configuration.
    
    Configurable and scalable - easy to add new models/providers.
    """
    
    # Provider configurations
    PROVIDERS: Dict[str, ProviderConfig] = {
        "ollama": ProviderConfig(
            name="ollama",
            enabled=True,
            base_url="http://localhost:11434",
            models={
                "chat": ModelConfig("qwen2.5-coder:7b", "ollama"),
                "code": ModelConfig("qwen2.5-coder:32b", "ollama"),
                "reasoning": ModelConfig("deepseek-r1:7b", "ollama"),
            }
        ),
        "cerebras": ProviderConfig(
            name="cerebras",
            enabled=True,
            base_url="https://api.cerebras.ai/v1",
            models={
                "orchestrator": ModelConfig("qwen-3-32b", "cerebras"),
                "complex": ModelConfig("qwen-3-235b-a22b-instruct-2507", "cerebras"),
                "code_gen": ModelConfig("zai-glm-4.7", "cerebras"),
            }
        ),
        "groq": ProviderConfig(
            name="groq",
            enabled=True,
            base_url="https://api.groq.com/openai/v1",
            models={
                "fast": ModelConfig("llama-3.1-8b-instant", "groq"),
                "versatile": ModelConfig("llama-3.3-70b-versatile", "groq"),
                "code": ModelConfig("llama-3.1-70b-versatile", "groq"),
            }
        ),
        "cloudflare": ProviderConfig(
            name="cloudflare",
            enabled=True,
            models={
                "llama": ModelConfig("@cf/meta/llama-3.1-70b-instruct", "cloudflare"),
                "qwen": ModelConfig("@cf/qwen/qwen2.5-coder-32b-instruct", "cloudflare"),
            }
        ),
    }
    
    # Task to model mapping (configurable)
    # Format: task_type -> [(provider, model_key), ...]
    # First is primary, rest are fallbacks
    TASK_MODELS: Dict[str, List[tuple]] = {
        "chat": [
            ("ollama", "chat"),           # Primary: Local 7B
            ("groq", "fast"),             # Fallback 1: Groq 8B
        ],
        "code_explain_simple": [
            ("ollama", "code"),           # Primary: Local 32B
            ("groq", "versatile"),        # Fallback: Groq 70B
        ],
        "code_explain_complex": [
            ("cerebras", "orchestrator"), # Primary: Cerebras 32B
            ("groq", "versatile"),        # Fallback
            ("ollama", "code"),           # Final fallback
        ],
        "code_generation": [
            ("ollama", "reasoning"),      # Primary: DeepSeek R1 local
            ("cerebras", "code_gen"),     # Fallback: GLM-4.7
            ("groq", "code"),             # Final fallback
        ],
        "code_generation_multi": [
            ("cerebras", "complex"),      # Primary: Qwen3-235B
            ("cerebras", "code_gen"),     # Fallback
            ("ollama", "reasoning"),      # Final: Local
        ],
        "bug_fixing": [
            ("ollama", "code"),           # Primary: Local 32B
            ("cerebras", "orchestrator"), # Fallback
            ("groq", "versatile"),        # Final
        ],
        "refactor": [
            ("cerebras", "orchestrator"), # Primary
            ("groq", "versatile"),        # Fallback
            ("ollama", "reasoning"),      # Final
        ],
        "architecture": [
            ("ollama", "reasoning"),      # Primary: DeepSeek R1
            ("cerebras", "code_gen"),     # Fallback
        ],
        "test_generation": [
            ("ollama", "code"),           # Primary: Local 32B
            ("groq", "versatile"),        # Fallback
        ],
        "documentation": [
            ("ollama", "chat"),           # Primary: Local 7B (simple task)
            ("groq", "fast"),             # Fallback
        ],
    }
    
    # Default settings
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_MAX_TOKENS = 4096
    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 60
    
    @classmethod
    def get_models_for_task(cls, task_type: str) -> List[tuple]:
        """Get list of (provider, model_key) for a task type."""
        return cls.TASK_MODELS.get(task_type, [("ollama", "chat")])
    
    @classmethod
    def get_provider(cls, provider_name: str) -> Optional[ProviderConfig]:
        """Get provider configuration."""
        return cls.PROVIDERS.get(provider_name)
    
    @classmethod
    def is_provider_enabled(cls, provider_name: str) -> bool:
        """Check if provider is enabled."""
        provider = cls.PROVIDERS.get(provider_name)
        return provider.enabled if provider else False
