"""
Terminal Integration Tools for AI Agent

LangChain tools for:
- Sending commands to terminal
- Getting terminal output
- Clearing terminal

Integrates with the existing WebSocket terminal.
"""

import asyncio
import subprocess
from typing import Dict, Any, Optional
from pathlib import Path
import os
from langchain_core.tools import tool

from .file_tools import get_workspace

# Import logging
from ..logger import agent_logger


# Store terminal output for retrieval
_terminal_output_buffer: list = []
_max_buffer_lines = 500


def _add_to_buffer(text: str):
    """Add text to output buffer."""
    global _terminal_output_buffer
    lines = text.split("\n")
    _terminal_output_buffer.extend(lines)
    # Keep only last N lines
    if len(_terminal_output_buffer) > _max_buffer_lines:
        _terminal_output_buffer = _terminal_output_buffer[-_max_buffer_lines:]


def _run_command_sync(command: str, cwd: str, timeout: int = 30) -> Dict[str, Any]:
    """
    Run a command synchronously and return result.
    
    This is a simplified version that runs commands directly.
    For full terminal integration, we'd connect to the WebSocket terminal.
    """
    agent_logger.info(f"💻 Running command: {command[:80]}...")
    
    try:
        # Build environment with venv if available
        env = os.environ.copy()
        
        # Check for venv in workspace
        workspace = Path(cwd)
        venv_active = False
        for venv_name in ['.venv', 'venv']:
            venv_path = workspace / venv_name / 'Scripts'
            if venv_path.exists():
                env['PATH'] = str(venv_path) + os.pathsep + env.get('PATH', '')
                env['VIRTUAL_ENV'] = str(workspace / venv_name)
                venv_active = True
                agent_logger.debug(f"Using venv: {venv_name}")
                break
        
        # Run command
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env
        )
        
        output = result.stdout + result.stderr
        _add_to_buffer(output)
        
        if result.returncode == 0:
            agent_logger.info(f"✅ Command success (exit 0): {command[:50]}")
        else:
            agent_logger.warning(f"⚠️ Command failed (exit {result.returncode}): {command[:50]}")
        
        return {
            "success": result.returncode == 0,
            "output": output,
            "exit_code": result.returncode,
            "command": command
        }
        
    except subprocess.TimeoutExpired:
        agent_logger.error(f"❌ Command timeout ({timeout}s): {command[:50]}")
        return {
            "success": False,
            "output": f"Command timed out after {timeout} seconds",
            "exit_code": -1,
            "command": command
        }
    except Exception as e:
        agent_logger.error(f"❌ Command error: {command[:50]} - {e}")
        return {
            "success": False,
            "output": str(e),
            "exit_code": -1,
            "command": command
        }


@tool
def run_terminal_command(command: str, timeout: int = 300) -> Dict[str, Any]:
    """
    Execute a shell command in the workspace.
    
    The command runs in the workspace directory with venv activated if available.
    
    Args:
        command: Shell command to execute (e.g., "pip install requests", "python main.py")
        timeout: Maximum time to wait for command (default: 300 seconds / 5 min)
        
    Returns:
        Dictionary with output, exit code, and success status
    """
    agent_logger.info(f"🔧 Tool: run_terminal_command({command[:50]}...)")
    workspace = get_workspace()
    
    # Safety: Block dangerous commands
    dangerous_patterns = [
        "rm -rf /",
        "format ",
        "del /s /q",
        ":(){:|:&};:",  # Fork bomb
        "shutdown",
        "reboot",
    ]
    
    cmd_lower = command.lower()
    for pattern in dangerous_patterns:
        if pattern in cmd_lower:
            agent_logger.error(f"🚫 BLOCKED dangerous command: {command}")
            return {
                "success": False,
                "output": f"Blocked: Potentially dangerous command",
                "exit_code": -1,
                "command": command
            }
    
    return _run_command_sync(command, str(workspace), timeout)


@tool
def run_python_file(file_path: str, args: str = "", timeout: int = 60) -> Dict[str, Any]:
    """
    Execute a Python file in the workspace.
    
    Args:
        file_path: Path to Python file (relative to workspace)
        args: Command line arguments to pass
        timeout: Maximum execution time (default: 60 seconds)
        
    Returns:
        Dictionary with output and execution result
    """
    workspace = get_workspace()
    full_path = workspace / file_path
    
    if not full_path.exists():
        return {
            "success": False,
            "output": f"File not found: {file_path}",
            "exit_code": -1
        }
    
    command = f'python -u "{file_path}" {args}'.strip()
    return _run_command_sync(command, str(workspace), timeout)


@tool
def run_pip_command(action: str, packages: str = "") -> Dict[str, Any]:
    """
    Run pip commands (install, uninstall, list, show).
    
    Args:
        action: pip action (install, uninstall, list, show, freeze)
        packages: Package names for install/uninstall/show
        
    Returns:
        Dictionary with pip output
    """
    valid_actions = ["install", "uninstall", "list", "show", "freeze"]
    
    if action not in valid_actions:
        return {
            "success": False,
            "output": f"Invalid action. Use one of: {valid_actions}",
            "exit_code": -1
        }
    
    if action in ["install", "uninstall", "show"] and not packages:
        return {
            "success": False,
            "output": f"Packages required for {action}",
            "exit_code": -1
        }
    
    command = f"pip {action}"
    if packages:
        command += f" {packages}"
    
    # Longer timeout for install (5 min)
    timeout = 300 if action == "install" else 120
    
    return _run_command_sync(command, str(get_workspace()), timeout)


@tool
def get_terminal_output(lines: int = 50) -> Dict[str, Any]:
    """
    Get recent terminal output from the buffer.
    
    Args:
        lines: Number of recent lines to return (default: 50)
        
    Returns:
        Dictionary with recent output
    """
    global _terminal_output_buffer
    
    recent = _terminal_output_buffer[-lines:] if _terminal_output_buffer else []
    output = "\n".join(recent)
    
    # Check for common error patterns
    has_error = any(
        pattern in output.lower() 
        for pattern in ["error:", "exception:", "traceback", "failed", "exit code: 1"]
    )
    
    return {
        "output": output,
        "lines": len(recent),
        "has_error": has_error
    }


@tool
def suggest_command(command: str, description: str = "") -> Dict[str, Any]:
    """
    Suggest a terminal command for the user to run manually.
    
    USE THIS BY DEFAULT instead of running commands directly.
    Only use run_terminal_command if the user EXPLICITLY asks you to execute/run something.
    
    Args:
        command: The shell command to suggest (e.g., "pip install flask", "npm run dev")
        description: Optional description of what the command does
        
    Returns:
        Dictionary with the suggested command formatted for user display
    """
    agent_logger.info(f"💡 Tool: suggest_command({command[:50]}...)")
    
    return {
        "success": True,
        "type": "suggested_command",
        "command": command,
        "description": description or f"Run this command in your terminal",
        "message": f"Please run this command in your terminal:\n```\n{command}\n```"
    }


@tool
def clear_terminal_buffer() -> Dict[str, Any]:
    """
    Clear the terminal output buffer.
    
    Returns:
        Success status
    """
    global _terminal_output_buffer
    _terminal_output_buffer = []
    
    return {"success": True, "message": "Terminal buffer cleared"}


@tool
def check_command_available(command: str) -> Dict[str, Any]:
    """
    Check if a command is available in the system.
    
    Args:
        command: Command name to check (e.g., "python", "node", "git")
        
    Returns:
        Dictionary with availability status
    """
    import shutil
    
    path = shutil.which(command)
    
    if path:
        return {
            "available": True,
            "command": command,
            "path": path
        }
    else:
        return {
            "available": False,
            "command": command,
            "message": f"Command '{command}' not found in PATH"
        }


# Export all terminal tools
TERMINAL_TOOLS = [
    suggest_command,  # Default: suggest commands for user to run
    run_terminal_command,  # Only use when user explicitly asks to run
    run_python_file,
    run_pip_command,
    get_terminal_output,
    clear_terminal_buffer,
    check_command_available
]
