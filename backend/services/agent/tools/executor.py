"""
Tool Executor for AI Agent

Handles:
- Executing tool calls from LLM responses
- Formatting tool results as ToolMessages
- Error handling and logging
- Timeout management

This is the core engine that makes agentic loops work.
"""

import asyncio
import time
from typing import List, Dict, Any, Optional, Callable
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
import logging

# Setup logger
logger = logging.getLogger("tool_executor")


class ToolExecutionResult:
    """Result of a single tool execution."""
    
    def __init__(
        self,
        tool_name: str,
        tool_call_id: str,
        success: bool,
        result: Any = None,
        error: Optional[str] = None,
        duration_ms: float = 0
    ):
        self.tool_name = tool_name
        self.tool_call_id = tool_call_id
        self.success = success
        self.result = result
        self.error = error
        self.duration_ms = duration_ms
    
    def to_tool_message(self) -> ToolMessage:
        """Convert to LangChain ToolMessage."""
        if self.success:
            content = self._format_result(self.result)
        else:
            content = f"Error executing {self.tool_name}: {self.error}"
        
        return ToolMessage(
            content=content,
            tool_call_id=self.tool_call_id,
            name=self.tool_name
        )
    
    def _format_result(self, result: Any) -> str:
        """Format tool result as string for LLM."""
        if result is None:
            return "Tool executed successfully (no output)"
        
        if isinstance(result, dict):
            # Format dict nicely
            if "error" in result:
                return f"Error: {result['error']}"
            elif "content" in result:
                # File content - may be large
                content = result.get("content", "")
                if len(content) > 5000:
                    return f"File content (truncated):\n{content[:5000]}...\n[Truncated: {len(content)} chars total]"
                return f"File content:\n{content}"
            else:
                # Generic dict formatting
                import json
                try:
                    return json.dumps(result, indent=2, default=str)
                except:
                    return str(result)
        
        if isinstance(result, str):
            # Truncate long strings
            if len(result) > 5000:
                return f"{result[:5000]}...\n[Truncated: {len(result)} chars total]"
            return result
        
        return str(result)


class ToolExecutor:
    """
    Executes tool calls from LLM responses.
    
    Features:
    - Maps tool names to tool functions
    - Executes tools with error handling
    - Supports async execution
    - Tracks execution time
    - Logs all tool operations
    """
    
    def __init__(self, tools: List[BaseTool], timeout_seconds: int = 30):
        """
        Initialize executor with available tools.
        
        Args:
            tools: List of LangChain tools
            timeout_seconds: Timeout for each tool execution
        """
        self.tools = {tool.name: tool for tool in tools}
        self.timeout_seconds = timeout_seconds
        self.execution_history: List[ToolExecutionResult] = []
        
        logger.info(f"🔧 ToolExecutor initialized with {len(tools)} tools: {list(self.tools.keys())}")
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self.tools.get(name)
    
    async def execute_tool_call(self, tool_call: Any) -> ToolExecutionResult:
        """
        Execute a single tool call.
        
        Args:
            tool_call: Tool call from LLM response (has name, args, id)
            
        Returns:
            ToolExecutionResult with result or error
        """
        tool_name = tool_call.get("name", "") if isinstance(tool_call, dict) else getattr(tool_call, "name", "")
        tool_call_id = tool_call.get("id", "") if isinstance(tool_call, dict) else getattr(tool_call, "id", "")
        tool_args = tool_call.get("args", {}) if isinstance(tool_call, dict) else getattr(tool_call, "args", {})
        
        logger.info(f"🔧 Executing tool: {tool_name}")
        logger.debug(f"   Args: {tool_args}")
        
        start_time = time.time()
        
        # Check if tool exists
        tool = self.get_tool(tool_name)
        if tool is None:
            error_msg = f"Unknown tool: {tool_name}. Available: {list(self.tools.keys())}"
            logger.error(f"   ❌ {error_msg}")
            return ToolExecutionResult(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                success=False,
                error=error_msg
            )
        
        try:
            # Execute the tool
            # LangChain tools can be sync or async
            if asyncio.iscoroutinefunction(tool.invoke):
                result = await asyncio.wait_for(
                    tool.ainvoke(tool_args),
                    timeout=self.timeout_seconds
                )
            else:
                # Run sync tool in executor to not block
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: tool.invoke(tool_args)),
                    timeout=self.timeout_seconds
                )
            
            duration_ms = (time.time() - start_time) * 1000
            
            logger.info(f"   ✅ Tool {tool_name} completed in {duration_ms:.1f}ms")
            logger.debug(f"   Result: {str(result)[:200]}...")
            
            execution_result = ToolExecutionResult(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                success=True,
                result=result,
                duration_ms=duration_ms
            )
            
        except asyncio.TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = f"Tool execution timed out after {self.timeout_seconds}s"
            logger.error(f"   ⏱️ {error_msg}")
            
            execution_result = ToolExecutionResult(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                success=False,
                error=error_msg,
                duration_ms=duration_ms
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"   ❌ Tool error: {error_msg}")
            
            execution_result = ToolExecutionResult(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                success=False,
                error=error_msg,
                duration_ms=duration_ms
            )
        
        # Track execution history
        self.execution_history.append(execution_result)
        
        return execution_result
    
    async def execute_tool_calls(self, tool_calls: List[Any]) -> List[ToolMessage]:
        """
        Execute multiple tool calls and return ToolMessages.
        
        Args:
            tool_calls: List of tool calls from LLM response
            
        Returns:
            List of ToolMessages to add to conversation
        """
        if not tool_calls:
            return []
        
        logger.info(f"🔧 Executing {len(tool_calls)} tool calls...")
        
        tool_messages = []
        for tool_call in tool_calls:
            result = await self.execute_tool_call(tool_call)
            tool_messages.append(result.to_tool_message())
        
        return tool_messages
    
    def get_tools_used(self) -> List[str]:
        """Get list of unique tools that were executed."""
        return list(set(r.tool_name for r in self.execution_history))
    
    def get_total_tool_calls(self) -> int:
        """Get total number of tool calls made."""
        return len(self.execution_history)
    
    def get_execution_summary(self) -> Dict[str, Any]:
        """Get summary of all tool executions."""
        successful = sum(1 for r in self.execution_history if r.success)
        failed = sum(1 for r in self.execution_history if not r.success)
        total_time = sum(r.duration_ms for r in self.execution_history)
        
        return {
            "total_calls": len(self.execution_history),
            "successful": successful,
            "failed": failed,
            "total_time_ms": total_time,
            "tools_used": self.get_tools_used()
        }
    
    def clear_history(self):
        """Clear execution history."""
        self.execution_history = []


def has_tool_calls(response: Any) -> bool:
    """
    Check if LLM response contains tool calls.
    
    Args:
        response: LLM response (AIMessage)
        
    Returns:
        True if response has tool calls
    """
    if response is None:
        return False
    
    # Check for tool_calls attribute (LangChain standard)
    tool_calls = getattr(response, "tool_calls", None)
    if tool_calls:
        return len(tool_calls) > 0
    
    # Check for additional_kwargs (some models use this)
    additional_kwargs = getattr(response, "additional_kwargs", {})
    if additional_kwargs.get("tool_calls"):
        return True
    
    return False


def get_tool_calls(response: Any) -> List[Any]:
    """
    Extract tool calls from LLM response.
    
    Args:
        response: LLM response (AIMessage)
        
    Returns:
        List of tool calls
    """
    if response is None:
        return []
    
    # Standard LangChain tool_calls
    tool_calls = getattr(response, "tool_calls", None)
    if tool_calls:
        return list(tool_calls)
    
    # Fallback to additional_kwargs
    additional_kwargs = getattr(response, "additional_kwargs", {})
    if additional_kwargs.get("tool_calls"):
        return additional_kwargs["tool_calls"]
    
    return []
