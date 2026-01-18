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
    
    # Console handler - important logs only
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
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
