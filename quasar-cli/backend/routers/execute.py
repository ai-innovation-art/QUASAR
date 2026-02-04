"""
AI Code Editor - Code Execution Router
Handles running Python/Node.js code
"""

import subprocess
import os
import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Import logging
from logging_config import execute_logger

router = APIRouter()

# Import the files module to access current_workspace dynamically
from routers import files as files_router


class ExecuteRequest(BaseModel):
    """Request model for code execution"""
    file_path: str  # Relative path to file within workspace
    

class ExecuteResponse(BaseModel):
    """Response model for code execution"""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    file_path: str
    language: str


def get_workspace():
    """Get current workspace from files router"""
    if not files_router.current_workspace:
        raise HTTPException(status_code=400, detail="No workspace folder opened. Please open a folder first.")
    return files_router.current_workspace


def get_full_path(relative_path: str) -> Path:
    """Convert relative path to full path within workspace"""
    workspace = get_workspace()
    
    full_path = Path(workspace) / relative_path
    
    # Security: Ensure path is within workspace
    try:
        full_path.resolve().relative_to(Path(workspace).resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: Path outside workspace")
    
    return full_path


def detect_language(file_path: str) -> str:
    """Detect language from file extension"""
    ext = Path(file_path).suffix.lower()
    language_map = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.sh': 'shell',
        '.bash': 'shell'
    }
    return language_map.get(ext, 'unknown')


@router.post("/python")
def execute_python(request: ExecuteRequest) -> ExecuteResponse:
    """
    Execute a Python file.
    Returns stdout, stderr, and exit code.
    """
    full_path = get_full_path(request.file_path)
    
    if not full_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")
    
    if not full_path.suffix.lower() == '.py':
        raise HTTPException(status_code=400, detail="Not a Python file")
    
    try:
        # Run Python script
        result = subprocess.run(
            [sys.executable, str(full_path)],
            capture_output=True,
            text=True,
            timeout=30,  # 30 second timeout
            cwd=get_workspace()  # Run from workspace directory
        )
        
        return ExecuteResponse(
            success=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
            file_path=request.file_path,
            language='python'
        )
        
    except subprocess.TimeoutExpired:
        return ExecuteResponse(
            success=False,
            stdout='',
            stderr='Execution timed out (30 seconds limit)',
            exit_code=-1,
            file_path=request.file_path,
            language='python'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution error: {str(e)}")


@router.post("/node")
def execute_node(request: ExecuteRequest) -> ExecuteResponse:
    """
    Execute a Node.js file.
    Returns stdout, stderr, and exit code.
    """
    full_path = get_full_path(request.file_path)
    
    if not full_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")
    
    if not full_path.suffix.lower() == '.js':
        raise HTTPException(status_code=400, detail="Not a JavaScript file")
    
    try:
        # Run Node.js script
        result = subprocess.run(
            ['node', str(full_path)],
            capture_output=True,
            text=True,
            timeout=30,  # 30 second timeout
            cwd=get_workspace()  # Run from workspace directory
        )
        
        return ExecuteResponse(
            success=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
            file_path=request.file_path,
            language='javascript'
        )
        
    except subprocess.TimeoutExpired:
        return ExecuteResponse(
            success=False,
            stdout='',
            stderr='Execution timed out (30 seconds limit)',
            exit_code=-1,
            file_path=request.file_path,
            language='javascript'
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Node.js is not installed or not in PATH")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution error: {str(e)}")


@router.post("/auto")
def execute_auto(request: ExecuteRequest) -> ExecuteResponse:
    """
    Auto-detect language and execute file.
    Supports Python (.py) and Node.js (.js)
    """
    full_path = get_full_path(request.file_path)
    
    if not full_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")
    
    language = detect_language(request.file_path)
    
    if language == 'python':
        return execute_python(request)
    elif language == 'javascript':
        return execute_node(request)
    else:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file type. Supported: .py (Python), .js (Node.js)"
        )
