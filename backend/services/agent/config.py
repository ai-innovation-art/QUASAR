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
                
                # 🧪 TEST SLOT - Replace model name here for quick testing
                "test": ModelConfig("deepseek-v3.2:cloud", "ollama"),                         # ← Change this to test any Ollama model
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
                
                # 🧪 TEST SLOT - Replace model name here for quick testing
                "test": ModelConfig("zai-glm-4.7", "cerebras"),                         # ← Change this to test any Cerebras model
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
                "reasoning": ModelConfig("openai/gpt-oss-120b", "groq"),  # GPT-OSS 120B with openai prefix
                
                # 🧪 TEST SLOT - Replace model name here for quick testing
                "test": ModelConfig("llama-3.1-8b-instant", "groq"),                    # ← Change this to test any Groq model
            }
        ),
        "cloudflare": ProviderConfig(
            name="cloudflare",
            enabled=True,
            models={
                "llama": ModelConfig("@cf/meta/llama-3.1-70b-instruct", "cloudflare"),
                "llama_fast": ModelConfig("@cf/meta/llama-3.1-8b-instruct", "cloudflare"),  # Fast 8B model
                "qwen": ModelConfig("@cf/qwen/qwen2.5-coder-32b-instruct", "cloudflare"),

                # 🧪 TEST SLOT - Replace model name here for quick testing
                "test": ModelConfig("@cf/openai/gpt-oss-120b", "cloudflare"), 
            }
        ),
    }
    
    # Task to model mapping (configurable)
    # Format: task_type -> [(provider, model_key), ...]
    # First is primary, rest are fallbacks
    # NOTE: All Ollama models are now cloud-based (no local download needed)
    TASK_MODELS: Dict[str, List[tuple]] = {
        # 🧪 TESTING - Uncomment this to test your test models across all tasks
        # "chat": [("ollama", "test")],
        # "code_generation": [("cerebras", "test")],
        # "bug_fixing": [("groq", "test")],
        
        # Task 1: Conversational Chat
        "chat": [
            ("cerebras", "code_gen"),         # Primary: zai-glm-4.7 (fast, good at coding)
            ("groq", "versatile"),           # Fallback 1: llama-3.3-70b-versatile
            ("ollama", "chat"),              # Fallback 2: qwen3-vl:235b-instruct-cloud
        ],
        
        # Task 2: Code Explanation (Simple)
        "code_explain_simple": [
            ("ollama", "code"),              # Primary: glm-4.7:cloud
            ("groq", "versatile"),           # Fallback 1: llama-3.3-70b-versatile
            ("cerebras", "code_gen"),        # Fallback 2: zai-glm-4.7
        ],
        
        # Task 3: Code Explanation (Complex)
        "code_explain_complex": [
            ("cerebras", "code_gen"),        # Primary: zai-glm-4.7
            ("groq", "versatile"),           # Fallback 1: llama-3.3-70b-versatile
            ("ollama", "chat"),              # Fallback 2: qwen3-vl:235b-instruct-cloud
        ],
        
        # Task 4: Code Generation (Function/Class)
        "code_generation": [
            ("cerebras", "code_gen"),         # Primary: zai-glm-4.7 (fast, good at coding)
            ("groq", "versatile"),           # Fallback 1: llama-3.3-70b-versatile
            ("ollama", "code"),              # Fallback 2: glm-4.7:cloud
        ],
        
        # Task 5: Code Generation (Multi-file/Module)
        "code_generation_multi": [
            ("cerebras", "code_gen"),         # Primary: zai-glm-4.7 (fast, good at coding)
            ("groq", "reasoning"),           # Fallback 1: gpt-oss-120b
            ("ollama", "code"),              # Fallback 2: glm-4.7:cloud
        ],
        
        # Task 6: Bug Detection & Fixing
        "bug_fixing": [
            ("cerebras", "code_gen"),         # Primary: zai-glm-4.7 (fast, good at coding)
            ("groq", "reasoning"),           # Fallback 1: gpt-oss-120b
            ("ollama", "code"),              # Fallback 2: glm-4.7:cloud
        ],
        
        # Task 7: Code Refactoring
        "refactor": [
            ("cerebras", "code_gen"),         # Primary: zai-glm-4.7 (fast, good at coding)
            ("ollama", "code"),              # Fallback 1: glm-4.7:cloud
            ("groq", "versatile"),           # Fallback 2: llama-3.3-70b-versatile
        ],
        
        # Task 8: Architecture & Design
        "architecture": [
            ("ollama", "reasoning"),         # Primary: gpt-oss:20b-cloud
            ("cerebras", "code_gen"),        # Fallback 1: zai-glm-4.7
            ("groq", "reasoning"),           # Fallback 2: gpt-oss-120b
        ],
        
        # Task 9: Test Generation
        "test_generation": [
            ("ollama", "chat"),              # Primary: qwen3-vl:235b-instruct-cloud
            ("groq", "versatile"),           # Fallback 1: llama-3.3-70b-versatile
            ("cerebras", "orchestrator"),    # Fallback 2: qwen-3-32b
        ],
        
        # Task 10: Documentation Generation
        "documentation": [
            ("ollama", "chat"),              # Primary: qwen3-vl:235b-instruct-cloud
            ("groq", "fast"),                # Fallback 1: llama-3.1-8b-instant
            ("cloudflare", "llama_fast"),    # Fallback 2: llama-3.1-8b
        ],
    }
    
    # Default settings
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_MAX_TOKENS = 4096
    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 60
    
    # Agentic Loop Configuration
    MAX_TOOL_ITERATIONS = 30          # Max tool call loops per request (increased for complex tasks)
    TOOL_TIMEOUT_SECONDS = 30         # Timeout per individual tool execution
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
