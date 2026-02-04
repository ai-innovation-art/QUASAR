"""
Global Logger for AI Agent

Centralized logging with file output and console output.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime


# Create logs directory
LOGS_DIR = Path(__file__).parent.parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Log file path
LOG_FILE = LOGS_DIR / f"agent_{datetime.now().strftime('%Y%m%d')}.log"


def setup_logger(name: str = "agent") -> logging.Logger:
    """
    Setup logger with file and console handlers.
    
    Args:
        name: Logger name
        
    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.DEBUG)
    
    # File handler - detailed logs
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # Console handler - silent (CRITICAL only) to keep CLI clean
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.CRITICAL)
    console_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


# Global logger instance
agent_logger = setup_logger("agent")


def log_model_call(provider: str, model_name: str, task_type: str = None):
    """Log when a model is being called."""
    agent_logger.info(f"🤖 Model Call: {provider}/{model_name}" + (f" for {task_type}" if task_type else ""))


def log_model_response(provider: str, model_name: str, response_length: int, success: bool = True):
    """Log model response."""
    status = "✅ Success" if success else "❌ Failed"
    agent_logger.info(f"{status}: {provider}/{model_name} returned {response_length} chars")


def log_classification(task_type: str, confidence: float, reasoning: str):
    """Log task classification result."""
    agent_logger.info(f"📋 Classified as: {task_type} (confidence: {confidence:.2f})")
    agent_logger.debug(f"Reasoning: {reasoning}")


def log_error(error_type: str, error: Exception, context: str = None):
    """Log an error with context."""
    agent_logger.error(f"❌ {error_type}: {str(error)}")
    if context:
        agent_logger.debug(f"Context: {context}")
    agent_logger.exception(error)


def log_api_request(endpoint: str, params: dict = None):
    """Log API request."""
    agent_logger.info(f"📥 API Request: {endpoint}")
    if params:
        agent_logger.debug(f"Parameters: {params}")


def log_api_response(endpoint: str, success: bool, response_summary: str = None):
    """Log API response."""
    status = "✅ Success" if success else "❌ Failed"
    agent_logger.info(f"📤 API Response: {endpoint} - {status}")
    if response_summary:
        agent_logger.debug(f"Summary: {response_summary}")


# ============================================
# Tool Execution Logging (Agentic Loop)
# ============================================

def log_tool_call(tool_name: str, args: dict = None):
    """Log when a tool is being called."""
    agent_logger.info(f"🔧 Tool Call: {tool_name}")
    if args:
        # Truncate long args for readability
        args_str = str(args)[:200]
        agent_logger.debug(f"   Args: {args_str}")


def log_tool_result(tool_name: str, success: bool, result_summary: str = None, duration_ms: float = 0):
    """Log tool execution result."""
    status = "✅" if success else "❌"
    duration_str = f" ({duration_ms:.1f}ms)" if duration_ms > 0 else ""
    agent_logger.info(f"   {status} Tool {tool_name} completed{duration_str}")
    if result_summary:
        agent_logger.debug(f"   Result: {result_summary[:200]}...")


def log_tool_error(tool_name: str, error: str):
    """Log tool execution error."""
    agent_logger.error(f"   ❌ Tool {tool_name} error: {error}")


def log_agentic_iteration(iteration: int, total_tool_calls: int, has_more_calls: bool):
    """Log agentic loop iteration."""
    if has_more_calls:
        agent_logger.info(f"🔄 Agentic Loop - Iteration {iteration}: {total_tool_calls} tool calls, continuing...")
    else:
        agent_logger.info(f"✅ Agentic Loop - Iteration {iteration}: Complete ({total_tool_calls} total tool calls)")


def log_agentic_start(task_type: str, tools_count: int):
    """Log start of agentic execution."""
    agent_logger.info(f"🚀 Starting agentic execution for '{task_type}' with {tools_count} tools available")


def log_agentic_complete(iterations: int, tools_used: list, total_calls: int):
    """Log completion of agentic execution."""
    tools_summary = ", ".join(tools_used) if tools_used else "none"
    agent_logger.info(f"✅ Agentic execution complete: {iterations} iterations, {total_calls} tool calls")
    agent_logger.debug(f"   Tools used: {tools_summary}")


def log_agentic_max_iterations(max_iterations: int, current_iteration: int):
    """Log when max iterations reached."""
    agent_logger.warning(f"⚠️ Max iterations ({max_iterations}) reached at iteration {current_iteration}. Stopping loop.")

