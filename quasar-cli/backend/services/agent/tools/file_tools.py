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
    
    For large files (>2000 lines), returns metadata only and suggests using read_file_chunk.
    
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
        lines = content.split("\n")
        line_count = len(lines)
        size_bytes = len(content.encode("utf-8"))
        
        # Check if file is too large
        MAX_LINES = 2000
        if line_count > MAX_LINES:
            agent_logger.warning(f"⚠️ Large file detected: {path} ({line_count} lines). Returning metadata only.")
            return {
                "path": path,
                "language": detect_language(path),
                "lines": line_count,
                "size_bytes": size_bytes,
                "is_large_file": True,
                "max_lines_shown": 0,
                "hint": f"File has {line_count} lines. Use read_file_chunk(path, start_line, end_line) to read specific sections. Recommended chunk size: 500 lines."
            }
        
        agent_logger.info(f"✅ read_file success: {path} ({len(content)} chars, {line_count} lines)")
        return {
            "content": content,
            "path": path,
            "language": detect_language(path),
            "lines": line_count,
            "size_bytes": size_bytes
        }
    except Exception as e:
        agent_logger.error(f"❌ read_file error: {path} - {e}")
        return {"error": f"Failed to read file: {str(e)}"}


@tool
def read_file_chunk(path: str, start_line: int = 1, end_line: int = 500) -> Dict[str, Any]:
    """
    Read a specific chunk of a file by line numbers.
    
    Use this for large files that exceed the context limit.
    
    Args:
        path: File path relative to workspace
        start_line: Starting line number (1-indexed, inclusive)
        end_line: Ending line number (1-indexed, inclusive)
        
    Returns:
        Dictionary with chunk content, line range, and total lines
    """
    agent_logger.info(f"🔧 Tool: read_file_chunk({path}, lines {start_line}-{end_line})")
    
    is_valid, error, full_path = validate_path(path)
    if not is_valid:
        agent_logger.error(f"❌ read_file_chunk failed: {error}")
        return {"error": error}
    
    if not full_path.exists():
        agent_logger.error(f"❌ File not found: {path}")
        return {"error": f"File not found: {path}"}
    
    if not full_path.is_file():
        agent_logger.error(f"❌ Not a file: {path}")
        return {"error": f"Not a file: {path}"}
    
    try:
        content = full_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        total_lines = len(lines)
        
        # Validate line range
        if start_line < 1:
            start_line = 1
        if end_line > total_lines:
            end_line = total_lines
        if start_line > end_line:
            return {"error": f"Invalid range: start_line ({start_line}) > end_line ({end_line})"}
        
        # Extract chunk (convert to 0-indexed)
        chunk_lines = lines[start_line - 1:end_line]
        chunk_content = "\n".join(chunk_lines)
        
        agent_logger.info(f"✅ read_file_chunk success: {path} lines {start_line}-{end_line} ({len(chunk_lines)} lines)")
        return {
            "content": chunk_content,
            "path": path,
            "language": detect_language(path),
            "start_line": start_line,
            "end_line": end_line,
            "lines_in_chunk": len(chunk_lines),
            "total_lines": total_lines,
            "has_more_before": start_line > 1,
            "has_more_after": end_line < total_lines
        }
    except Exception as e:
        agent_logger.error(f"❌ read_file_chunk error: {path} - {e}")
        return {"error": f"Failed to read file chunk: {str(e)}"}



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
        return {
            "error": f"File already exists: {path}",
            "file_exists": True,
            "path": path,
            "hint": "Use overwrite=True to replace the existing file, or choose a different filename."
        }
    
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
def modify_file(path: str, content: str, create_backup: bool = False) -> Dict[str, Any]:
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
def patch_file(path: str, find_text: str, replace_text: str, occurrence: int = 1) -> Dict[str, Any]:
    """
    Patch a file by finding and replacing specific text.
    
    Use this for TARGETED edits when you only need to change a specific section
    without rewriting the entire file. For example, updating a checkbox from [ ] to [x].
    
    Args:
        path: File path relative to workspace
        find_text: Exact text to find (including whitespace and newlines)
        replace_text: Text to replace it with
        occurrence: Which occurrence to replace (1=first, 0=all occurrences)
        
    Returns:
        Dictionary with success status and number of replacements made
    """
    agent_logger.info(f"🔧 Tool: patch_file({path}, find={find_text[:50]}..., replace={replace_text[:50]}...)")
    
    is_valid, error, full_path = validate_path(path)
    if not is_valid:
        return {"error": error}
    
    if not full_path.exists():
        return {"error": f"File not found: {path}"}
    
    try:
        content = full_path.read_text(encoding="utf-8")
        
        # Check if the text exists
        if find_text not in content:
            return {
                "error": f"Text not found in file",
                "hint": "The exact text was not found. Check for extra spaces, newlines, or typos."
            }
        
        # Count occurrences
        count = content.count(find_text)
        
        if occurrence == 0:
            # Replace all occurrences
            new_content = content.replace(find_text, replace_text)
            replaced_count = count
        else:
            # Replace specific occurrence
            if occurrence > count:
                return {"error": f"Only {count} occurrence(s) found, requested occurrence {occurrence}"}
            
            # Find the nth occurrence and replace it
            idx = -1
            for i in range(occurrence):
                idx = content.find(find_text, idx + 1)
            
            new_content = content[:idx] + replace_text + content[idx + len(find_text):]
            replaced_count = 1
        
        # Write back
        full_path.write_text(new_content, encoding="utf-8")
        
        agent_logger.info(f"✅ patch_file success: {path} ({replaced_count} replacement(s))")
        return {
            "success": True,
            "path": path,
            "replacements": replaced_count,
            "occurrences_found": count
        }
        
    except Exception as e:
        agent_logger.error(f"❌ patch_file error: {path} - {e}")
        return {"error": f"Failed to patch file: {str(e)}"}


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
def move_file(source: str, destination: str) -> Dict[str, Any]:
    """
    Move or rename a file/directory.
    
    Args:
        source: Source path relative to workspace
        destination: Destination path relative to workspace
        
    Returns:
        Dictionary with success status
    """
    agent_logger.info(f"🔧 Tool: move_file({source} -> {destination})")
    
    # Validate source
    is_valid, error, source_path = validate_path(source)
    if not is_valid:
        return {"error": f"Source: {error}"}
    
    if not source_path.exists():
        return {"error": f"Source not found: {source}"}
    
    # Validate destination
    is_valid, error, dest_path = validate_path(destination)
    if not is_valid:
        return {"error": f"Destination: {error}"}
    
    try:
        import shutil
        
        # Create destination directory if needed
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Move the file/directory
        shutil.move(str(source_path), str(dest_path))
        
        agent_logger.info(f"✅ Moved: {source} -> {destination}")
        return {
            "success": True,
            "source": source,
            "destination": destination,
            "message": f"Moved {source} to {destination}"
        }
    except Exception as e:
        agent_logger.error(f"❌ Move failed: {e}")
        return {"error": f"Failed to move: {str(e)}"}


@tool
def list_files(path: str = ".", recursive: bool = False) -> Dict[str, Any]:
    """
    List files and directories in a path.
    
    Args:
        path: Directory path relative to workspace (default: workspace root)
        recursive: If True, list recursively (limited to 100 files, 50 dirs)
        
    Returns:
        Dictionary with files and directories
    """
    # Limits to prevent context overflow
    MAX_FILES = 100
    MAX_DIRS = 50
    
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
        files_truncated = False
        dirs_truncated = False
        
        if recursive:
            for item in full_path.rglob("*"):
                rel_path = str(item.relative_to(full_path))
                
                # Skip common ignored directories
                if any(part in [".git", "__pycache__", "node_modules", ".venv", "venv"] for part in item.parts):
                    continue
                
                if item.is_file():
                    if len(files) < MAX_FILES:
                        files.append({
                            "path": rel_path,
                            "language": detect_language(rel_path),
                            "size": item.stat().st_size
                        })
                    else:
                        files_truncated = True
                elif item.is_dir():
                    if len(directories) < MAX_DIRS:
                        directories.append(rel_path)
                    else:
                        dirs_truncated = True
        else:
            for item in full_path.iterdir():
                if item.is_file():
                    if len(files) < MAX_FILES:
                        files.append({
                            "path": item.name,
                            "language": detect_language(item.name),
                            "size": item.stat().st_size
                        })
                    else:
                        files_truncated = True
                elif item.is_dir():
                    if len(directories) < MAX_DIRS:
                        directories.append(item.name)
                    else:
                        dirs_truncated = True
        
        result = {
            "path": path,
            "files": files,
            "directories": sorted(directories),
            "total_files": len(files),
            "total_directories": len(directories)
        }
        
        # Add hints if truncated
        if files_truncated or dirs_truncated:
            result["truncated"] = True
            result["hint"] = f"Results limited to {MAX_FILES} files and {MAX_DIRS} directories. Use a more specific path to see more."
        
        return result
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
                            "content": line.strip()  # Show full line
                        })
            except:
                continue
        
        return {
            "query": query,
            "pattern": file_pattern,
            "matches": matches,  # Limit results removed
            "total_matches": len(matches)
        }
    except Exception as e:
        return {"error": f"Search failed: {str(e)}"}


@tool
def grep_search(query: str, path: str = ".", include_pattern: str = None) -> Dict[str, Any]:
    """
    High-performance text search using native system tools (findstr on Windows).
    
    Args:
        query: Text pattern to search for
        path: Directory to search in (default: workspace root)
        include_pattern: Optional file pattern (e.g., "*.py")
        
    Returns:
        Dictionary with match results
    """
    is_valid, error, full_path = validate_path(path)
    if not is_valid:
        return {"error": error}
        
    import subprocess
    import platform
    
    matches = []
    
    try:
        if platform.system() == "Windows":
            # Use findstr for extreme speed on Windows
            # /S = recursive, /N = line number, /I = case insensitive (optional, keeping it case-sensitive for now)
            cmd = ["findstr", "/S", "/N", query]
            if include_pattern:
                cmd.append(include_pattern)
            else:
                cmd.append("*.*")
                
            process = subprocess.run(cmd, cwd=full_path, capture_output=True, text=True, encoding="cp437", errors="ignore")
            output = process.stdout
            
            for line in output.splitlines():
                if ":" in line:
                    try:
                        # findstr format: path:line:content
                        parts = line.split(":", 2)
                        if len(parts) >= 3:
                            rel_path = parts[0]
                            # Filter out ignored dirs
                            if any(d in rel_path for d in [".git", "node_modules", "__pycache__", ".editor"]):
                                continue
                                
                            matches.append({
                                "file": rel_path,
                                "line": int(parts[1]),
                                "content": parts[2].strip()
                            })
                    except:
                        continue
        else:
            # Fallback to existing search_files logic for non-windows if rg not found
            return search_files(query, include_pattern or "*", path)
            
        return {
            "query": query,
            "matches": matches[:100], # Limit to 100 for context safety
            "total_matches": len(matches),
            "truncated": len(matches) > 100
        }
    except Exception as e:
        return {"error": f"Grep search failed: {str(e)}"}


@tool
def list_tree_fast(path: str = ".", max_depth: int = 3) -> Dict[str, Any]:
    """
    Highly optimized recursive file listing using os.scandir.
    Use this for getting a quick overview of the project structure.
    
    Args:
        path: Directory to list
        max_depth: Maximum recursion depth
        
    Returns:
        Flattened list of all files in a tree-like format
    """
    is_valid, error, full_path = validate_path(path)
    if not is_valid:
        return {"error": error}
        
    import os
    
    tree = []
    
    def _scan(dir_path: Path, current_depth: int):
        if current_depth > max_depth:
            return
            
        try:
            with os.scandir(dir_path) as it:
                for entry in it:
                    # Skip ignored dirs
                    if entry.is_dir():
                        if entry.name in [".git", "node_modules", "__pycache__", ".editor", "venv", ".venv"]:
                            continue
                        rel_path = str(Path(entry.path).relative_to(full_path))
                        tree.append(f"📁 {rel_path}/")
                        _scan(entry.path, current_depth + 1)
                    else:
                        rel_path = str(Path(entry.path).relative_to(full_path))
                        tree.append(f"📄 {rel_path}")
        except (PermissionError, FileNotFoundError):
            pass
            
    _scan(full_path, 1)
    
    return {
        "path": path,
        "tree": tree[:500], # Limit output size
        "count": len(tree),
        "truncated": len(tree) > 500
    }


# Export all file tools
FILE_TOOLS = [
    read_file,
    read_file_chunk,
    create_file,
    modify_file,
    patch_file,
    delete_file,
    move_file,
    list_files,
    search_files,
    grep_search,
    list_tree_fast
]
