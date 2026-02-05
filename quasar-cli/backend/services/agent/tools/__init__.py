"""
AI Agent Tools Package

Exports all tools for use with LangChain agents.
"""

from .file_tools import (
    FILE_TOOLS,
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
    list_tree_fast,
    set_workspace,
    get_workspace
)

from .web_tools import (
    WEB_TOOLS,
    search_web,
    read_url,
    browse_interactive
)

from .terminal_tools import (
    TERMINAL_TOOLS,
    run_terminal_command,
    run_python_file,
    run_pip_command,
    get_terminal_output,
    clear_terminal_buffer,
    check_command_available
)

from .executor import (
    ToolExecutor,
    ToolExecutionResult,
    has_tool_calls,
    get_tool_calls
)


# All tools combined
ALL_TOOLS = FILE_TOOLS + TERMINAL_TOOLS + WEB_TOOLS

# Tool categories for selective use
TOOLS_BY_CATEGORY = {
    "read_only": [
        read_file, read_file_chunk, list_files, search_files, grep_search, list_tree_fast,
        get_terminal_output, check_command_available, search_web, read_url
    ],
    "write": [create_file, modify_file, patch_file, delete_file, move_file],
    "execute": [run_terminal_command, run_python_file, run_pip_command],
    "web": WEB_TOOLS,
}


def get_tools_for_task(task_type: str) -> list:
    """
    Get appropriate tools for a task type.
    
    Args:
        task_type: Type of task (chat, code_generation, bug_fixing, etc.)
        
    Returns:
        List of tools appropriate for the task
    """
    # Simple READ tasks - read only
    read_only_tasks = ["code_explain_simple", "code_explain_complex"]
    
    # Chat task - needs ALL tools for agentic operations (move, delete, create, etc.)
    full_agentic_tasks = ["chat"]
    
    # Code generation - can create files
    generation_tasks = ["code_generation", "code_generation_multi", "test_generation", "documentation"]
    
    # Bug fixing - can modify files and run commands
    full_access_tasks = ["bug_fixing", "refactor"]
    
    if task_type in read_only_tasks:
        return TOOLS_BY_CATEGORY["read_only"]
    elif task_type in ["research"]: # New explicit research task
        return WEB_TOOLS + [read_file, list_files, list_tree_fast]
    elif task_type in full_agentic_tasks:
        return ALL_TOOLS
    elif task_type in generation_tasks:
        # Generation tasks now get research capabilities to find docs
        return FILE_TOOLS + WEB_TOOLS + [run_terminal_command, check_command_available]
    elif task_type in full_access_tasks:
        return ALL_TOOLS
    else:
        return ALL_TOOLS
