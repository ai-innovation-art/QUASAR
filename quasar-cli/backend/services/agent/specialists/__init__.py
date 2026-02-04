"""
Specialist Agents for AI Agent

Each specialist handles a specific type of task with
appropriate prompts and tool access.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod
import logging

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.tools import BaseTool

from ..models.router import ModelRouter
from ..tools import get_tools_for_task

# Setup logger
logger = logging.getLogger("specialists")


@dataclass
class SpecialistResponse:
    """Response from a specialist agent."""
    success: bool
    response: str
    model_used: str
    provider: str
    tools_invoked: List[str] = None
    iterations: int = 1
    error: Optional[str] = None


class BaseSpecialist(ABC):
    """
    Base class for all specialist agents.
    
    Each specialist handles a specific type of task.
    """
    
    def __init__(self, model_router: ModelRouter):
        self.model_router = model_router
        self.task_type: str = "chat"
        self.max_iterations: int = 3
        logger.debug(f"🎯 Specialist created: {self.__class__.__name__}")
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """Get the system prompt for this specialist."""
        pass
    
    def get_tools(self) -> List[BaseTool]:
        """Get tools available to this specialist."""
        return get_tools_for_task(self.task_type)
    
    async def execute(
        self,
        query: str,
        context: Dict[str, Any] = None
    ) -> SpecialistResponse:
        """
        Execute the specialist's task.
        
        Args:
            query: User's query
            context: Additional context (file content, selection, etc.)
        """
        model = self.model_router.get_model(self.task_type)
        
        if model is None:
            return SpecialistResponse(
                success=False,
                response="No model available",
                model_used="none",
                provider="none",
                error="All models unavailable"
            )
        
        # Build messages
        messages = [
            SystemMessage(content=self.get_system_prompt()),
            HumanMessage(content=self._build_user_message(query, context))
        ]
        
        try:
            response = await model.ainvoke(messages)
            
            return SpecialistResponse(
                success=True,
                response=response.content,
                model_used=self.task_type,
                provider="auto",
                tools_invoked=[],
                iterations=1
            )
            
        except Exception as e:
            return SpecialistResponse(
                success=False,
                response=str(e),
                model_used="unknown",
                provider="unknown",
                error=str(e)
            )
    
    def _build_user_message(self, query: str, context: Dict[str, Any] = None) -> str:
        """Build the user message with context."""
        if not context:
            return query
        
        parts = []
        
        if context.get("file_path"):
            parts.append(f"Current file: {context['file_path']}")
        
        if context.get("file_content"):
            parts.append(f"```\n{context['file_content']}\n```")
        
        if context.get("selected_code"):
            parts.append(f"Selected code:\n```\n{context['selected_code']}\n```")
        
        if context.get("error_message"):
            parts.append(f"Error:\n{context['error_message']}")
        
        if context.get("terminal_output"):
            parts.append(f"Terminal output:\n{context['terminal_output']}")
        
        parts.append(f"\nUser request: {query}")
        
        return "\n\n".join(parts)


class ChatSpecialist(BaseSpecialist):
    """
    Handles general chat and Q&A.
    
    Simple, fast responses for casual queries.
    """
    
    def __init__(self, model_router: ModelRouter):
        super().__init__(model_router)
        self.task_type = "chat"
    
    def get_system_prompt(self) -> str:
        return """You are a friendly and helpful AI assistant in a code editor.
Answer questions clearly and concisely.
For coding questions, provide examples when helpful.
Be conversational but professional."""


class CodeExplainSpecialist(BaseSpecialist):
    """
    Handles code explanation tasks.
    
    Provides clear explanations of code snippets.
    """
    
    def __init__(self, model_router: ModelRouter, complex: bool = False):
        super().__init__(model_router)
        self.task_type = "code_explain_complex" if complex else "code_explain_simple"
        self.complex = complex
    
    def get_system_prompt(self) -> str:
        if self.complex:
            return """You are an expert code analyst.
Provide comprehensive explanations of code and architecture.
Explain:
- Overall structure and design patterns used
- How components interact
- Key algorithms and their complexity
- Trade-offs and design decisions
- Potential improvements

Be thorough but organized. Use clear headings."""
        else:
            return """You are a helpful code explainer.
Explain the provided code clearly and concisely.
- What the code does
- How it works step by step
- Key concepts used
- Any potential issues

Keep explanations accessible to developers of varying levels."""


class CodeGenerationSpecialist(BaseSpecialist):
    """
    Handles code generation tasks.
    
    Generates clean, working code.
    """
    
    def __init__(self, model_router: ModelRouter, multi_file: bool = False):
        super().__init__(model_router)
        self.task_type = "code_generation_multi" if multi_file else "code_generation"
        self.multi_file = multi_file
        self.max_iterations = 3  # For validation loops
    
    def get_system_prompt(self) -> str:
        if self.multi_file:
            return """You are an expert software engineer.
Generate complete, production-ready code for the requested feature.

Guidelines:
- Create all necessary files with proper structure
- Use clear file paths (e.g., "src/models/user.py")
- Include all imports and dependencies
- Add helpful comments
- Follow best practices for the language
- Include error handling
- Make code modular and maintainable

Format code blocks with file paths:
```python
# FILE: src/models/user.py
class User:
    pass
```"""
        else:
            return """You are an expert programmer.
Generate clean, well-documented code for the user's request.

Guidelines:
- Write complete, runnable code
- Include necessary imports
- Add helpful comments
- Follow language best practices
- Handle edge cases appropriately

Provide the code in a single code block with syntax highlighting."""


class BugFixingSpecialist(BaseSpecialist):
    """
    Handles debugging and bug fixing.
    
    Analyzes errors and provides fixes.
    """
    
    def __init__(self, model_router: ModelRouter):
        super().__init__(model_router)
        self.task_type = "bug_fixing"
        self.max_iterations = 3  # Try fixes multiple times if needed
    
    def get_system_prompt(self) -> str:
        return """You are an expert debugger and bug fixer.
Analyze the provided error and code to identify and fix the issue.

Your approach:
1. Understand the error message
2. Identify the root cause
3. Explain what's wrong and why
4. Provide the corrected code
5. Explain the fix
6. Suggest how to prevent similar issues

Be systematic and thorough. Ensure your fix actually resolves the issue."""


class RefactorSpecialist(BaseSpecialist):
    """
    Handles code refactoring.
    
    Improves code quality while preserving functionality.
    """
    
    def __init__(self, model_router: ModelRouter):
        super().__init__(model_router)
        self.task_type = "refactor"
    
    def get_system_prompt(self) -> str:
        return """You are a senior software engineer focused on code quality.
Refactor the provided code to improve its quality while preserving functionality.

Consider:
- Code readability and clarity
- DRY principle (Don't Repeat Yourself)
- SOLID principles where applicable
- Proper naming conventions
- Error handling
- Performance optimizations
- Code organization

For each change, briefly explain why it's an improvement.
Provide the complete refactored code."""


class TestGenerationSpecialist(BaseSpecialist):
    """
    Handles test generation.
    
    Creates comprehensive tests for code.
    """
    
    def __init__(self, model_router: ModelRouter):
        super().__init__(model_router)
        self.task_type = "test_generation"
    
    def get_system_prompt(self) -> str:
        return """You are a testing expert.
Generate comprehensive tests for the provided code.

Guidelines:
- Use pytest (Python) or jest (JavaScript) as appropriate
- Cover normal cases, edge cases, and error cases
- Use descriptive test names
- Follow AAA pattern (Arrange, Act, Assert)
- Include setup and teardown when needed
- Add comments explaining what each test verifies

Organize tests logically and make them easy to understand."""


# Factory function to get specialist
def get_specialist(task_type: str, model_router: ModelRouter) -> BaseSpecialist:
    """
    Get the appropriate specialist for a task type.
    
    Args:
        task_type: Type of task
        model_router: Model router instance
        
    Returns:
        Specialist instance
    """
    specialists = {
        "chat": ChatSpecialist,
        "code_explain_simple": lambda r: CodeExplainSpecialist(r, complex=False),
        "code_explain_complex": lambda r: CodeExplainSpecialist(r, complex=True),
        "code_generation": lambda r: CodeGenerationSpecialist(r, multi_file=False),
        "code_generation_multi": lambda r: CodeGenerationSpecialist(r, multi_file=True),
        "bug_fixing": BugFixingSpecialist,
        "refactor": RefactorSpecialist,
        "test_generation": TestGenerationSpecialist,
    }
    
    creator = specialists.get(task_type, ChatSpecialist)
    
    if callable(creator) and not isinstance(creator, type):
        return creator(model_router)
    else:
        return creator(model_router)


# Export all specialists
__all__ = [
    "BaseSpecialist",
    "SpecialistResponse",
    "ChatSpecialist",
    "CodeExplainSpecialist",
    "CodeGenerationSpecialist",
    "BugFixingSpecialist",
    "RefactorSpecialist",
    "TestGenerationSpecialist",
    "get_specialist"
]
