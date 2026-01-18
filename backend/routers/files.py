"""
AI Code Editor - File Operations Router
Handles all file system operations
"""

import os
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

# Import logging
from logging_config import files_logger, log_file_operation

router = APIRouter()

# Store current workspace path (in-memory for now)
current_workspace: Optional[str] = None


# ============================================
# Pydantic Models
# ============================================

class OpenFolderRequest(BaseModel):
    path: str


class SaveFileRequest(BaseModel):
    path: str  # Relative path within workspace
    content: str


class CreateItemRequest(BaseModel):
    path: str  # Relative path within workspace
    is_folder: bool = False


class RenameRequest(BaseModel):
    old_path: str
    new_path: str


class FileTreeItem(BaseModel):
    name: str
    type: str  # "file" or "folder"
    path: str  # Relative path
    children: Optional[List["FileTreeItem"]] = None


# ============================================
# Helper Functions
# ============================================

def get_full_path(relative_path: str) -> Path:
    """Convert relative path to full path within workspace"""
    if not current_workspace:
        raise HTTPException(status_code=400, detail="No workspace folder opened")
    
    # Normalize and join paths
    full_path = Path(current_workspace) / relative_path
    
    # Security: Ensure the path is within workspace (prevent directory traversal)
    try:
        full_path.resolve().relative_to(Path(current_workspace).resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: Path outside workspace")
    
    return full_path


def build_file_tree(folder_path: Path, relative_base: str = "") -> List[dict]:
    """Recursively build file tree structure"""
    items = []
    
    try:
        for entry in sorted(folder_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            # Skip only: hidden files (except .venv), __pycache__, node_modules, .git
            if entry.name in ['__pycache__', 'node_modules', '.git']:
                continue
            # Skip hidden files, but allow .venv (not .env - that's for credentials)
            if entry.name.startswith('.') and entry.name != '.venv':
                continue
            
            relative_path = f"{relative_base}/{entry.name}" if relative_base else entry.name
            
            if entry.is_dir():
                items.append({
                    "name": entry.name,
                    "type": "folder",
                    "path": relative_path,
                    "children": build_file_tree(entry, relative_path)
                })
            else:
                items.append({
                    "name": entry.name,
                    "type": "file",
                    "path": relative_path
                })
    except PermissionError:
        pass  # Skip folders we can't access
    
    return items


# ============================================
# API Endpoints
# ============================================

@router.post("/open")
def open_folder(request: OpenFolderRequest):
    """
    Set the current workspace folder.
    User provides a folder path, and we validate it exists.
    """
    global current_workspace
    
    files_logger.info(f"📂 Opening folder: {request.path}")
    
    folder_path = Path(request.path)
    
    # Validate path exists
    if not folder_path.exists():
        files_logger.error(f"❌ Folder not found: {request.path}")
        raise HTTPException(status_code=404, detail=f"Folder not found: {request.path}")
    
    if not folder_path.is_dir():
        files_logger.error(f"❌ Not a folder: {request.path}")
        raise HTTPException(status_code=400, detail=f"Not a folder: {request.path}")
    
    current_workspace = str(folder_path.resolve())
    files_logger.info(f"✅ Workspace set: {current_workspace}")
    
    # Return the file tree
    file_tree = build_file_tree(folder_path)
    files_logger.debug(f"Built file tree with {len(file_tree)} root items")
    
    return {
        "success": True,
        "workspace": current_workspace,
        "tree": file_tree
    }


@router.get("/tree")
def get_file_tree():
    """
    Get the file tree of the current workspace.
    """
    if not current_workspace:
        raise HTTPException(status_code=400, detail="No workspace folder opened. Use /open first.")
    
    folder_path = Path(current_workspace)
    file_tree = build_file_tree(folder_path)
    
    return {
        "workspace": current_workspace,
        "tree": file_tree
    }


@router.get("/read")
def read_file(path: str = Query(..., description="Relative path to file")):
    """
    Read the content of a file.
    """
    full_path = get_full_path(path)
    
    if not full_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    
    if not full_path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {path}")
    
    try:
        # Try to read as text
        content = full_path.read_text(encoding='utf-8')
        files_logger.info(f"📖 Read file: {path} ({len(content)} chars)")
    except UnicodeDecodeError:
        files_logger.error(f"❌ Cannot read binary file: {path}")
        # Binary file - return empty or handle differently
        raise HTTPException(status_code=400, detail="Cannot read binary file")
    except Exception as e:
        files_logger.error(f"❌ Error reading file: {path} - {e}")
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")
    
    return {
        "path": path,
        "content": content,
        "name": full_path.name
    }


@router.post("/save")
def save_file(request: SaveFileRequest):
    """
    Save content to a file.
    """
    files_logger.info(f"💾 Saving file: {request.path}")
    full_path = get_full_path(request.path)
    
    try:
        # Create parent directories if they don't exist
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write the file
        full_path.write_text(request.content, encoding='utf-8')
        files_logger.info(f"✅ Saved file: {request.path} ({len(request.content)} chars)")
    except Exception as e:
        files_logger.error(f"❌ Error saving file: {request.path} - {e}")
        raise HTTPException(status_code=500, detail=f"Error saving file: {str(e)}")
    
    return {
        "success": True,
        "path": request.path,
        "message": f"File saved: {request.path}"
    }


@router.post("/create")
def create_item(request: CreateItemRequest):
    """
    Create a new file or folder.
    """
    full_path = get_full_path(request.path)
    
    if full_path.exists():
        raise HTTPException(status_code=409, detail=f"Already exists: {request.path}")
    
    try:
        if request.is_folder:
            full_path.mkdir(parents=True, exist_ok=True)
        else:
            # Create parent directories if needed
            full_path.parent.mkdir(parents=True, exist_ok=True)
            # Create empty file
            full_path.touch()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating: {str(e)}")
    
    return {
        "success": True,
        "path": request.path,
        "type": "folder" if request.is_folder else "file",
        "message": f"Created: {request.path}"
    }


@router.delete("/delete")
def delete_item(path: str = Query(..., description="Relative path to delete")):
    """
    Delete a file or folder.
    """
    full_path = get_full_path(path)
    
    if not full_path.exists():
        raise HTTPException(status_code=404, detail=f"Not found: {path}")
    
    try:
        if full_path.is_dir():
            # Remove directory and all contents
            import shutil
            shutil.rmtree(full_path)
        else:
            full_path.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting: {str(e)}")
    
    return {
        "success": True,
        "path": path,
        "message": f"Deleted: {path}"
    }


@router.put("/rename")
def rename_item(request: RenameRequest):
    """
    Rename a file or folder.
    """
    import shutil
    
    old_full_path = get_full_path(request.old_path)
    new_full_path = get_full_path(request.new_path)
    
    if not old_full_path.exists():
        raise HTTPException(status_code=404, detail=f"Not found: {request.old_path}")
    
    if new_full_path.exists():
        raise HTTPException(status_code=409, detail=f"Already exists: {request.new_path}")
    
    try:
        # Use shutil.move for better compatibility on Windows/OneDrive
        shutil.move(str(old_full_path), str(new_full_path))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error renaming: {str(e)}")
    
    return {
        "success": True,
        "old_path": request.old_path,
        "new_path": request.new_path,
        "message": f"Renamed: {request.old_path} → {request.new_path}"
    }


@router.get("/workspace")
def get_workspace():
    """
    Get current workspace info.
    """
    return {
        "workspace": current_workspace,
        "is_open": current_workspace is not None
    }
