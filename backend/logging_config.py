"""
Global Logging Module for AI Code Editor Backend

Provides centralized logging for all backend components:
- API requests/responses
- File operations
- Terminal operations
- Agent operations
- WebSocket connections

All logs are written to: backend/logs/
"""

import logging
import sys
import os
from pathlib import Path
from datetime import datetime
from functools import wraps
import time


# Create logs directory
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Log files
MAIN_LOG = LOGS_DIR / f"backend_{datetime.now().strftime('%Y%m%d')}.log"
ERROR_LOG = LOGS_DIR / f"errors_{datetime.now().strftime('%Y%m%d')}.log"


def setup_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """
    Setup a logger with file and console handlers.
    
    Args:
        name: Logger name (e.g., 'files', 'terminal', 'agent')
        level: Logging level
        
    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # File handler - detailed logs
    file_handler = logging.FileHandler(MAIN_LOG, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-15s | %(funcName)-20s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # Error file handler - errors only
    error_handler = logging.FileHandler(ERROR_LOG, encoding='utf-8')
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    
    # Console handler - important logs only
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(levelname)s: [%(name)s] %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console_handler)
    
    return logger


# Pre-configured loggers for each module
api_logger = setup_logger("api")
files_logger = setup_logger("files")
terminal_logger = setup_logger("terminal")
execute_logger = setup_logger("execute")
agent_logger = setup_logger("agent")
ws_logger = setup_logger("websocket")


def log_request(logger: logging.Logger):
    """
    Decorator to log API request/response.
    
    Usage:
        @log_request(api_logger)
        async def my_endpoint():
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            func_name = func.__name__
            
            # Log request
            logger.info(f"📥 Request: {func_name}")
            if kwargs:
                logger.debug(f"Parameters: {kwargs}")
            
            try:
                result = await func(*args, **kwargs)
                elapsed = (time.time() - start) * 1000
                logger.info(f"📤 Response: {func_name} ({elapsed:.0f}ms)")
                return result
                
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                logger.error(f"❌ Error in {func_name} ({elapsed:.0f}ms): {type(e).__name__}: {e}")
                raise
                
        return wrapper
    return decorator


def log_operation(logger: logging.Logger, operation: str):
    """
    Context manager for logging operations.
    
    Usage:
        with log_operation(files_logger, "read_file"):
            contents = read_file(path)
    """
    class OperationLogger:
        def __init__(self):
            self.start = None
            
        def __enter__(self):
            self.start = time.time()
            logger.debug(f"➡️ Starting: {operation}")
            return self
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            elapsed = (time.time() - self.start) * 1000
            if exc_type:
                logger.error(f"❌ Failed: {operation} ({elapsed:.0f}ms) - {exc_type.__name__}: {exc_val}")
            else:
                logger.debug(f"✅ Completed: {operation} ({elapsed:.0f}ms)")
            return False
            
    return OperationLogger()


# Convenience functions
def log_file_operation(operation: str, path: str, success: bool = True, error: str = None):
    """Log file operation."""
    if success:
        files_logger.info(f"📁 {operation}: {path}")
    else:
        files_logger.error(f"❌ {operation} failed: {path} - {error}")


def log_terminal_command(command: str, exit_code: int = None):
    """Log terminal command."""
    if exit_code is None:
        terminal_logger.info(f"💻 Running: {command[:100]}")
    else:
        status = "✅" if exit_code == 0 else "❌"
        terminal_logger.info(f"{status} Command finished (exit {exit_code}): {command[:50]}")


def log_websocket_event(event: str, client_id: str = None, data: str = None):
    """Log WebSocket event."""
    ws_logger.info(f"🔌 WS {event}" + (f" [{client_id}]" if client_id else ""))
    if data:
        ws_logger.debug(f"Data: {data[:200]}")


def log_agent_event(event: str, details: str = None):
    """Log agent event."""
    agent_logger.info(f"🤖 {event}")
    if details:
        agent_logger.debug(f"Details: {details}")


# Export all
__all__ = [
    "setup_logger",
    "log_request",
    "log_operation",
    "api_logger",
    "files_logger", 
    "terminal_logger",
    "execute_logger",
    "agent_logger",
    "ws_logger",
    "log_file_operation",
    "log_terminal_command",
    "log_websocket_event",
    "log_agent_event"
]
