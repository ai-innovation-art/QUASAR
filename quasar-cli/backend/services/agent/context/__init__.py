"""
Context Management Package for AI Agent

Exports:
- ContextManager: Main context manager
- ConversationSummarizer: Summarizes conversation history
- TOKEN_BUDGETS: Token limits per task type
"""

from .manager import (
    ContextManager,
    PermanentContext,
    TaskContext,
    SessionMemory,
    ConversationMessage,
    TOKEN_BUDGETS
)

from .summarizer import (
    ConversationSummarizer,
    get_summarizer
)

__all__ = [
    "ContextManager",
    "PermanentContext",
    "TaskContext",
    "SessionMemory",
    "ConversationMessage",
    "TOKEN_BUDGETS",
    "ConversationSummarizer",
    "get_summarizer"
]
