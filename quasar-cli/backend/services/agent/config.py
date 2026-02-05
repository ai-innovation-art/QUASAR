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
                "glm-4.7:cloud": ModelConfig("glm-4.7:cloud", "ollama"),
                "gpt-oss:120b-cloud": ModelConfig("gpt-oss:120b-cloud", "ollama"),
                "qwen3-coder:480b-cloud": ModelConfig("qwen3-coder:480b-cloud", "ollama"),
                "deepseek-v3.1:671b-cloud": ModelConfig("deepseek-v3.1:671b-cloud", "ollama"),
                "deepseek-v3.2:cloud": ModelConfig("deepseek-v3.2:cloud", "ollama"),
            }
        ),
        "cerebras": ProviderConfig(
            name="cerebras",
            enabled=True,
            base_url="https://api.cerebras.ai/v1",
            models={
                "zai-glm-4.7": ModelConfig("zai-glm-4.7", "cerebras"),
                "qwen-3-235b-a22b-instruct-2507": ModelConfig("qwen-3-235b-a22b-instruct-2507", "cerebras"),
            }
        ),
        "groq": ProviderConfig(
            name="groq",
            enabled=True,
            base_url="https://api.groq.com/openai/v1",
            models={
                "openai/gpt-oss-120b": ModelConfig("openai/gpt-oss-120b", "groq"),
                "openai/gpt-oss-20b": ModelConfig("openai/gpt-oss-20b", "groq"),
                "llama-3.3-70b-versatile": ModelConfig("llama-3.3-70b-versatile", "groq"),
                "meta-llama/llama-4-scout-17b-16e-instruct": ModelConfig("meta-llama/llama-4-scout-17b-16e-instruct", "groq"),
            }
        ),
        "cloudflare": ProviderConfig(
            name="cloudflare",
            enabled=False,  # Skipped 
            models={
                # "@cf/meta/llama-3.1-70b-instruct": ModelConfig("@cf/meta/llama-3.1-70b-instruct", "cloudflare"),
                # "@cf/meta/llama-3.1-8b-instruct": ModelConfig("@cf/meta/llama-3.1-8b-instruct", "cloudflare"),
                # "@cf/qwen/qwen2.5-coder-32b-instruct": ModelConfig("@cf/qwen/qwen2.5-coder-32b-instruct", "cloudflare"),
            }
        ),
    }
    
    # Task to model mapping (configurable)
    # Format: task_type -> [(provider, model_key), ...]
    # First is primary, rest are fallbacks
    TASK_MODELS: Dict[str, List[tuple]] = {
        # Task 1: Conversational Chat
        "chat": [
            ("cerebras", "zai-glm-4.7"),
            ("ollama", "glm-4.7:cloud"),
            ("groq", "openai/gpt-oss-120b"),
        ],
        
        # Task 2: Code Explanation (Simple)
        "code_explain_simple": [
            ("ollama", "glm-4.7:cloud"),
            ("groq", "openai/gpt-oss-120b"),
            ("cerebras", "zai-glm-4.7"),
        ],
        
        # Task 3: Code Explanation (Complex)
        "code_explain_complex": [
            ("groq", "openai/gpt-oss-120b"),
            ("cerebras", "qwen-3-235b-a22b-instruct-2507"),
            ("ollama", "qwen3-coder:480b-cloud"),
        ],
        
        # Task 4: Code Generation (Function/Class)
        "code_generation": [
            ("cerebras", "zai-glm-4.7"),
            ("ollama", "glm-4.7:cloud"),
            ("groq", "openai/gpt-oss-120b"),
        ],
        
        # Task 5: Code Generation (Multi-file/Module)
        "code_generation_multi": [
            ("cerebras", "zai-glm-4.7"),
            ("ollama", "qwen3-coder:480b-cloud"),
            ("groq", "openai/gpt-oss-120b"),
        ],
        
        # Task 6: Bug Detection & Fixing
        "bug_fixing": [
            ("ollama", "deepseek-v3.1:671b-cloud"),
            ("cerebras", "qwen-3-235b-a22b-instruct-2507"),
            ("groq", "openai/gpt-oss-120b"),
        ],
        
        # Task 7: Code Refactoring
        "refactor": [
            ("cerebras", "zai-glm-4.7"),
            ("ollama", "glm-4.7:cloud"),
            ("groq", "llama-3.3-70b-versatile"),
        ],
        
        # Task 8: Architecture & Design
        "architecture": [
            ("ollama", "deepseek-v3.1:671b-cloud"),
            ("cerebras", "qwen-3-235b-a22b-instruct-2507"),
            ("groq", "openai/gpt-oss-120b"),
        ],
        
        # Task 9: Test Generation
        "test_generation": [
            ("ollama", "glm-4.7:cloud"),
            ("cerebras", "zai-glm-4.7"),
            ("groq", "llama-3.3-70b-versatile"),
        ],
        
        # Task 10: Documentation Generation
        "documentation": [
            ("groq", "openai/gpt-oss-20b"),
            ("ollama", "deepseek-v3.2:cloud"),
            ("cerebras", "zai-glm-4.7"),
        ],
        
        # Task 11: Web & Documentation Research
        "research": [
            ("cerebras", "zai-glm-4.7"),
            ("ollama", "glm-4.7:cloud"),
            ("groq", "llama-3.3-70b-versatile"),
        ],
    }
    
    # Default settings
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_MAX_TOKENS = 4096
    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 60
    
    # Agentic Loop Configuration
    MAX_TOOL_ITERATIONS = 30          # Max tool call loops per request (increased for complex tasks)
    TOOL_TIMEOUT_SECONDS = 180         # Timeout per individual tool execution
    PIP_INSTALL_TIMEOUT = 180         # Extended timeout for pip install commands (2 minutes)
    ENABLE_TOOL_CONFIRMATION = False  # Require user confirmation for dangerous ops
    
    # Task types that should use tools
    TOOL_ENABLED_TASKS = [
        "code_generation",
        "code_generation_multi",
        "bug_fixing",
        "refactor",
        "test_generation",
        "architecture",
        "code_explain_simple",       
        "code_explain_complex",
        "chat",
        "documentation",
        "research",
    ]
    
    # Tasks that are read-only (can't modify/create files) - only chat
    READ_ONLY_TASKS = [
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
