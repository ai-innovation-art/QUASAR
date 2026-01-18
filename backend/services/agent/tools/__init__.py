"""
AI Agent Tools Package

Exports all tools for use with LangChain agents.
"""

from .file_tools import (
    FILE_TOOLS,
    read_file,
    create_file,
    modify_file,
    delete_file,
    list_files,
    search_files,
    set_workspace,
    get_workspace
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


# All tools combined
ALL_TOOLS = FILE_TOOLS + TERMINAL_TOOLS

# Tool categories for selective use
TOOLS_BY_CATEGORY = {
    "file": FILE_TOOLS,
    "terminal": TERMINAL_TOOLS,
    "read_only": [read_file, list_files, search_files, get_terminal_output, check_command_available],
    "write": [create_file, modify_file, delete_file],
    "execute": [run_terminal_command, run_python_file, run_pip_command],
}


def get_tools_for_task(task_type: str) -> list:
    """
    Get appropriate tools for a task type.
    
    Args:
        task_type: Type of task (chat, code_generation, bug_fixing, etc.)
        
    Returns:
        List of tools appropriate for the task
    """
    # Simple tasks - read only
    read_only_tasks = ["chat", "code_explain_simple", "code_explain_complex"]
    
    # Code generation - can create files
    generation_tasks = ["code_generation", "code_generation_multi", "test_generation", "documentation"]
    
    # Bug fixing - can modify files and run commands
    full_access_tasks = ["bug_fixing", "refactor"]
    
    if task_type in read_only_tasks:
        return TOOLS_BY_CATEGORY["read_only"]
    elif task_type in generation_tasks:
        return TOOLS_BY_CATEGORY["file"] + [run_terminal_command, check_command_available]
    elif task_type in full_access_tasks:
        return ALL_TOOLS
    else:
        # Default: all tools
        return ALL_TOOLS
