#!/usr/bin/env python
"""
QUASAR CLI - Terminal-based AI Code Editor

Usage:
    quasar "your prompt here"           # Single command mode
    quasar --interactive                # REPL mode
    quasar --help                       # Show help
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.text import Text

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from services.agent.orchestrator import Orchestrator
from services.agent.models import CredentialManager

app = typer.Typer(
    name="quasar",
    help="🚀 QUASAR - AI-powered CLI code editor",
    add_completion=False,
)
console = Console()

# Global orchestrator and selected model
_orchestrator: Optional[Orchestrator] = None
_selected_model: Optional[str] = None


def get_orchestrator() -> Orchestrator:
    """Get or create orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


def check_api_keys() -> bool:
    """Check if any API keys are configured."""
    cred_manager = CredentialManager()
    status = cred_manager.get_status()
    
    available = [name for name, info in status.items() if info.get("has_credentials")]
    
    if not available or available == ["ollama"]:
        console.print(Panel(
            "[bold red]⚠️  No API keys found![/bold red]\n\n"
            "Please set at least one of these environment variables:\n\n"
            "  [green]GROQ_API_KEY_1[/green]=gsk_...\n"
            "  [green]CEREBRAS_API_KEY_1[/green]=csk_...\n"
            "  [green]OPENAI_API_KEY_1[/green]=sk_...\n\n"
            "You can add multiple keys: GROQ_API_KEY_2, etc.\n\n"
            "[dim]Get API keys at:[/dim]\n"
            "  Groq: https://console.groq.com\n"
            "  Cerebras: https://cloud.cerebras.ai",
            title="Setup Required",
            border_style="red"
        ))
        return False
    
    console.print(f"[dim]✓ Available providers: {', '.join(available)}[/dim]")
    return True


async def process_query(query: str, workspace: str, selected_model: Optional[str] = None) -> None:
    """Process a single query and stream the response."""
    orchestrator = get_orchestrator()
    orchestrator.set_workspace(workspace)
    
    response_text = ""
    current_tool = None
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task("Thinking...", total=None)
        
        try:
            async for chunk in orchestrator.process_stream(query=query, selected_model=selected_model):
                chunk_type = chunk.get("type", "")
                
                if chunk_type == "classification":
                    task_type = chunk.get("task_type", "unknown")
                    progress.update(task_id, description=f"[cyan]Task: {task_type}[/cyan]")
                
                elif chunk_type == "iteration":
                    current = chunk.get("current", 1)
                    max_iter = chunk.get("max", 30)
                    progress.update(task_id, description=f"[yellow]Iteration {current}/{max_iter}[/yellow]")
                
                elif chunk_type == "tool_start":
                    tool_name = chunk.get("tool", "unknown")
                    current_tool = tool_name
                    progress.update(task_id, description=f"[blue]🔧 {tool_name}...[/blue]")
                
                elif chunk_type == "tool_complete":
                    tool_name = chunk.get("tool", current_tool or "tool")
                    console.print(f"  [green]✓[/green] {tool_name}")
                    current_tool = None
                
                elif chunk_type == "message":
                    # Progress/observation messages
                    msg = chunk.get("content", "")
                    if msg:
                        progress.update(task_id, description=f"[dim]{msg[:60]}...[/dim]" if len(msg) > 60 else f"[dim]{msg}[/dim]")
                
                elif chunk_type == "token":
                    # Streaming response text - collect it
                    token = chunk.get("content", "")
                    response_text += token
                    # Stop the spinner when we start getting response
                    if response_text and len(response_text) < 10:
                        progress.stop()
                
                elif chunk_type == "error":
                    error_msg = chunk.get("message", "Unknown error")
                    console.print(f"[red]❌ Error: {error_msg}[/red]")
                    return
                
                elif chunk_type == "done":
                    # Final summary
                    model = chunk.get("model", "unknown")
                    provider = chunk.get("provider", "unknown")
                    tools_used = chunk.get("tools_used", [])
                    tool_count = chunk.get("tool_calls_count", 0)
                    
                    # Print the response
                    if response_text:
                        console.print()
                        console.print(Markdown(response_text))
                    
                    # Print summary
                    console.print()
                    summary = f"[dim]Model: {provider}/{model}"
                    if tool_count > 0:
                        summary += f" | Tools: {tool_count}"
                    summary += "[/dim]"
                    console.print(summary)
                    return
        
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled[/yellow]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


def run_repl(workspace: str, selected_model: Optional[str] = None) -> None:
    """Run interactive REPL mode."""
    model_info = f"\n[dim]Model: {selected_model}[/dim]" if selected_model else ""
    console.print(Panel(
        "[bold cyan]🚀 QUASAR AI Editor[/bold cyan]\n\n"
        f"[dim]Workspace: {workspace}[/dim]"
        f"{model_info}\n\n"
        "Type your requests, or:\n"
        "  [green]/help[/green]  - Show commands\n"
        "  [green]/quit[/green]  - Exit",
        border_style="cyan"
    ))
    
    while True:
        try:
            console.print()
            query = console.input("[bold green]>[/bold green] ").strip()
            
            if not query:
                continue
            
            # Handle special commands
            if query.lower() in ["/quit", "/exit", "/q"]:
                console.print("[dim]Goodbye![/dim]")
                break
            elif query.lower() == "/help":
                console.print(Panel(
                    "[bold]Commands:[/bold]\n"
                    "  /quit, /exit, /q - Exit REPL\n"
                    "  /help - Show this help\n\n"
                    "[bold]Examples:[/bold]\n"
                    '  "Create a hello.py file"\n'
                    '  "Explain main.py"\n'
                    '  "Fix the bug in utils.py"\n'
                    '  "List files in current directory"',
                    title="Help",
                    border_style="blue"
                ))
                continue
            
            # Process the query
            asyncio.run(process_query(query, workspace, selected_model))
            
        except KeyboardInterrupt:
            console.print("\n[dim]Use /quit to exit[/dim]")
        except EOFError:
            console.print("\n[dim]Goodbye![/dim]")
            break


@app.command()
def main(
    query: Optional[str] = typer.Argument(None, help="Query to process"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Run in interactive REPL mode"),
    workspace: str = typer.Option(None, "--workspace", "-w", help="Workspace directory (default: current dir)"),
    model: str = typer.Option(None, "--model", "-m", help="Model to use (format: provider/model-name, e.g., cerebras/qwen-3-32b)"),
):
    """
    🚀 QUASAR - AI-powered CLI code editor
    
    Examples:
        quasar "create a hello.py file"
        quasar "explain main.py"
        quasar --interactive
    """
    # Set workspace
    if workspace is None:
        workspace = os.getcwd()
    workspace = str(Path(workspace).resolve())
    
    # Check for API keys
    if not check_api_keys():
        raise typer.Exit(1)
    
    if interactive or query is None:
        # REPL mode
        run_repl(workspace, model)
    else:
        # Single command mode
        asyncio.run(process_query(query, workspace, model))


if __name__ == "__main__":
    app()
