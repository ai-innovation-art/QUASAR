"""
AI Agent Orchestrator

The main coordinator that:
1. Classifies user queries into task types
2. Routes to appropriate specialist
3. Manages agentic loops
4. Handles fallbacks

Uses LLM for intelligent task classification.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import json

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from .models.router import ModelRouter
from .config import AgentConfig
from .tools import get_tools_for_task, set_workspace
from .logger import (
    agent_logger,
    log_model_call,
    log_model_response,
    log_classification,
    log_error
)


class TaskType(str, Enum):
    """Types of tasks the agent can handle."""
    CHAT = "chat"
    CODE_EXPLAIN_SIMPLE = "code_explain_simple"
    CODE_EXPLAIN_COMPLEX = "code_explain_complex"
    CODE_GENERATION = "code_generation"
    CODE_GENERATION_MULTI = "code_generation_multi"
    BUG_FIXING = "bug_fixing"
    REFACTOR = "refactor"
    ARCHITECTURE = "architecture"
    TEST_GENERATION = "test_generation"
    DOCUMENTATION = "documentation"


@dataclass
class TaskClassification:
    """Result of task classification."""
    task_type: TaskType
    confidence: float
    requires_file_context: bool
    requires_terminal: bool
    estimated_complexity: str  # low, medium, high
    reasoning: str


@dataclass
class AgentResponse:
    """Response from the agent."""
    success: bool
    response: str
    task_type: str
    model_used: str
    provider: str
    tools_used: List[str] = None
    error: Optional[str] = None


CLASSIFICATION_PROMPT = """You are a task classifier for an AI code editor.
Classify the user's query into one of these task types:

1. chat - Simple Q&A, general questions, greetings (e.g., "What is Python?", "Hello")
2. code_explain_simple - Explain a small piece of code (<100 lines)
3. code_explain_complex - Explain large code, architecture, design patterns
4. code_generation - Generate a single function, class, or small module
5. code_generation_multi - Generate multiple files/complete features
6. bug_fixing - Debug errors, fix bugs, resolve issues (KEYWORDS: error, bug, fix, debug, exception, NameError, TypeError, etc.)
7. refactor - Improve code quality, apply best practices
8. architecture - System design, architecture decisions
9. test_generation - Write tests for code
10. documentation - Write docstrings, README, docs

IMPORTANT RULES:
- PRIORITIZE keywords in the user's query over context
- If query contains "error", "bug", "fix", "debug", ANY exception name (NameError, TypeError, etc.) → classify as bug_fixing
- If query contains "create", "generate", "write", "build" → classify as code_generation
- If query contains "explain", "what does", "how does" → classify as code_explain_*
- ONLY use provided context, do NOT invent or hallucinate file names or code
- Be concise in reasoning

User query: {query}

Context (use only if relevant):
- Current file: {current_file}
- Has selection: {has_selection}
- Has error in terminal: {has_error}

Respond with JSON only:
{{
    "task_type": "<task type>",
    "confidence": <0.0-1.0>,
    "requires_file_context": <true/false>,
    "requires_terminal": <true/false>,
    "estimated_complexity": "<low/medium/high>",
    "reasoning": "<brief explanation based ONLY on query keywords>"
}}
"""


class Orchestrator:
    """
    Main orchestrator for the AI agent.
    
    Classifies tasks and routes to appropriate handlers.
    Uses ContextManager for hierarchical context management.
    """
    
    def __init__(self, workspace_path: str = None):
        from .context import ContextManager
        
        self.model_router = ModelRouter()
        self.context_manager = ContextManager()
        self.workspace = workspace_path
        
        if workspace_path:
            set_workspace(workspace_path)
            self.context_manager.set_workspace(workspace_path)
        
        agent_logger.info("🚀 Orchestrator initialized with ContextManager")
    
    def set_workspace(self, path: str):
        """Set the workspace path."""
        self.workspace = path
        set_workspace(path)
        self.context_manager.set_workspace(path)
        agent_logger.info(f"📁 Workspace set to: {path}")
    
    async def classify_task(
        self,
        query: str,
        current_file: str = None,
        has_selection: bool = False,
        has_error: bool = False
    ) -> TaskClassification:
        """
        Classify the user's query into a task type.
        
        Uses LLM for intelligent classification.
        """
        agent_logger.info(f"🔍 Classifying query: {query[:100]}...")
        
        # Build classification prompt
        prompt = CLASSIFICATION_PROMPT.format(
            query=query,
            current_file=current_file or "None",
            has_selection=has_selection,
            has_error=has_error
        )
        
        # Use Cerebras qwen-3-32b for classification (per agent_orchestration.md)
        agent_logger.debug("Attempting to get Cerebras (qwen-3-32b) for classification...")
        model = self.model_router.get_model_for_provider("cerebras", "qwen-3-32b")
        provider = "cerebras"
        model_name = "qwen-3-32b"
        
        if model is None:
            agent_logger.warning("Cerebras not available, trying Groq gpt-oss-120b...")
            # Fallback to Groq gpt-oss-120b
            model = self.model_router.get_model_for_provider("groq", "openai/gpt-oss-120b")
            provider = "groq"
            model_name = "gpt-oss-120b"
        
        if model is None:
            agent_logger.warning("No cloud models available, using keyword fallback")
            # Default classification if no model available
            return self._fallback_classification(query)
        
        # Log which model we're using
        log_model_call(provider, model_name, "classification")
        
        try:
            messages = [HumanMessage(content=prompt)]
            response = await model.ainvoke(messages)
            
            # Log raw response
            content = response.content
            agent_logger.debug(f"Raw LLM response ({len(content)} chars):")
            agent_logger.debug(content[:500] + ("..." if len(content) > 500 else ""))
            
            log_model_response(provider, model_name, len(content), success=True)
            
            # Parse JSON response
            # Strip <think>...</think> tags (Qwen-3 includes reasoning before JSON)
            if "<think>" in content:
                agent_logger.debug("Stripping <think> tags from response")
                content = content.split("</think>")[-1].strip()
            
            # Extract JSON from response (handle markdown code blocks)
            if "```json" in content:
                agent_logger.debug("Extracting JSON from ```json block")
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                agent_logger.debug("Extracting JSON from ``` block")
                content = content.split("```")[1].split("```")[0]
            
            content = content.strip()
            agent_logger.debug(f"Cleaned content: {content[:200]}...")
            
            # Try to parse JSON
            try:
                data = json.loads(content)
                agent_logger.debug(f"✅ Successfully parsed JSON: {data}")
            except json.JSONDecodeError as je:
                agent_logger.error(f"❌ JSON parse error: {je}")
                agent_logger.error(f"Problematic content: {content[:500]}")
                
                # Try to find JSON object in the content
                import re
                agent_logger.debug("Attempting regex JSON extraction...")
                json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
                if json_match:
                    extracted = json_match.group(0)
                    agent_logger.debug(f"Regex extracted: {extracted}")
                    data = json.loads(extracted)
                else:
                    agent_logger.error("Regex extraction failed, using fallback")
                    raise je
            
            classification = TaskClassification(
                task_type=TaskType(data.get("task_type", "chat")),
                confidence=float(data.get("confidence", 0.8)),
                requires_file_context=data.get("requires_file_context", False),
                requires_terminal=data.get("requires_terminal", False),
                estimated_complexity=data.get("estimated_complexity", "low"),
                reasoning=data.get("reasoning", "")
            )
            
            log_classification(
                classification.task_type.value,
                classification.confidence,
                classification.reasoning
            )
            
            return classification
            
        except Exception as e:
            log_error("Classification", e, f"Query: {query[:100]}")
            agent_logger.warning("Falling back to keyword-based classification")
            return self._fallback_classification(query)
    
    def _fallback_classification(self, query: str) -> TaskClassification:
        """
        Simple keyword-based fallback classification.
        """
        query_lower = query.lower()
        
        # Bug fixing keywords
        if any(kw in query_lower for kw in ["error", "bug", "fix", "debug", "traceback", "exception"]):
            return TaskClassification(
                task_type=TaskType.BUG_FIXING,
                confidence=0.7,
                requires_file_context=True,
                requires_terminal=True,
                estimated_complexity="medium",
                reasoning="Detected error/bug-related keywords"
            )
        
        # Code generation keywords
        if any(kw in query_lower for kw in ["create", "generate", "write", "make", "build"]):
            # Multi-file indicators
            if any(kw in query_lower for kw in ["complete", "full", "entire", "system", "application"]):
                return TaskClassification(
                    task_type=TaskType.CODE_GENERATION_MULTI,
                    confidence=0.7,
                    requires_file_context=True,
                    requires_terminal=True,
                    estimated_complexity="high",
                    reasoning="Detected multi-file generation keywords"
                )
            return TaskClassification(
                task_type=TaskType.CODE_GENERATION,
                confidence=0.7,
                requires_file_context=True,
                requires_terminal=False,
                estimated_complexity="medium",
                reasoning="Detected code generation keywords"
            )
        
        # Explanation keywords
        if any(kw in query_lower for kw in ["explain", "what does", "how does", "understand"]):
            return TaskClassification(
                task_type=TaskType.CODE_EXPLAIN_SIMPLE,
                confidence=0.7,
                requires_file_context=True,
                requires_terminal=False,
                estimated_complexity="low",
                reasoning="Detected explanation keywords"
            )
        
        # Refactor keywords
        if any(kw in query_lower for kw in ["refactor", "improve", "optimize", "clean"]):
            return TaskClassification(
                task_type=TaskType.REFACTOR,
                confidence=0.7,
                requires_file_context=True,
                requires_terminal=False,
                estimated_complexity="medium",
                reasoning="Detected refactoring keywords"
            )
        
        # Test generation
        if any(kw in query_lower for kw in ["test", "unittest", "pytest"]):
            return TaskClassification(
                task_type=TaskType.TEST_GENERATION,
                confidence=0.7,
                requires_file_context=True,
                requires_terminal=False,
                estimated_complexity="medium",
                reasoning="Detected testing keywords"
            )
        
        # Default to chat
        return TaskClassification(
            task_type=TaskType.CHAT,
            confidence=0.5,
            requires_file_context=False,
            requires_terminal=False,
            estimated_complexity="low",
            reasoning="No specific keywords detected, defaulting to chat"
        )
    
    async def process(
        self,
        query: str,
        current_file: str = None,
        file_content: str = None,
        selected_code: str = None,
        terminal_output: str = None,
        error_message: str = None
    ) -> AgentResponse:
        """
        Process a user query through the full agent pipeline.
        
        1. Classify the task
        2. Update context manager
        3. Get appropriate model
        4. Build context with token budgeting
        5. Execute with tools
        6. Record conversation
        7. Return response
        """
        # Update task context in context manager
        self.context_manager.set_task_context(
            current_file=current_file,
            file_content=file_content,
            selected_code=selected_code,
            error_message=error_message,
            terminal_output=terminal_output
        )
        
        # Classify the task
        has_error = bool(error_message or (terminal_output and "error" in terminal_output.lower()))
        
        classification = await self.classify_task(
            query=query,
            current_file=current_file,
            has_selection=bool(selected_code),
            has_error=has_error
        )
        
        # Get context for this task type (with token budgeting)
        context_data = self.context_manager.get_context_for_task(classification.task_type.value)
        agent_logger.debug(f"Context budget: {context_data['token_budget']} tokens")
        
        # Build context messages using context manager data
        system_prompt = self._build_system_prompt(classification.task_type)
        
        context_parts = []
        
        # Add permanent context
        if context_data["permanent"]:
            context_parts.append(context_data["permanent"])
        
        # Add task context
        if context_data["task"]:
            context_parts.append(context_data["task"])
        
        # Add conversation summary
        if context_data["summary"]:
            context_parts.append(context_data["summary"])
        
        # Add session memory
        if context_data["session"]:
            context_parts.append(context_data["session"])
        
        context = "\n\n".join(context_parts) if context_parts else ""
        
        user_message = query
        if context:
            user_message = f"{context}\n\nUser request: {query}"
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ]
        
        # Record user message in context
        self.context_manager.add_message("user", query, classification.task_type.value)
        
        # Execute with fallback support
        agent_logger.info(f"🔄 Invoking model with fallback for task: {classification.task_type.value}")
        
        try:
            # Use invoke_with_fallback for automatic fallback when model fails
            response, provider, model_name = await self.model_router.invoke_with_fallback(
                task_type=classification.task_type.value,
                messages=messages
            )
            
            if response is None:
                agent_logger.error("❌ All models failed, including fallbacks")
                return AgentResponse(
                    success=False,
                    response="All models failed. Please check if Ollama is running with: ollama serve",
                    task_type=classification.task_type.value,
                    model_used="none",
                    provider="none",
                    error="All models unavailable"
                )
            
            agent_logger.info(f"✅ Model response received: {provider}/{model_name}")
            
            # Record assistant response in context
            self.context_manager.add_message("assistant", response.content[:500], classification.task_type.value)
            
            return AgentResponse(
                success=True,
                response=response.content,
                task_type=classification.task_type.value,
                model_used=model_name,
                provider=provider,
                tools_used=[]
            )
            
        except Exception as e:
            agent_logger.error(f"❌ invoke_with_fallback failed: {e}")
            self.context_manager.record_error(str(e))
            return AgentResponse(
                success=False,
                response=f"Error: {str(e)}",
                task_type=classification.task_type.value,
                model_used="unknown",
                provider="unknown",
                error=str(e)
            )
    
    def _build_system_prompt(self, task_type: TaskType) -> str:
        """Build system prompt based on task type."""
        
        base_prompt = """You are an expert AI coding assistant in a code editor.
You help users write, understand, debug, and improve code.
Be concise, accurate, and helpful."""
        
        task_prompts = {
            TaskType.CHAT: """
Answer the user's question clearly and concisely.
If it's about code, provide examples when helpful.""",
            
            TaskType.CODE_EXPLAIN_SIMPLE: """
Explain the provided code clearly.
Break down what each part does.
Highlight important patterns or potential issues.""",
            
            TaskType.CODE_EXPLAIN_COMPLEX: """
Provide a comprehensive explanation of the code/architecture.
Explain the overall design, how components interact.
Discuss trade-offs and design decisions.""",
            
            TaskType.CODE_GENERATION: """
Generate clean, well-documented code.
Follow best practices for the language.
Include helpful comments.
Make sure the code is complete and runnable.""",
            
            TaskType.CODE_GENERATION_MULTI: """
Generate complete, production-ready code.
Create all necessary files with proper structure.
Ensure all imports and dependencies are correct.
Include proper error handling.""",
            
            TaskType.BUG_FIXING: """
Analyze the error and identify the root cause.
Explain what's wrong and why.
Provide a corrected version of the code.
Suggest how to prevent similar issues.""",
            
            TaskType.REFACTOR: """
Improve the code while preserving functionality.
Apply best practices and design patterns.
Explain each improvement you make.
Ensure the refactored code is cleaner and more maintainable.""",
            
            TaskType.ARCHITECTURE: """
Provide thoughtful architectural advice.
Consider scalability, maintainability, and best practices.
Explain trade-offs of different approaches.
Give concrete recommendations.""",
            
            TaskType.TEST_GENERATION: """
Generate comprehensive tests for the code.
Cover edge cases and error conditions.
Use the appropriate testing framework.
Make tests clear and well-organized.""",
            
            TaskType.DOCUMENTATION: """
Write clear, helpful documentation.
Follow standard conventions for the format.
Be thorough but concise.
Include examples where helpful."""
        }
        
        return base_prompt + task_prompts.get(task_type, "")
