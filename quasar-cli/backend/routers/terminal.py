"""
AI Code Editor - WebSocket Terminal Router
Interactive terminal with auto-venv detection and creation
"""

import asyncio
import subprocess
import os
import sys
import threading
import queue
from pathlib import Path
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Optional

# Import logging
from logging_config import terminal_logger, ws_logger, log_terminal_command

router = APIRouter()

from routers import files as files_router


def find_venv(folder: str, root_workspace: str = None) -> Optional[Path]:
    """
    Find virtual environment. 
    First checks current folder, then falls back to root workspace.
    Only looks for .venv and venv (not .env which is for credentials)
    """
    folder_path = Path(folder)
    
    # Check current folder for venv
    for venv_name in ['.venv', 'venv']:
        venv_path = folder_path / venv_name
        scripts_path = venv_path / 'Scripts' / 'python.exe'  # Windows
        
        if scripts_path.exists():
            return venv_path
    
    # If not in current folder and we have a root workspace, check there
    if root_workspace and folder != root_workspace:
        root_path = Path(root_workspace)
        for venv_name in ['.venv', 'venv']:
            venv_path = root_path / venv_name
            scripts_path = venv_path / 'Scripts' / 'python.exe'
            
            if scripts_path.exists():
                return venv_path
            
    return None



def get_venv_env(venv_path: Path) -> dict:
    """Get environment variables with venv activated"""
    env = os.environ.copy()
    
    scripts_dir = str(venv_path / 'Scripts')
    
    # Prepend venv Scripts to PATH
    env['PATH'] = f"{scripts_dir};{env.get('PATH', '')}"
    
    # Set VIRTUAL_ENV
    env['VIRTUAL_ENV'] = str(venv_path)
    
    # Remove PYTHONHOME if set (can cause issues)
    env.pop('PYTHONHOME', None)
    
    return env


class TerminalSession:
    """Interactive terminal with auto-venv support"""
    
    def __init__(self, websocket: WebSocket, cwd: str = None):
        self.websocket = websocket
        self.process: Optional[subprocess.Popen] = None
        self.cwd = cwd or os.getcwd()
        self.root_workspace = self.cwd  # Store root for venv fallback
        self.running = False
        self.output_queue = queue.Queue()
        self.output_thread = None
        self.venv_path: Optional[Path] = None
        self.venv_env: Optional[dict] = None
        
    async def detect_venv(self):
        """Detect and setup virtual environment"""
        self.venv_path = find_venv(self.cwd, self.root_workspace)
        
        if self.venv_path:
            self.venv_env = get_venv_env(self.venv_path)
            await self.send(f"\x1b[32m✓ Using venv: {self.venv_path.name}\x1b[0m\r\n")
        else:
            await self.send(f"\x1b[33m⚠ No virtual environment found\x1b[0m\r\n")
            await self.send(f"\x1b[90m  Creating .venv automatically...\x1b[0m\r\n")
            
            # Create venv automatically
            await self.create_venv()
            
    async def create_venv(self):
        """Create a new virtual environment"""
        try:
            venv_path = Path(self.cwd) / '.venv'
            
            # Run python -m venv .venv
            process = subprocess.Popen(
                f'{sys.executable} -m venv "{venv_path}"',
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=self.cwd
            )
            
            # Wait for completion
            stdout, _ = process.communicate(timeout=60)
            
            if process.returncode == 0:
                self.venv_path = venv_path
                self.venv_env = get_venv_env(self.venv_path)
                await self.send(f"\x1b[32m✓ Created .venv successfully!\x1b[0m\r\n")
            else:
                await self.send(f"\x1b[31m✗ Failed to create venv\x1b[0m\r\n")
                if stdout:
                    await self.send(stdout.decode('utf-8', errors='replace'))
                    
        except Exception as e:
            await self.send(f"\x1b[31m✗ Error creating venv: {e}\x1b[0m\r\n")
        
    async def send(self, text: str):
        """Send text to WebSocket"""
        try:
            await self.websocket.send_text(text)
        except:
            self.running = False
            
    async def send_prompt(self):
        """Send command prompt with venv indicator"""
        venv_indicator = f"({self.venv_path.name})" if self.venv_path else ""
        await self.send(f"\x1b[36m{self.cwd}\x1b[0m \x1b[35m{venv_indicator}\x1b[0m\r\n\x1b[33m$\x1b[0m ")
        
    def _output_reader_thread(self):
        """Thread that reads process output and puts it in queue"""
        try:
            while self.process and self.process.poll() is None:
                try:
                    char = self.process.stdout.read(1)
                    if char:
                        self.output_queue.put(char)
                    else:
                        break
                except:
                    break
            try:
                if self.process and self.process.stdout:
                    remaining = self.process.stdout.read()
                    if remaining:
                        self.output_queue.put(remaining)
            except:
                pass
        except:
            pass
        finally:
            self.output_queue.put(None)
            
    async def start_process(self, command: str):
        """Start a process with venv environment"""
        # Add -u flag for Python
        if command.startswith('python ') and ' -u ' not in command:
            command = command.replace('python ', 'python -u ', 1)
        
        # Build environment - use venv if available
        env = self.venv_env if self.venv_env else os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['PYTHONIOENCODING'] = 'utf-8'
            
        self.process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            cwd=self.cwd,
            bufsize=0,
            env=env
        )
        
        self.output_thread = threading.Thread(target=self._output_reader_thread, daemon=True)
        self.output_thread.start()
        
    async def read_output(self):
        """Read available output from queue"""
        output = b''
        try:
            while True:
                try:
                    data = self.output_queue.get_nowait()
                    if data is None:
                        break
                    output += data
                except queue.Empty:
                    break
        except:
            pass
            
        if output:
            text = output.decode('utf-8', errors='replace')
            text = text.replace('\n', '\r\n')
            await self.send(text)
            
        return len(output) > 0
        
    def write_to_process(self, text: str):
        """Write to process stdin"""
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(text.encode('utf-8'))
                self.process.stdin.flush()
            except:
                pass
                
    def is_process_running(self) -> bool:
        return self.process is not None and self.process.poll() is None
        
    def stop_process(self):
        if self.process:
            try:
                self.process.terminate()
            except:
                pass
            self.process = None
            
    def stop(self):
        self.running = False
        self.stop_process()


terminal_sessions: dict[str, TerminalSession] = {}


@router.websocket("/ws/terminal")
async def websocket_terminal(websocket: WebSocket):
    """WebSocket terminal endpoint with auto-venv"""
    await websocket.accept()
    
    cwd = files_router.current_workspace or os.getcwd()
    session = TerminalSession(websocket, cwd)
    session.running = True
    session_id = str(id(websocket))
    terminal_sessions[session_id] = session
    
    cmd_buffer = ""
    
    try:
        # Welcome
        await session.send("\x1b[32m✓ Terminal connected\x1b[0m\r\n")
        await session.send(f"\x1b[90mWorkdir: {session.cwd}\x1b[0m\r\n")
        
        # Detect/create venv
        await session.detect_venv()
        await session.send("\r\n")
        await session.send_prompt()
        
        while session.running:
            try:
                if session.is_process_running():
                    await session.read_output()
                    
                    try:
                        data = await asyncio.wait_for(websocket.receive_text(), timeout=0.02)
                    except asyncio.TimeoutError:
                        continue
                    
                    for char in data:
                        if char == '\r' or char == '\n':
                            await session.send('\r\n')
                            session.write_to_process(cmd_buffer + '\n')
                            cmd_buffer = ""
                        elif char == '\x03':
                            session.stop_process()
                            await session.send('^C\r\n')
                            cmd_buffer = ""
                            await session.send_prompt()
                        elif char == '\x7f' or char == '\x08':
                            if cmd_buffer:
                                cmd_buffer = cmd_buffer[:-1]
                                await session.send('\x08 \x08')
                        elif ord(char) >= 32:
                            cmd_buffer += char
                            await session.send(char)
                else:
                    await session.read_output()
                    
                    if session.process and session.process.poll() is not None:
                        await asyncio.sleep(0.1)
                        await session.read_output()
                        
                        exit_code = session.process.returncode
                        if exit_code != 0:
                            await session.send(f"\r\n\x1b[90mExit: {exit_code}\x1b[0m")
                        session.process = None
                        await session.send_prompt()
                        continue
                    
                    data = await websocket.receive_text()
                    
                    for char in data:
                        if char == '\r' or char == '\n':
                            await session.send('\r\n')
                            command = cmd_buffer.strip()
                            cmd_buffer = ""
                            
                            if not command:
                                await session.send_prompt()
                                continue
                                
                            # Built-in commands
                            if command.lower() in ['clear', 'cls']:
                                await session.send("\x1b[2J\x1b[H")
                                await session.send_prompt()
                                continue
                                
                            if command.lower() == 'pwd':
                                await session.send(f"{session.cwd}\r\n")
                                await session.send_prompt()
                                continue
                                
                            if command.lower().startswith('cd '):
                                new_dir = command[3:].strip()
                                if new_dir == '..':
                                    new_path = Path(session.cwd).parent
                                elif len(new_dir) > 1 and new_dir[1] == ':':
                                    new_path = Path(new_dir)
                                else:
                                    new_path = Path(session.cwd) / new_dir
                                    
                                if new_path.exists() and new_path.is_dir():
                                    session.cwd = str(new_path.resolve())
                                    # Re-detect venv for new directory
                                    old_venv = session.venv_path
                                    session.venv_path = find_venv(session.cwd, session.root_workspace)
                                    if session.venv_path:
                                        session.venv_env = get_venv_env(session.venv_path)
                                        if session.venv_path != old_venv:
                                            await session.send(f"\x1b[32m✓ Using venv: {session.venv_path.name}\x1b[0m\r\n")
                                    else:
                                        session.venv_env = None
                                else:
                                    await session.send(f"\x1b[31mNot found: {new_dir}\x1b[0m\r\n")
                                await session.send_prompt()
                                continue
                                
                            if command.lower() == 'exit':
                                session.running = False
                                continue
                                
                            # Start process
                            try:
                                await session.start_process(command)
                            except Exception as e:
                                await session.send(f"\x1b[31mError: {e}\x1b[0m\r\n")
                                await session.send_prompt()
                                
                        elif char == '\x7f' or char == '\x08':
                            if cmd_buffer:
                                cmd_buffer = cmd_buffer[:-1]
                                await session.send('\x08 \x08')
                        elif char == '\x03':
                            cmd_buffer = ""
                            await session.send('^C\r\n')
                            await session.send_prompt()
                        elif ord(char) >= 32:
                            cmd_buffer += char
                            await session.send(char)
                        
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"Terminal error: {e}")
                continue
                
    finally:
        session.stop()
        if session_id in terminal_sessions:
            del terminal_sessions[session_id]


@router.get("/sessions")
def get_terminal_sessions():
    return {"active_sessions": len(terminal_sessions)}
