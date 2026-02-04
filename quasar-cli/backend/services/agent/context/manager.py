"""
Context Manager for AI Agent

Manages hierarchical context:
- Permanent: User preferences, workspace info
- Task: Current file, selection, errors
- Summary: Compressed conversation history
- Session: Files created, actions taken

Implements token budgeting per task type.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging

# Setup logger
logger = logging.getLogger("context")


@dataclass
class PermanentContext:
    """Always-included context (workspace, preferences)."""
    workspace_path: str = ""
    project_type: str = "unknown"  # web_app, cli, library, etc.
    language: str = "python"
    user_preferences: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskContext:
    """Context for current task."""
    current_file: Optional[str] = None
    file_content: Optional[str] = None
    selected_code: Optional[str] = None
    error_message: Optional[str] = None
    terminal_output: Optional[str] = None
    file_language: str = "text"


@dataclass
class ConversationMessage:
    """Single conversation message."""
    role: str  # user, assistant
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    task_type: Optional[str] = None


@dataclass 
class SessionMemory:
    """Session-level memory (files created, errors seen)."""
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    errors_encountered: List[str] = field(default_factory=list)
    commands_run: List[str] = field(default_factory=list)
    

# Token budgets per task type (from agent_orchestration.md)
TOKEN_BUDGETS = {
    "chat": {"permanent": 100, "task": 200, "summary": 100, "total": 400},
    "code_explain_simple": {"permanent": 100, "task": 1000, "summary": 200, "total": 1300},
    "code_explain_complex": {"permanent": 100, "task": 2000, "summary": 400, "total": 2500},
    "code_generation": {"permanent": 100, "task": 1500, "summary": 300, "total": 1900},
    "code_generation_multi": {"permanent": 100, "task": 3000, "summary": 500, "total": 3600},
    "bug_fixing": {"permanent": 100, "task": 1500, "summary": 300, "total": 1900},
    "refactor": {"permanent": 100, "task": 2000, "summary": 400, "total": 2500},
    "architecture": {"permanent": 100, "task": 2000, "summary": 400, "total": 2500},
    "test_generation": {"permanent": 100, "task": 1500, "summary": 300, "total": 1900},
    "documentation": {"permanent": 100, "task": 1000, "summary": 200, "total": 1300},
}


class ContextManager:
    """
    Manages context for AI agent conversations.
    
    Provides hierarchical context with token budgeting.
    """
    
    def __init__(self):
        self.permanent = PermanentContext()
        self.task = TaskContext()
        self.session = SessionMemory()
        self.conversation_history: List[ConversationMessage] = []
        self.conversation_summary: str = ""
        self.summarize_threshold = 5  # Summarize every N messages
        logger.info("📋 ContextManager initialized")
    
    def set_workspace(self, path: str, project_type: str = "unknown"):
        """Set workspace info."""
        self.permanent.workspace_path = path
        self.permanent.project_type = project_type
        logger.info(f"📁 Workspace set: {path}")
    
    def set_task_context(
        self,
        current_file: str = None,
        file_content: str = None,
        selected_code: str = None,
        error_message: str = None,
        terminal_output: str = None
    ):
        """Update task context."""
        self.task = TaskContext(
            current_file=current_file,
            file_content=file_content,
            selected_code=selected_code,
            error_message=error_message,
            terminal_output=terminal_output,
            file_language=self._detect_language(current_file) if current_file else "text"
        )
    
    def add_message(self, role: str, content: str, task_type: str = None):
        """Add message to conversation history."""
        msg = ConversationMessage(
            role=role,
            content=content,
            task_type=task_type
        )
        self.conversation_history.append(msg)
        
        # Check if we need to summarize
        if len(self.conversation_history) >= self.summarize_threshold * 2:
            self._trigger_summarization()
    
    def record_file_created(self, path: str):
        """Record file creation in session."""
        if path not in self.session.files_created:
            self.session.files_created.append(path)
    
    def record_file_modified(self, path: str):
        """Record file modification in session."""
        if path not in self.session.files_modified:
            self.session.files_modified.append(path)
    
    def record_error(self, error: str):
        """Record error in session."""
        self.session.errors_encountered.append(error)  # Full error
    
    def record_command(self, command: str):
        """Record command in session."""
        self.session.commands_run.append(command)  # Full command
    
    def get_context_for_task(self, task_type: str) -> Dict[str, Any]:
        """
        Build context dict for a task, respecting token budgets.
        
        Returns structured context ready for prompt building.
        """
        budget = TOKEN_BUDGETS.get(task_type, TOKEN_BUDGETS["chat"])
        
        context = {
            "permanent": self._build_permanent_context(budget["permanent"]),
            "task": self._build_task_context(budget["task"]),
            "summary": self._build_summary_context(budget["summary"]),
            "session": self._build_session_context(),
            "token_budget": budget["total"]
        }
        
        return context
    
    def get_recent_messages(self, count: int = 3) -> List[ConversationMessage]:
        """Get last N messages from history."""
        return self.conversation_history[-count:] if self.conversation_history else []
    
    def clear_task_context(self):
        """Clear task-specific context (keep permanent and session)."""
        self.task = TaskContext()
    
    def clear_all(self):
        """Clear all context."""
        self.permanent = PermanentContext()
        self.task = TaskContext()
        self.session = SessionMemory()
        self.conversation_history = []
        self.conversation_summary = ""
    
    def _build_permanent_context(self, token_limit: int) -> str:
        """Build permanent context string."""
        lines = []
        if self.permanent.workspace_path:
            lines.append(f"Workspace: {self.permanent.workspace_path}")
        if self.permanent.project_type != "unknown":
            lines.append(f"Project: {self.permanent.project_type}")
        if self.permanent.language:
            lines.append(f"Language: {self.permanent.language}")
        
        return "\n".join(lines)
    
    def _build_task_context(self, token_limit: int) -> str:
        """Build task context string (no file content - user will provide path)."""
        lines = []
        
        # Note: We don't include file_content here - user will provide file path
        # and agent will read it if needed. This saves tokens.
        
        if self.task.current_file:
            lines.append(f"Current file: {self.task.current_file} ({self.task.file_language})")
        
        if self.task.error_message:
            lines.append(f"Error:\n{self.task.error_message}")
        
        if self.task.selected_code:
            lines.append(f"Selected code:\n```\n{self.task.selected_code}\n```")
        
        if self.task.terminal_output:
            lines.append(f"Terminal:\n{self.task.terminal_output}")
        
        return "\n\n".join(lines)
    
    def _build_summary_context(self, token_limit: int) -> str:
        """Build conversation summary."""
        if self.conversation_summary:
            return f"Previous context: {self.conversation_summary}"
        return ""
    
    def _build_session_context(self) -> str:
        """Build session memory context."""
        lines = []
        
        if self.session.files_created:
            lines.append(f"Files created: {', '.join(self.session.files_created[-5:])}")
        
        if self.session.files_modified:
            lines.append(f"Files modified: {', '.join(self.session.files_modified[-5:])}")
        
        return "\n".join(lines) if lines else ""
    
    def _truncate_code(self, code: str, char_limit: int) -> str:
        """Return full code (no truncation)."""
        return code
    
    def _detect_language(self, file_path: str) -> str:
        """Detect language from file extension."""
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".jsx": "jsx", ".tsx": "tsx", ".html": "html", ".css": "css",
            ".json": "json", ".md": "markdown", ".sql": "sql",
            ".java": "java", ".cpp": "cpp", ".go": "go", ".rs": "rust"
        }
        
        for ext, lang in ext_map.items():
            if file_path.endswith(ext):
                return lang
        return "text"
    
    def _trigger_summarization(self):
        """Summarize older messages into a useful context."""
        old_messages = self.conversation_history[:-self.summarize_threshold]
        
        if old_messages:
            # Build a more descriptive summary
            summary_parts = []
            
            # Extract key actions from messages
            for msg in old_messages:
                content_lower = msg.content.lower()[:200]  # First 200 chars
                
                # Look for phase/task completion markers
                if 'phase' in content_lower and ('complete' in content_lower or 'done' in content_lower):
                    summary_parts.append(f"Completed phase mentioned in conversation")
                elif msg.role == 'user' and msg.task_type:
                    # Summarize what user asked for
                    if 'implement' in content_lower or 'create' in content_lower:
                        summary_parts.append(f"User requested implementation/creation")
                    elif 'fix' in content_lower or 'bug' in content_lower:
                        summary_parts.append(f"User requested bug fix")
                    elif 'explain' in content_lower:
                        summary_parts.append(f"User asked for explanation")
            
            # Add file activity
            if self.session.files_created:
                summary_parts.append(f"Created: {', '.join(self.session.files_created[-3:])}")
            if self.session.files_modified:
                summary_parts.append(f"Modified: {', '.join(self.session.files_modified[-3:])}")
            
            # Build final summary
            user_count = sum(1 for m in old_messages if m.role == "user")
            self.conversation_summary = f"Previous {user_count} exchanges. " + "; ".join(summary_parts[:5])
            
            # Keep only recent messages
            self.conversation_history = self.conversation_history[-self.summarize_threshold:]
    
    def to_dict(self) -> Dict[str, Any]:
        """Export context to dictionary (for persistence)."""
        return {
            "permanent": {
                "workspace": self.permanent.workspace_path,
                "project_type": self.permanent.project_type,
                "language": self.permanent.language
            },
            "session": {
                "files_created": self.session.files_created,
                "files_modified": self.session.files_modified,
                "errors": self.session.errors_encountered[-5:],
                "commands": self.session.commands_run[-5:]
            },
            "summary": self.conversation_summary,
            "message_count": len(self.conversation_history)
        }
