"""
AI Agent Orchestrator

The main coordinator that:
1. Classifies user queries into task types
2. Routes to appropriate specialist
3. Manages agentic loops
4. Handles fallbacks

Uses LLM for intelligent task classification.
"""

from typing import Dict, Any, Optional, List, AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
import json

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from .models.router import ModelRouter
from .config import AgentConfig
from .tools import get_tools_for_task, set_workspace, ToolExecutor, has_tool_calls, get_tool_calls, ALL_TOOLS
from .logger import (
    agent_logger,
    log_model_call,
    log_model_response,
    log_classification,
    log_error,
    log_tool_call,
    log_tool_result,
    log_agentic_start,
    log_agentic_complete,
    log_agentic_iteration,
    log_agentic_max_iterations
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
    tools_used: List[str] = field(default_factory=list)
    tool_calls_count: int = 0
    iterations: int = 1
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

# Implicit rules that the agent MUST follow
IMPLICIT_RULES_PROMPT = """

YOU ARE A COLLABORATIVE AI ASSISTANT. The human is your partner, not just a recipient.

═══════════════════════════════════════════════════════════════
CORE PRINCIPLE: COMMUNICATE, DON'T JUST EXECUTE
═══════════════════════════════════════════════════════════════

Before ANY tool call, explain what you're about to do and why.
After ANY tool call, share what you observed and learned.
This keeps the human informed and allows them to guide you.

GOOD EXAMPLE:
"I'll read Tasks.md to understand our current progress..."
[tool call: read_file]
"I see we've completed Phase 1 and 2. Phase 3 has 4 tasks remaining. 
Should I start with 'Implement task validation'?"

BAD EXAMPLE:
[tool call: read_file]
[tool call: create_file]
[tool call: run_terminal_command]
(No explanation, human has no idea what's happening)

═══════════════════════════════════════════════════════════════
INCREMENTAL DEVELOPMENT: ONE STEP AT A TIME
═══════════════════════════════════════════════════════════════

SIMPLE TASKS (move, delete, rename, single file edit):
→ Complete in 1-2 tool calls. Be direct.

COMPLEX TASKS (multi-file projects, phase-based work):
→ Work on ONE sub-task at a time
→ After completing each sub-task, pause and report to user
→ Let the user decide whether to continue or take over
→ Example: "I've set up the database models. Want me to proceed 
  with the API endpoints, or would you like to review first?"

NEVER try to complete an entire phase or project in one go.
The human may want to modify, test, or take a different approach.

═══════════════════════════════════════════════════════════════
SMART FILE DISCOVERY
═══════════════════════════════════════════════════════════════

If a file is not found (like Task.md), search for alternatives:
- Try common variations: Tasks.md, task.md, TODO.md, tasks.txt
- Use list_files to see what's available
- Report what you found to the user

═══════════════════════════════════════════════════════════════
DIRECT ACTIONS (No over-thinking needed)
═══════════════════════════════════════════════════════════════

"delete X" → delete_file(X) directly. Don't read it first.
"move X to Y" → move_file(X, Y) directly. Don't read it first.
"create X" → create_file(X). Don't search first.
"run X" → run_terminal_command(X). Actually run it.
"fix X" → Read only if needed to understand the error.

═══════════════════════════════════════════════════════════════
FILE EDITING: USE PATCH_FILE FOR EXISTING FILES
═══════════════════════════════════════════════════════════════

CRITICAL: When modifying an EXISTING file, use patch_file() for targeted edits!

✅ CORRECT (preserves rest of file):
  patch_file("config.py", "DEBUG = False", "DEBUG = True")
  patch_file("utils.py", "def old_func():", "def new_func():")
  
❌ WRONG (overwrites entire file):
  create_file("config.py", "DEBUG = True")  ← Loses all other content!
  modify_file("config.py", "DEBUG = True")  ← Also requires full content!

WHEN TO USE EACH TOOL:
- create_file → NEW files only (file doesn't exist)
- modify_file → When rewriting ENTIRE file (rare)
- patch_file → Updating SECTIONS of existing files (most common!)

═══════════════════════════════════════════════════════════════
AVOID LOOPS AND RETRIES
═══════════════════════════════════════════════════════════════

If a tool fails:
1. Explain the error to the user
2. Try ONE alternative approach
3. If still failing, ASK the user for guidance

NEVER run the same command more than twice.
NEVER call the same tool repeatedly without explaining why.

═══════════════════════════════════════════════════════════════
═══════════════════════════════════════════════════════════════
PROJECT TRACKING (Task.md) - MANDATORY
═══════════════════════════════════════════════════════════════

For ANY complex or multi-file project, it is MANDATORY to:
- ALWAYS create a `Tasks.md` (or `task.md`) file at the root to track sub-tasks.
- READ this file FIRST before starting work to understand current progress.
- Maintain checkboxes ([ ] -> [x]) as you finish steps.
- Use `patch_file()` for targeted updates to avoid overwriting the whole file.
- This file is your shared roadmap with the user.

═══════════════════════════════════════════════════════════════
LARGE FILES
═══════════════════════════════════════════════════════════════

If read_file returns "is_large_file": true:
- Use read_file_chunk(path, start_line, end_line)
- Read only the sections you need

═══════════════════════════════════════════════════════════════
TERMINAL COMMANDS: LET THE USER RUN TESTS
═══════════════════════════════════════════════════════════════

For TESTING and VALIDATION (pytest, npm test, etc.):
- DON'T run tests automatically
- Instead, TELL the user the commands to run:
  "You can test this with: `python -m pytest tests/`"
- The user can run it themselves and share results if needed

ONLY run terminal commands automatically when:
- User explicitly says "run it" or "test it"
- Installing dependencies (pip install)
- Creating/initializing projects
- User specifically requests execution

This saves tokens and gives the user full control over testing.

═══════════════════════════════════════════════════════════════
THE GOLDEN RULE
═══════════════════════════════════════════════════════════════

Always give the human context and control.
They should never wonder "what is the AI doing?" or "why did it do that?"
"""



class _LoopDetector:
    """Detects if the agent is stuck in a loop calling the same tools repeatedly."""
    
    def __init__(self, window_size: int = 5, threshold: int = 3):
        self.history = []
        self.window_size = window_size
        self.threshold = threshold
    
    def add_call(self, tool_name: str, tool_args: dict) -> None:
        """Add a tool call to history."""
        # Create a signature for this call (tool name + key args)
        key_args = str(sorted(tool_args.items())[:3]) if tool_args else ""
        call_signature = f"{tool_name}:{key_args}"
        
        self.history.append(call_signature)
        if len(self.history) > self.window_size:
            self.history.pop(0)
    
    def is_looping(self) -> bool:
        """Check if the same call is repeating too many times."""
        if len(self.history) < self.threshold:
            return False
        
        # Check if last N calls are identical
        recent = self.history[-self.threshold:]
        return len(set(recent)) == 1  # All identical
    
    def reset(self) -> None:
        """Reset the detector."""
        self.history = []


def _get_progress_message(tool_name: str, tool_args: dict) -> str:
    """Generate a human-readable progress message for a tool call."""
    
    # Extract common args
    path = tool_args.get('path', tool_args.get('file_path', ''))
    if path:
        # Get just the filename
        path = path.replace('\\', '/').split('/')[-1]
    
    messages = {
        'read_file': f"Reading `{path}`...",
        'create_file': f"Creating `{path}`...",  
        'modify_file': f"Modifying `{path}`...",
        'delete_file': f"Deleting `{path}`...",
        'list_files': "Scanning directory structure...",
        'search_code': f"Searching for pattern in codebase...",
        'run_terminal_command': f"Running command...",
    }
    
    return messages.get(tool_name, f"Executing {tool_name}...")


def _generate_tool_explanation(tool_name: str, tool_args: dict, total_tools: int) -> str:
    """Generate a conversational explanation when model doesn't provide text before tools."""
    
    # Extract common args
    path = tool_args.get('path', tool_args.get('file_path', ''))
    if path:
        path = path.replace('\\', '/').split('/')[-1]  # Get filename only
    
    explanations = {
        'read_file': f"Let me read `{path}` to understand the current state...",
        'create_file': f"I'll create `{path}` with the implementation...",
        'modify_file': f"I'll update `{path}` with the necessary changes...",
        'delete_file': f"I'll remove `{path}` as it's no longer needed...",
        'list_files': "Let me scan the directory to see what files we have...",
        'search_code': "I'll search the codebase for relevant code...",
        'run_terminal_command': f"I'll run a command to {tool_args.get('command', 'execute this task')[:30]}...",
        'move_file': f"I'll move `{tool_args.get('source', 'file')}` to its new location...",
    }
    
    base = explanations.get(tool_name, f"I'll use `{tool_name}` to help with this...")
    
    if total_tools > 1:
        base += f" (and {total_tools - 1} more action{'s' if total_tools > 2 else ''})"
    
    return base


def _generate_observation(tool_name: str, tool_args: dict, result: str) -> str:
    """Generate a human-readable observation after a tool completes."""
    
    result_lower = result.lower() if result else ""
    result_start = result[:200].lower() if result else ""  # Check only beginning of result
    path = tool_args.get('path', tool_args.get('file_path', ''))
    if path:
        path = path.replace('\\', '/').split('/')[-1]
    
    # Handle errors/failures - check for actual ERROR patterns, not just keywords in content
    # Error results typically start with "Error:" or contain specific error messages
    is_error = (
        result_start.startswith("error:") or
        result_start.startswith("error -") or
        "filenotfounderror" in result_start or
        "does not exist" in result_start or
        "no such file" in result_start or
        "failed:" in result_start or
        "permission denied" in result_start
    )
    
    if is_error:
        if tool_name == "read_file":
            return f"⚠️ `{path}` not found. Let me search for similar files..."
        elif tool_name == "run_terminal_command":
            return "⚠️ Command failed. Let me check the error and try a fix..."
        elif tool_name == "list_files":
            return "⚠️ Could not list directory. Checking permissions..."
        else:
            return f"⚠️ {tool_name} encountered an issue. Adjusting approach..."
    
    # Handle successes - don't show observation for reads (too verbose)
    if tool_name == "read_file":
        return None  # Success reads don't need observation
    
    elif tool_name == "list_files":
        return "✓ Found the directory structure. Looking for relevant files..."
    
    elif tool_name == "create_file":
        return f"✓ Created `{path}` successfully."
    
    elif tool_name == "modify_file":
        return f"✓ Updated `{path}` with the changes."
    
    elif tool_name == "delete_file":
        return f"✓ Deleted `{path}`."
    
    elif tool_name == "run_terminal_command":
        if "exit_code\": 0" in result_lower or "exit code: 0" in result_lower or '"success": true' in result_lower:
            return "✓ Command completed successfully."
        return None
    
    return None  # No observation needed for other tools


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
        
        # Use Groq llama-3.3-70b-versatile for classification
        agent_logger.debug("Attempting to get Groq (llama-3.3-70b-versatile) for classification...")
        model = self.model_router.get_model_for_provider("groq", "llama-3.3-70b-versatile")
        provider = "groq"
        model_name = "llama-3.3-70b-versatile"
        
        if model is None:
            agent_logger.warning("Groq not available, trying Cerebras zai-glm-4.7...")
            # Fallback to Cerebras zai-glm-4.7
            model = self.model_router.get_model_for_provider("cerebras", "zai-glm-4.7")
            provider = "cerebras"
            model_name = "zai-glm-4.7"
        
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
        error_message: str = None,
        selected_model: Optional[str] = None
    ) -> AgentResponse:
        """
        Process a user query through the full agent pipeline.
        
        1. Classify the task
        2. Update context manager
        3. Get appropriate model
        4. Build context with token budgeting
        5. Execute with agentic tool loop (if applicable)
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
        
        # Add tool instructions if this task uses tools
        if self._should_use_tools(classification.task_type.value):
            system_prompt += self._get_tool_instructions()
        
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
        
        # Determine if we should use the agentic loop with tools
        use_tools = self._should_use_tools(classification.task_type.value)
        
        if use_tools:
            # Execute with agentic tool loop
            return await self._agentic_loop(
                messages=messages,
                task_type=classification.task_type.value,
                selected_model=selected_model
            )
        else:
            # Simple invocation without tools
            return await self._simple_invoke(
                messages=messages,
                task_type=classification.task_type.value,
                selected_model=selected_model
            )
    
    def _should_use_tools(self, task_type: str) -> bool:
        """Determine if this task type should use tools."""
        return task_type in AgentConfig.TOOL_ENABLED_TASKS
    
    def _get_tool_instructions(self) -> str:
        """Get instructions for the LLM about tool usage."""
        return """

You have access to tools to help complete the user's request.
Use tools when needed to:
- Read files to understand code
- Create or modify files
- Run commands to test code
- Search for code patterns

When using tools:
1. Think about what you need before calling tools
2. Use the appropriate tool for the task
3. Analyze tool results before responding
4. If a tool fails, try an alternative approach
5. Provide a clear final response after completing tool operations

IMPORTANT - TERMINAL COMMANDS:
- BY DEFAULT, use `suggest_command` to suggest commands for the user to run manually
- ONLY use `run_terminal_command` if the user EXPLICITLY asks you to run/execute something
- Examples of explicit execution requests: "run this", "execute the code", "start the server for me"
- For package installs (pip, npm, etc.), ALWAYS use `suggest_command` unless user explicitly says "install for me"

After completing all necessary tool operations, provide your final response to the user.
"""
    
    async def _simple_invoke(
        self,
        messages: list,
        task_type: str,
        selected_model: Optional[str] = None
    ) -> AgentResponse:
        """Simple model invocation without tools."""
        agent_logger.info(f"🔄 Simple invoke (no tools) for task: {task_type}")
        
        try:
            if selected_model and selected_model != "Auto":
                # User selected specific model - NO fallback
                provider, model_key = selected_model.split("/")
                model = self.model_router.get_model_for_provider(provider, model_key)
                if model is None:
                    raise Exception(f"Could not load selected model: {selected_model}")
                    
                response = await model.ainvoke(messages)
                model_name = model_key # Will be resolved in get_model_for_provider
            else:
                # Auto mode - use fallback chain
                response, provider, model_name = await self.model_router.invoke_with_fallback(
                    task_type=task_type,
                    messages=messages
                )
            
            if response is None:
                agent_logger.error("❌ All models failed, including fallbacks")
                return AgentResponse(
                    success=False,
                    response="All models failed. Please check if Ollama is running with: ollama serve",
                    task_type=task_type,
                    model_used="none",
                    provider="none",
                    error="All models unavailable"
                )
            
            agent_logger.info(f"✅ Model response received: {provider}/{model_name}")
            
            # Record assistant response in context
            self.context_manager.add_message("assistant", response.content, task_type)
            
            return AgentResponse(
                success=True,
                response=response.content,
                task_type=task_type,
                model_used=model_name,
                provider=provider,
                tools_used=[],
                tool_calls_count=0,
                iterations=1
            )
            
        except Exception as e:
            agent_logger.error(f"❌ Simple invoke failed: {e}")
            self.context_manager.record_error(str(e))
            return AgentResponse(
                success=False,
                response=f"Error: {str(e)}",
                task_type=task_type,
                model_used="unknown",
                provider="unknown",
                error=str(e)
            )
    
    async def _agentic_loop(
        self,
        messages: list,
        task_type: str,
        selected_model: Optional[str] = None
    ) -> AgentResponse:
        """
        Execute an agentic loop with tool calling.
        
        The loop:
        1. Invokes the model with tools bound
        2. If model returns tool calls, execute them
        3. Add tool results to messages
        4. Repeat until no more tool calls or max iterations
        5. Return final response
        """
        # Get tools for this task type
        tools = get_tools_for_task(task_type)
        
        log_agentic_start(task_type, len(tools))
        
        # Create tool executor
        tool_executor = ToolExecutor(tools, timeout_seconds=AgentConfig.TOOL_TIMEOUT_SECONDS)
        
        # Get model for this task
        if selected_model and selected_model != "Auto":
            # User selected specific model
            provider, model_key = selected_model.split("/")
            model = self.model_router.get_model_for_provider(provider, model_key)
            model_name = model_key
            use_fallback = False
        else:
            # Auto mode
            model = self.model_router.get_model(task_type)
            use_fallback = True
            
            # Get model info for logging
            models_chain = AgentConfig.get_models_for_task(task_type)
            if models_chain:
                provider, model_key = models_chain[0]
                provider_config = AgentConfig.get_provider(provider)
                model_name = provider_config.models[model_key].name if provider_config and model_key in provider_config.models else "unknown"
            else:
                provider = "unknown"
                model_name = "unknown"
        
        # Bind tools to the model
        try:
            model_with_tools = model.bind_tools(tools)
            agent_logger.info(f"🔧 Bound {len(tools)} tools to model {provider}/{model_name}")
        except Exception as e:
            agent_logger.warning(f"⚠️ Model doesn't support tool binding: {e}")
            agent_logger.info("Falling back to simple invoke")
            return await self._simple_invoke(messages, task_type)
        
        # Agentic loop
        max_iterations = AgentConfig.MAX_TOOL_ITERATIONS
        current_messages = list(messages)  # Copy messages
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            agent_logger.info(f"🔄 Agentic loop iteration {iteration}/{max_iterations}")
            
            try:
                # Invoke model with tools
                response = await model_with_tools.ainvoke(current_messages)
                
                # Check if response has tool calls
                if has_tool_calls(response):
                    tool_calls = get_tool_calls(response)
                    agent_logger.info(f"🔧 Model requested {len(tool_calls)} tool calls")
                    
                    # Log iteration with pending tool calls
                    log_agentic_iteration(iteration, tool_executor.get_total_tool_calls(), has_more_calls=True)
                    
                    # Add the AI message with tool calls to conversation
                    current_messages.append(response)
                    
                    # Execute tools
                    tool_messages = await tool_executor.execute_tool_calls(tool_calls)
                    
                    # Add tool results to conversation
                    current_messages.extend(tool_messages)
                    
                    # Continue loop to let model process tool results
                    continue
                else:
                    # No tool calls - model has finished
                    agent_logger.info(f"✅ Model finished without more tool calls")
                    log_agentic_iteration(iteration, tool_executor.get_total_tool_calls(), has_more_calls=False)
                    
                    # Get execution summary
                    summary = tool_executor.get_execution_summary()
                    log_agentic_complete(iteration, summary["tools_used"], summary["total_calls"])
                    
                    # Record assistant response in context
                    self.context_manager.add_message("assistant", response.content, task_type)
                    
                    # Record files modified/created in session
                    for tool_name in summary["tools_used"]:
                        if tool_name == "create_file":
                            # Would need to track specific files - for now just log
                            pass
                        elif tool_name == "modify_file":
                            pass
                    
                    return AgentResponse(
                        success=True,
                        response=response.content,
                        task_type=task_type,
                        model_used=model_name,
                        provider=provider,
                        tools_used=summary["tools_used"],
                        tool_calls_count=summary["total_calls"],
                        iterations=iteration
                    )
                    
            except Exception as e:
                agent_logger.error(f"❌ Error in agentic loop iteration {iteration}: {e}")
                self.context_manager.record_error(str(e))
                
                # Check for rate limit and fallback if enabled
                error_str = str(e)
                is_rate_limit = "429" in error_str or "rate limit" in error_str.lower() or "quota" in error_str.lower()
                
                if is_rate_limit and use_fallback:
                    agent_logger.warning(f"⚠️ Rate limit hit in _agentic_loop, trying rotation/fallback...")
                    # For synchronous _agentic_loop, fallback is more complex to implement mid-stream
                    # but we can try rotating credentials for the model used
                    self.model_router.cred_manager.rotate_credential(provider)
                    # Note: Full mid-loop model switching for sync method is omitted for brevity 
                    # as streaming is the primary interaction mode
                
                # If we had some successful tool calls, return partial result
                summary = tool_executor.get_execution_summary()
                if summary["total_calls"] > 0:
                    return AgentResponse(
                        success=False,
                        response=f"Error during execution: {str(e)}. Completed {summary['total_calls']} tool calls before error.",
                        task_type=task_type,
                        model_used=model_name,
                        provider=provider,
                        tools_used=summary["tools_used"],
                        tool_calls_count=summary["total_calls"],
                        iterations=iteration,
                        error=str(e)
                    )
                else:
                    return AgentResponse(
                        success=False,
                        response=f"Error: {str(e)}",
                        task_type=task_type,
                        model_used=model_name,
                        provider=provider,
                        error=str(e)
                    )
        
        # Max iterations reached
        log_agentic_max_iterations(max_iterations, iteration)
        summary = tool_executor.get_execution_summary()
        
        # Try to get final response from last message
        last_ai_message = None
        for msg in reversed(current_messages):
            if isinstance(msg, AIMessage) and msg.content:
                last_ai_message = msg
                break
        
        final_response = last_ai_message.content if last_ai_message else "Maximum iterations reached. Task may be incomplete."
        
        return AgentResponse(
            success=True,  # Partial success
            response=final_response + f"\n\n[Note: Reached maximum {max_iterations} iterations]",
            task_type=task_type,
            model_used=model_name,
            provider=provider,
            tools_used=summary["tools_used"],
            tool_calls_count=summary["total_calls"],
            iterations=iteration
        )
    
    async def process_stream(
        self,
        query: str,
        current_file: str = None,
        file_content: str = None,
        selected_code: str = None,
        terminal_output: str = None,
        error_message: str = None,
        selected_model: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process a user query with streaming responses.
        
        Yields SSE events:
        - classification: Task classification result
        - token: Individual response tokens
        - tool_start: Tool execution starting
        - tool_complete: Tool execution completed
        - done: Final completion signal
        """
        # Update task context
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
        
        # Yield classification result
        yield {
            "type": "classification",
            "task_type": classification.task_type.value,
            "confidence": classification.confidence
        }
        
        # Build context and messages
        context_data = self.context_manager.get_context_for_task(classification.task_type.value)
        system_prompt = self._build_system_prompt(classification.task_type)
        
        if self._should_use_tools(classification.task_type.value):
            system_prompt += self._get_tool_instructions()
        
        context_parts = []
        if context_data["permanent"]:
            context_parts.append(context_data["permanent"])
        if context_data["task"]:
            context_parts.append(context_data["task"])
        if context_data["summary"]:
            context_parts.append(context_data["summary"])
        if context_data["session"]:
            context_parts.append(context_data["session"])
        
        context = "\n\n".join(context_parts) if context_parts else ""
        user_message = f"{context}\n\nUser request: {query}" if context else query
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ]
        
        self.context_manager.add_message("user", query, classification.task_type.value)
        
        use_tools = self._should_use_tools(classification.task_type.value)
        
        if use_tools:
            # Streaming agentic loop
            async for chunk in self._agentic_loop_stream(
                messages=messages,
                task_type=classification.task_type.value,
                selected_model=selected_model
            ):
                yield chunk
        else:
            # Simple streaming without tools
            async for chunk in self._simple_stream(
                messages=messages,
                task_type=classification.task_type.value,
                selected_model=selected_model
            ):
                yield chunk
    
    async def _simple_stream(
        self,
        messages: list,
        task_type: str,
        selected_model: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Simple streaming invocation without tools."""
        agent_logger.info(f"🔄 Simple stream (no tools) for task: {task_type}")
        
        # Get model
        if selected_model and selected_model != "Auto":
            provider, model_key = selected_model.split("/")
            model = self.model_router.get_model_for_provider(provider, model_key)
            model_name = model_key
            use_fallback = False
        else:
            model = self.model_router.get_model(task_type)
            use_fallback = True
            
            # Get model info for response
            models_chain = AgentConfig.get_models_for_task(task_type)
            if models_chain:
                provider, model_key = models_chain[0]
                provider_config = AgentConfig.get_provider(provider)
                model_name = provider_config.models[model_key].name if provider_config and model_key in provider_config.models else "unknown"
            else:
                provider = "unknown"
                model_name = "unknown"
        
        try:
            full_response = ""
            
            # Stream tokens using astream
            async for chunk in model.astream(messages):
                token = chunk.content if hasattr(chunk, 'content') else str(chunk)
                if token:
                    full_response += token
                    yield {"type": "token", "content": token}
            
            agent_logger.info(f"✅ Stream complete: {provider}/{model_name}")
            
            # Record in context
            self.context_manager.add_message("assistant", full_response, task_type)
            
            yield {
                "type": "done",
                "model": model_name,
                "provider": provider,
                "task_type": task_type,
                "iterations": 1,
                "tool_calls_count": 0
            }
            
        except Exception as e:
            agent_logger.error(f"❌ Simple stream error: {e}")
            yield {"type": "error", "message": str(e)}
    
    async def _agentic_loop_stream(
        self,
        messages: list,
        task_type: str,
        selected_model: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streaming agentic loop with tool calling."""
        tools = get_tools_for_task(task_type)
        log_agentic_start(task_type, len(tools))
        
        tool_executor = ToolExecutor(tools, timeout_seconds=AgentConfig.TOOL_TIMEOUT_SECONDS)
        # Get model
        if selected_model and selected_model != "Auto":
            provider, model_key = selected_model.split("/")
            model = self.model_router.get_model_for_provider(provider, model_key)
            model_name = model_key
            use_fallback = False
        else:
            model = self.model_router.get_model(task_type)
            use_fallback = True
            
            # Get model info
            models_chain = AgentConfig.get_models_for_task(task_type)
            if models_chain:
                provider, model_key = models_chain[0]
                provider_config = AgentConfig.get_provider(provider)
                model_name = provider_config.models[model_key].name if provider_config and model_key in provider_config.models else "unknown"
            else:
                provider = "unknown"
                model_name = "unknown"
        
        # Bind tools
        try:
            model_with_tools = model.bind_tools(tools)
            agent_logger.info(f"🔧 Bound {len(tools)} tools to model for streaming")
        except Exception as e:
            agent_logger.warning(f"⚠️ Tool binding failed: {e}")
            async for chunk in self._simple_stream(messages, task_type):
                yield chunk
            return
        
        max_iterations = AgentConfig.MAX_TOOL_ITERATIONS
        current_messages = list(messages)
        iteration = 0
        loop_detector = _LoopDetector(window_size=5, threshold=3)
        
        while iteration < max_iterations:
            iteration += 1
            remaining = max_iterations - iteration
            agent_logger.info(f"🔄 Streaming agentic loop iteration {iteration}/{max_iterations}")
            
            yield {"type": "iteration", "current": iteration, "max": max_iterations, "remaining": remaining}
            
            # Iteration warning: when 1 iteration remains, inject summary request
            if remaining <= 1:
                agent_logger.info(f"⚠️ {remaining} iterations remaining - injecting summary reminder")
                summary_request = f"""
[SYSTEM: CRITICAL RESOURCE LIMIT]
Only {remaining} tool iteration remaining!
You MUST include a "PROGRESS SUMMARY" block in your response:
- ✅ WHAT IS DONE: (List completed steps)
- ⏳ WHAT IS PENDING: (List remaining steps)
- 📋 CONTINUATION DATA: (Briefly describe current state for next session)

You MUST provide this summary NOW as this is your LAST chance to speak.
"""
                # Check if we already added a summary request recently to avoid bloating
                if not any("[SYSTEM: CRITICAL RESOURCE LIMIT]" in getattr(m, 'content', '') for m in current_messages[-2:]):
                    current_messages.append(SystemMessage(content=summary_request))
                
                if remaining == 1:
                    yield {"type": "iteration_warning", "remaining": remaining, "message": "LAST iteration remaining - summarizing progress"}
            
            try:
                # Collect full response (can't stream when checking for tool calls)
                response = await model_with_tools.ainvoke(current_messages)

                
                if has_tool_calls(response):
                    tool_calls = get_tool_calls(response)
                    agent_logger.info(f"🔧 Model requested {len(tool_calls)} tool calls")
                    
                    current_messages.append(response)
                    
                    # Execute tools with progress messages before and after each
                    for tool_call in tool_calls:
                        tool_name = tool_call.get("name", "") if isinstance(tool_call, dict) else getattr(tool_call, "name", "")
                        tool_args = tool_call.get("args", {}) if isinstance(tool_call, dict) else getattr(tool_call, "args", {})
                        
                        # Check for loop
                        loop_detector.add_call(tool_name, tool_args)
                        if loop_detector.is_looping():
                            agent_logger.warning("⚠️ Loop detected, stopping to avoid infinite execution")
                            yield {"type": "message", "content": "⚠️ Detected repetitive actions. Stopping to avoid infinite loop."}
                            summary = tool_executor.get_execution_summary()
                            yield {
                                "type": "done",
                                "model": model_name,
                                "provider": provider,
                                "task_type": task_type,
                                "iterations": iteration,
                                "tool_calls_count": summary["total_calls"],
                                "tools_used": summary["tools_used"],
                                "loop_detected": True
                            }
                            return
                        
                        # 1. Progress message BEFORE tool
                        progress_msg = _get_progress_message(tool_name, tool_args)
                        yield {"type": "message", "content": progress_msg}
                        
                        # 2. Tool start
                        yield {"type": "tool_start", "tool": tool_name, "args": tool_args}
                        
                        # 3. Execute tool
                        tool_messages = await tool_executor.execute_tool_calls([tool_call])
                        current_messages.extend(tool_messages)
                        
                        # 4. Tool complete
                        result = tool_messages[0].content if tool_messages else "completed"
                        yield {"type": "tool_complete", "tool": tool_name, "result": result}
                        
                        # 5. Observation AFTER tool
                        observation = _generate_observation(tool_name, tool_args, result)
                        if observation:
                            yield {"type": "message", "content": observation}
                        
                        # 6. File tree update for file-modifying operations
                        file_modifying_tools = ["create_file", "delete_file", "modify_file", "move_file", "rename_file"]
                        if tool_name in file_modifying_tools:
                            yield {"type": "file_tree_updated"}
                    
                    continue
                else:
                    # No tool calls - stream the final response text
                    if response.content:
                        # Yield content in chunks for smoother streaming
                        content = response.content
                        chunk_size = 10  # Characters per chunk
                        for i in range(0, len(content), chunk_size):
                            yield {"type": "token", "content": content[i:i+chunk_size]}
                    
                    summary = tool_executor.get_execution_summary()
                    log_agentic_complete(iteration, summary["tools_used"], summary["total_calls"])
                    
                    self.context_manager.add_message("assistant", response.content, task_type)
                    
                    yield {
                        "type": "done",
                        "model": model_name,
                        "provider": provider,
                        "task_type": task_type,
                        "iterations": iteration,
                        "tool_calls_count": summary["total_calls"],
                        "tools_used": summary["tools_used"]
                    }
                    return
                    
            except Exception as e:
                error_str = str(e)
                # Check if this is a rate limit error (429)
                if "429" in error_str or "rate limit" in error_str.lower() or "quota" in error_str.lower():
                    agent_logger.warning(f"⚠️ Rate limit hit: {error_str[:100]}...")
                    
                    # STEP 1: Always try rotating credentials within same provider first
                    current_provider = provider
                    cred_rotated = self.model_router.cred_manager.rotate_credential(current_provider)
                    
                    if cred_rotated:
                        agent_logger.info(f"🔄 Rotated to next API key for {current_provider}")
                        yield {"type": "message", "content": f"⚠️ Rate limit hit. Trying next API key for {current_provider}..."}
                        
                        try:
                            # Get fresh model with rotated credentials
                            # If pinned, we need to ensure we get the same model again
                            if selected_model and selected_model != "Auto":
                                prov, m_key = selected_model.split("/")
                                rotated_model = self.model_router.get_model_for_provider(prov, m_key)
                            else:
                                rotated_model = self.model_router.get_model(task_type)
                                
                            if rotated_model:
                                model_with_tools = rotated_model.bind_tools(tools)
                                agent_logger.info(f"✅ Credential rotation successful for {current_provider}")
                                yield {"type": "message", "content": f"✓ Using next API key for {current_provider}"}
                                iteration -= 1  # Retry this iteration
                                continue
                        except Exception as rot_error:
                            agent_logger.warning(f"⚠️ Credential rotation failed: {rot_error}")
                    
                    # STEP 2: Try fallback providers ONLY IF use_fallback is true (Auto mode)
                    if use_fallback:
                        models_chain = AgentConfig.get_models_for_task(task_type)
                        if models_chain and len(models_chain) > 1:
                            for fallback_idx in range(1, len(models_chain)):
                                fallback_provider, fallback_model_key = models_chain[fallback_idx]
                                agent_logger.info(f"🔄 Trying fallback: {fallback_provider}/{fallback_model_key}")
                                
                                yield {"type": "message", "content": f"⚠️ Switching to {fallback_provider}..."}
                                
                                try:
                                    fallback_model = self.model_router.get_model_for_provider(fallback_provider, fallback_model_key)
                                    if fallback_model:
                                        provider_config = AgentConfig.get_provider(fallback_provider)
                                        model_name = provider_config.models[fallback_model_key].name if provider_config and fallback_model_key in provider_config.models else "unknown"
                                        provider = fallback_provider
                                        
                                        # Rebind tools with fallback model
                                        model_with_tools = fallback_model.bind_tools(tools)
                                        agent_logger.info(f"✅ Fallback successful: {fallback_provider}/{model_name}")
                                        yield {"type": "message", "content": f"✓ Using {fallback_provider}/{model_name}"}
                                        
                                        # Continue with the loop (don't increment iteration for retry)
                                        iteration -= 1
                                        break
                                except Exception as fallback_error:
                                    agent_logger.warning(f"⚠️ Fallback {fallback_provider} also failed: {fallback_error}")
                                    continue
                            else:
                                # All fallbacks exhausted
                                agent_logger.error(f"❌ All fallback providers exhausted")
                                yield {"type": "error", "message": "Rate limit exceeded on all providers. Please wait and try again."}
                                return
                        else:
                            yield {"type": "error", "message": f"Rate limit exceeded: {error_str[:100]}"}
                            return
                    else:
                        # Pinned model - all local keys failed, don't fall back to other providers
                        agent_logger.error(f"❌ Key rotation failed for pinned model {provider}")
                        yield {"type": "error", "message": f"Rate limit exceeded for your selected model ({provider}). Please try another model or wait."}
                        return
                else:
                    agent_logger.error(f"❌ Agentic stream error: {e}")
                    yield {"type": "error", "message": str(e)}
                    return
        
        # Max iterations reached
        log_agentic_max_iterations(max_iterations, iteration)
        summary = tool_executor.get_execution_summary()
        
        yield {
            "type": "done",
            "model": model_name,
            "provider": provider,
            "task_type": task_type,
            "iterations": iteration,
            "tool_calls_count": summary["total_calls"],
            "tools_used": summary["tools_used"],
            "max_iterations_reached": True
        }

    
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
        return base_prompt + task_prompts.get(task_type, "") + IMPLICIT_RULES_PROMPT
