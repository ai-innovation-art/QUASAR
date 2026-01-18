"""
File Operations Tools for AI Agent

LangChain tools for:
- Reading files
- Creating files
- Modifying files
- Deleting files
- Listing directories

All tools validate paths are within workspace.
"""

from typing import Optional, List, Dict, Any
from pathlib import Path
import os
from langchain_core.tools import tool

# Import logging
from ..logger import agent_logger


# Workspace will be set by the agent when initialized
_workspace_path: Optional[Path] = None


def set_workspace(path: str):
    """Set the current workspace path."""
    global _workspace_path
    _workspace_path = Path(path)
    agent_logger.info(f"🔧 Tool workspace set: {path}")


def get_workspace() -> Path:
    """Get current workspace path."""
    global _workspace_path
    if _workspace_path is None:
        # Default to current directory if not set
        return Path(os.getcwd())
    return _workspace_path


def validate_path(path: str) -> tuple[bool, str, Optional[Path]]:
    """
    Validate that path is safe and within workspace.
    
    Returns:
        (is_valid, error_message, resolved_path)
    """
    workspace = get_workspace()
    
    # Check for path traversal
    if ".." in path:
        agent_logger.warning(f"⚠️ Path traversal attempt: {path}")
        return (False, "Path traversal (..) not allowed", None)
    
    # Resolve full path
    if Path(path).is_absolute():
        full_path = Path(path)
    else:
        full_path = workspace / path
    
    full_path = full_path.resolve()
    
    # Ensure path is within workspace
    try:
        full_path.relative_to(workspace)
    except ValueError:
        agent_logger.warning(f"⚠️ Path outside workspace: {path}")
        return (False, f"Path must be within workspace: {workspace}", None)
    
    return (True, "", full_path)


def detect_language(file_path: str) -> str:
    """Detect programming language from file extension."""
    ext_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "jsx",
        ".tsx": "tsx",
        ".html": "html",
        ".css": "css",
        ".json": "json",
        ".md": "markdown",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".xml": "xml",
        ".sql": "sql",
        ".sh": "bash",
        ".ps1": "powershell",
        ".java": "java",
        ".cpp": "cpp",
        ".c": "c",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".php": "php",
    }
    ext = Path(file_path).suffix.lower()
    return ext_map.get(ext, "text")


@tool
def read_file(path: str) -> Dict[str, Any]:
    """
    Read the contents of a file in the workspace.
    
    Args:
        path: File path relative to workspace (e.g., "src/main.py")
        
    Returns:
        Dictionary with content, language, and line count
    """
    agent_logger.info(f"🔧 Tool: read_file({path})")
    
    is_valid, error, full_path = validate_path(path)
    if not is_valid:
        agent_logger.error(f"❌ read_file failed: {error}")
        return {"error": error}
    
    if not full_path.exists():
        agent_logger.error(f"❌ File not found: {path}")
        return {"error": f"File not found: {path}"}
    
    if not full_path.is_file():
        agent_logger.error(f"❌ Not a file: {path}")
        return {"error": f"Not a file: {path}"}
    
    try:
        content = full_path.read_text(encoding="utf-8")
        agent_logger.info(f"✅ read_file success: {path} ({len(content)} chars, {len(content.split(chr(10)))} lines)")
        return {
            "content": content,
            "path": path,
            "language": detect_language(path),
            "lines": len(content.split("\n")),
            "size_bytes": len(content.encode("utf-8"))
        }
    except Exception as e:
        agent_logger.error(f"❌ read_file error: {path} - {e}")
        return {"error": f"Failed to read file: {str(e)}"}


@tool
def create_file(path: str, content: str, overwrite: bool = False) -> Dict[str, Any]:
    """
    Create a new file with the given content.
    
    Args:
        path: File path relative to workspace
        content: File content to write
        overwrite: If True, overwrite existing file
        
    Returns:
        Dictionary with success status and file info
    """
    agent_logger.info(f"🔧 Tool: create_file({path}, overwrite={overwrite})")
    
    is_valid, error, full_path = validate_path(path)
    if not is_valid:
        agent_logger.error(f"❌ create_file failed: {error}")
        return {"error": error}
    
    if full_path.exists() and not overwrite:
        agent_logger.warning(f"⚠️ File exists, overwrite=False: {path}")
        return {"error": f"File already exists: {path}. Set overwrite=True to replace."}
    
    try:
        # Create parent directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write file
        full_path.write_text(content, encoding="utf-8")
        
        agent_logger.info(f"✅ create_file success: {path} ({len(content)} chars)")
        return {
            "success": True,
            "path": path,
            "language": detect_language(path),
            "lines": len(content.split("\n")),
            "size_bytes": len(content.encode("utf-8"))
        }
    except Exception as e:
        agent_logger.error(f"❌ create_file error: {path} - {e}")
        return {"error": f"Failed to create file: {str(e)}"}


@tool
def modify_file(path: str, content: str, create_backup: bool = True) -> Dict[str, Any]:
    """
    Modify an existing file with new content.
    
    Args:
        path: File path relative to workspace
        content: New file content
        create_backup: If True, create .bak backup before modifying
        
    Returns:
        Dictionary with success status
    """
    is_valid, error, full_path = validate_path(path)
    if not is_valid:
        return {"error": error}
    
    if not full_path.exists():
        return {"error": f"File not found: {path}"}
    
    try:
        # Create backup if requested
        backup_path = None
        if create_backup:
            backup_path = full_path.with_suffix(full_path.suffix + ".bak")
            backup_path.write_text(full_path.read_text(encoding="utf-8"), encoding="utf-8")
        
        # Write new content
        full_path.write_text(content, encoding="utf-8")
        
        result = {
            "success": True,
            "path": path,
            "lines": len(content.split("\n")),
            "size_bytes": len(content.encode("utf-8"))
        }
        
        if backup_path:
            result["backup_path"] = str(backup_path.relative_to(get_workspace()))
        
        return result
    except Exception as e:
        return {"error": f"Failed to modify file: {str(e)}"}


@tool
def delete_file(path: str, recursive: bool = False) -> Dict[str, Any]:
    """
    Delete a file or directory.
    
    Args:
        path: File/directory path relative to workspace
        recursive: If True, delete directories recursively
        
    Returns:
        Dictionary with success status
    """
    is_valid, error, full_path = validate_path(path)
    if not is_valid:
        return {"error": error}
    
    if not full_path.exists():
        return {"error": f"Path not found: {path}"}
    
    try:
        if full_path.is_file():
            full_path.unlink()
            return {"success": True, "deleted": path, "type": "file"}
        elif full_path.is_dir():
            if recursive:
                import shutil
                shutil.rmtree(full_path)
                return {"success": True, "deleted": path, "type": "directory"}
            else:
                # Check if directory is empty
                if any(full_path.iterdir()):
                    return {"error": f"Directory not empty: {path}. Set recursive=True to delete."}
                full_path.rmdir()
                return {"success": True, "deleted": path, "type": "directory"}
    except Exception as e:
        return {"error": f"Failed to delete: {str(e)}"}


@tool
def list_files(path: str = ".", recursive: bool = False) -> Dict[str, Any]:
    """
    List files and directories in a path.
    
    Args:
        path: Directory path relative to workspace (default: workspace root)
        recursive: If True, list recursively
        
    Returns:
        Dictionary with files and directories
    """
    is_valid, error, full_path = validate_path(path)
    if not is_valid:
        return {"error": error}
    
    if not full_path.exists():
        return {"error": f"Path not found: {path}"}
    
    if not full_path.is_dir():
        return {"error": f"Not a directory: {path}"}
    
    try:
        files = []
        directories = []
        
        # Skip these directories
        skip_dirs = {"__pycache__", "node_modules", ".git", ".venv", "venv"}
        
        if recursive:
            for item in full_path.rglob("*"):
                # Skip hidden and excluded directories
                if any(part in skip_dirs or part.startswith(".") for part in item.parts):
                    continue
                
                rel_path = str(item.relative_to(full_path))
                
                if item.is_file():
                    files.append({
                        "path": rel_path,
                        "language": detect_language(rel_path),
                        "size": item.stat().st_size
                    })
                elif item.is_dir():
                    directories.append(rel_path)
        else:
            for item in full_path.iterdir():
                # Skip hidden files and excluded directories
                if item.name.startswith(".") or item.name in skip_dirs:
                    continue
                
                if item.is_file():
                    files.append({
                        "path": item.name,
                        "language": detect_language(item.name),
                        "size": item.stat().st_size
                    })
                elif item.is_dir():
                    directories.append(item.name)
        
        return {
            "path": path,
            "files": files,
            "directories": sorted(directories),
            "total_files": len(files),
            "total_directories": len(directories)
        }
    except Exception as e:
        return {"error": f"Failed to list files: {str(e)}"}


@tool
def search_files(query: str, file_pattern: str = "*.py", path: str = ".") -> Dict[str, Any]:
    """
    Search for text pattern in files.
    
    Args:
        query: Text to search for
        file_pattern: Glob pattern for files to search (e.g., "*.py")
        path: Directory to search in
        
    Returns:
        Dictionary with matches
    """
    is_valid, error, full_path = validate_path(path)
    if not is_valid:
        return {"error": error}
    
    if not full_path.exists():
        return {"error": f"Path not found: {path}"}
    
    try:
        matches = []
        
        for file in full_path.rglob(file_pattern):
            # Skip excluded directories
            if any(part in ["__pycache__", "node_modules", ".git", ".venv"] for part in file.parts):
                continue
            
            if not file.is_file():
                continue
            
            try:
                content = file.read_text(encoding="utf-8")
                for line_num, line in enumerate(content.split("\n"), 1):
                    if query in line:
                        rel_path = str(file.relative_to(full_path))
                        matches.append({
                            "file": rel_path,
                            "line": line_num,
                            "content": line.strip()[:200]  # Truncate long lines
                        })
            except:
                continue
        
        return {
            "query": query,
            "pattern": file_pattern,
            "matches": matches[:50],  # Limit results
            "total_matches": len(matches)
        }
    except Exception as e:
        return {"error": f"Search failed: {str(e)}"}


# Export all file tools
FILE_TOOLS = [
    read_file,
    create_file,
    modify_file,
    delete_file,
    list_files,
    search_files
]
