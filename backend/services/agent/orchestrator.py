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
                task_type=classification.task_type.value
            )
        else:
            # Simple invocation without tools
            return await self._simple_invoke(
                messages=messages,
                task_type=classification.task_type.value
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

After completing all necessary tool operations, provide your final response to the user.
"""
    
    async def _simple_invoke(
        self,
        messages: list,
        task_type: str
    ) -> AgentResponse:
        """Simple model invocation without tools."""
        agent_logger.info(f"🔄 Simple invoke (no tools) for task: {task_type}")
        
        try:
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
            self.context_manager.add_message("assistant", response.content[:500], task_type)
            
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
        task_type: str
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
        
        # Get model for this task (we'll bind tools to it)
        model = self.model_router.get_model(task_type)
        
        if model is None:
            agent_logger.error("❌ No model available for agentic loop")
            return AgentResponse(
                success=False,
                response="No model available. Please check if Ollama is running.",
                task_type=task_type,
                model_used="none",
                provider="none",
                error="No model available"
            )
        
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
                    self.context_manager.add_message("assistant", response.content[:500], task_type)
                    
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
        error_message: str = None
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
                task_type=classification.task_type.value
            ):
                yield chunk
        else:
            # Simple streaming without tools
            async for chunk in self._simple_stream(
                messages=messages,
                task_type=classification.task_type.value
            ):
                yield chunk
    
    async def _simple_stream(
        self,
        messages: list,
        task_type: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Simple streaming invocation without tools."""
        agent_logger.info(f"🔄 Simple stream (no tools) for task: {task_type}")
        
        model = self.model_router.get_model(task_type)
        
        if model is None:
            yield {"type": "error", "message": "No model available"}
            return
        
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
            self.context_manager.add_message("assistant", full_response[:500], task_type)
            
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
        task_type: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streaming agentic loop with tool calling."""
        tools = get_tools_for_task(task_type)
        log_agentic_start(task_type, len(tools))
        
        tool_executor = ToolExecutor(tools, timeout_seconds=AgentConfig.TOOL_TIMEOUT_SECONDS)
        model = self.model_router.get_model(task_type)
        
        if model is None:
            yield {"type": "error", "message": "No model available"}
            return
        
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
        
        while iteration < max_iterations:
            iteration += 1
            agent_logger.info(f"🔄 Streaming agentic loop iteration {iteration}/{max_iterations}")
            
            yield {"type": "iteration", "current": iteration, "max": max_iterations}
            
            try:
                # Collect full response (can't stream when checking for tool calls)
                response = await model_with_tools.ainvoke(current_messages)
                
                if has_tool_calls(response):
                    tool_calls = get_tool_calls(response)
                    agent_logger.info(f"🔧 Model requested {len(tool_calls)} tool calls")
                    
                    current_messages.append(response)
                    
                    # Execute tools and yield progress
                    for tool_call in tool_calls:
                        tool_name = tool_call.get("name", "") if isinstance(tool_call, dict) else getattr(tool_call, "name", "")
                        
                        yield {"type": "tool_start", "tool": tool_name}
                        
                        # Execute single tool
                        tool_messages = await tool_executor.execute_tool_calls([tool_call])
                        current_messages.extend(tool_messages)
                        
                        # Get result for yield
                        result = tool_messages[0].content if tool_messages else "completed"
                        yield {"type": "tool_complete", "tool": tool_name, "result": result[:200]}
                    
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
                    
                    self.context_manager.add_message("assistant", response.content[:500], task_type)
                    
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
        
        return base_prompt + task_prompts.get(task_type, "")
