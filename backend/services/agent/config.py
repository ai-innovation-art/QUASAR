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
            base_url="http://localhost:11434",  # Still uses Ollama API, but with cloud models
            models={
                # Cloud models - no local download needed, just run: ollama run model:cloud
                "chat": ModelConfig("qwen3-vl:235b-instruct-cloud", "ollama"),                              # Fast chat, tools support
                "code": ModelConfig("glm-4.7:cloud", "ollama"),                         # GLM 4.7 cloud - tools+thinking, 198K context
                "reasoning": ModelConfig("gpt-oss:20b-cloud", "ollama"),                # GPT-OSS for reasoning, tools+thinking
                "agentic": ModelConfig("devstral-small-2:24b-cloud", "ollama"),         # Best for agentic tool calling
                # "vision": ModelConfig("qwen3-vl:235b-instruct-cloud", "ollama"),        # Vision + 235B reasoning
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
    # NOTE: All Ollama models are now cloud-based (no local download needed)
    TASK_MODELS: Dict[str, List[tuple]] = {
        "chat": [
            ("ollama", "chat"),           # Primary: qwen3:8b (cloud, fast)
            ("groq", "fast"),             # Fallback: Groq 8B
        ],
        "code_explain_simple": [
            ("ollama", "code"),           # Primary: glm-4.7:cloud
            ("groq", "versatile"),        # Fallback: Groq 70B
        ],
        "code_explain_complex": [
            ("ollama", "code"),           # Primary: glm-4.7:cloud (198K context)
            ("cerebras", "orchestrator"), # Fallback: Cerebras 32B
            ("groq", "versatile"),        # Final fallback
        ],
        "code_generation": [
            ("ollama", "code"),           # Primary: glm-4.7:cloud (tools+thinking)
            ("cerebras", "code_gen"),     # Fallback: Cerebras GLM-4.7
            ("groq", "code"),             # Final fallback
        ],
        "code_generation_multi": [
            ("ollama", "agentic"),        # Primary: devstral-small-2 (built for multi-file)
            ("cerebras", "complex"),      # Fallback: Qwen3-235B
            ("ollama", "code"),           # Final: glm-4.7:cloud
        ],
        "bug_fixing": [
            ("ollama", "agentic"),        # Primary: devstral-small-2 (great for debugging)
            ("ollama", "code"),           # Fallback: glm-4.7:cloud
            ("groq", "versatile"),        # Final
        ],
        "refactor": [
            ("ollama", "code"),           # Primary: glm-4.7:cloud
            ("cerebras", "orchestrator"), # Fallback
            ("groq", "versatile"),        # Final
        ],
        "architecture": [
            ("ollama", "reasoning"),      # Primary: gpt-oss:20b (reasoning+thinking)
            ("cerebras", "complex"),      # Fallback: Qwen3-235B
        ],
        "test_generation": [
            ("ollama", "code"),           # Primary: glm-4.7:cloud
            ("groq", "versatile"),        # Fallback
        ],
        "documentation": [
            ("ollama", "chat"),           # Primary: qwen3:8b (fast, simple task)
            ("groq", "fast"),             # Fallback
        ],
    }
    
    # Default settings
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_MAX_TOKENS = 4096
    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 60
    
    # Agentic Loop Configuration
    MAX_TOOL_ITERATIONS = 10          # Max tool call loops per request
    TOOL_TIMEOUT_SECONDS = 30         # Timeout per individual tool execution
    MAX_TOOL_RESULT_LENGTH = 5000     # Truncate tool results beyond this
    ENABLE_TOOL_CONFIRMATION = False  # Require user confirmation for dangerous ops
    
    # Task types that should use tools
    TOOL_ENABLED_TASKS = [
        "code_generation",
        "code_generation_multi",
        "bug_fixing",
        "refactor",
        "test_generation",
        "architecture",
        "code_explain_simple",        # Added - needs read_file tool
        "code_explain_complex",
    ]
    
    # Tasks that are read-only (can't modify/create files) - only chat and docs
    READ_ONLY_TASKS = [
        "chat",
        "documentation",
    ]
    
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
