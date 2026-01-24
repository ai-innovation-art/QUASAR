"""
Agent API Router

Provides endpoints for:
- Health check
- Model testing
- Agent chat with orchestrator
- WebSocket for real-time interaction
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, AsyncGenerator
import json
import traceback
import asyncio

from services.agent.models import CredentialManager, ModelRouter
from services.agent.orchestrator import Orchestrator
from services.agent.specialists import get_specialist
from services.agent.logger import agent_logger

router = APIRouter()

# Global orchestrator instance
_orchestrator: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    """Get or create orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        agent_logger.info("🤖 Creating new Orchestrator instance")
        _orchestrator = Orchestrator()
    return _orchestrator


class TestModelRequest(BaseModel):
    """Request for testing a model."""
    provider: str  # ollama, cerebras, groq, cloudflare
    model_name: Optional[str] = None
    prompt: str
    temperature: Optional[float] = 0.7


class TestModelResponse(BaseModel):
    """Response from model test."""
    success: bool
    provider: str
    model: str
    response: Optional[str] = None
    error: Optional[str] = None


class ChatRequest(BaseModel):
    """Request for agent chat."""
    query: str
    workspace: Optional[str] = None
    current_file: Optional[str] = None
    file_content: Optional[str] = None
    selected_code: Optional[str] = None
    terminal_output: Optional[str] = None
    error_message: Optional[str] = None
    selected_model: Optional[str] = None  # Format: "provider/model_key" or None for Auto


class ChatResponse(BaseModel):
    """Response from agent chat."""
    success: bool
    response: str
    task_type: str
    model: str
    provider: str
    tools_used: Optional[list] = None
    tool_calls_count: int = 0
    iterations: int = 1
    error: Optional[str] = None




@router.get("/health")
async def health_check():
    """
    Check agent service health and credential status.
    
    Returns:
        Status of all providers and credentials
    """
    cred_manager = CredentialManager()
    model_router = ModelRouter()
    
    return {
        "status": "ok",
        "service": "ai-agent",
        "providers": cred_manager.get_status(),
        "available_providers": model_router.get_available_providers()
    }


@router.get("/models/list")
async def list_models():
    """
    List all available models from config for user selection.
    
    Returns:
        List of {provider, model_name, display_name, model_key}
    """
    from services.agent.config import AgentConfig
    
    models = []
    
    # Iterate through all providers and their models
    for provider_name, provider_config in AgentConfig.PROVIDERS.items():
        if not provider_config.enabled:
            continue
            
        for model_key, model_config in provider_config.models.items():
            models.append({
                "provider": provider_name,
                "model_name": model_config.name,
                "model_key": model_key,
                "display_name": f"{provider_name.capitalize()} / {model_config.name}"
            })
    
    return {
        "models": models
    }


@router.post("/test-model", response_model=TestModelResponse)
async def test_model(request: TestModelRequest):
    """
    Test a specific model with a prompt.
    
    Useful for verifying credentials and model connectivity.
    """
    model_router = ModelRouter()
    
    try:
        model = model_router.get_model_for_provider(
            provider=request.provider,
            model_name=request.model_name,
            temperature=request.temperature
        )
        
        if model is None:
            return TestModelResponse(
                success=False,
                provider=request.provider,
                model=request.model_name or "default",
                error=f"Could not create model for provider: {request.provider}"
            )
        
        # Invoke the model
        from langchain_core.messages import HumanMessage
        messages = [HumanMessage(content=request.prompt)]
        
        response = await model.ainvoke(messages)
        
        return TestModelResponse(
            success=True,
            provider=request.provider,
            model=request.model_name or "default",
            response=response.content
        )
        
    except Exception as e:
        return TestModelResponse(
            success=False,
            provider=request.provider,
            model=request.model_name or "default",
            error=str(e)
        )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Process a chat request through the orchestrator.
    
    The orchestrator will:
    1. Classify the task
    2. Route to appropriate specialist
    3. Return the response
    """
    agent_logger.info(f"📨 /chat request: {request.query[:80]}...")
    agent_logger.debug(f"Context: file={request.current_file}, selected={bool(request.selected_code)}, error={bool(request.error_message)}")
    
    orchestrator = get_orchestrator()
    
    # Set workspace if provided
    if request.workspace:
        orchestrator.set_workspace(request.workspace)
    
    try:
        # Process through orchestrator
        agent_logger.info("🔄 Processing query through orchestrator...")
        result = await orchestrator.process(
            query=request.query,
            current_file=request.current_file,
            file_content=request.file_content,
            selected_code=request.selected_code,
            terminal_output=request.terminal_output,
            error_message=request.error_message,
            selected_model=request.selected_model
        )
        
        agent_logger.info(f"✅ /chat response: task_type={result.task_type}, provider={result.provider}, success={result.success}")
        agent_logger.debug(f"Response length: {len(result.response)} chars")
        
        return ChatResponse(
            success=result.success,
            response=result.response,
            task_type=result.task_type,
            model=result.model_used,
            provider=result.provider,
            tools_used=result.tools_used,
            tool_calls_count=result.tool_calls_count,
            iterations=result.iterations,
            error=result.error
        )
        
    except Exception as e:
        agent_logger.error(f"❌ /chat error: {type(e).__name__}: {e}")
        agent_logger.error(traceback.format_exc())
        return ChatResponse(
            success=False,
            response=str(e),
            task_type="error",
            model="none",
            provider="none",
            error=str(e)
        )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Stream AI responses in real-time using Server-Sent Events (SSE).
    
    Streams:
    - classification: Task type classification result
    - token: Individual response tokens
    - tool_start: Tool execution starting
    - tool_complete: Tool execution completed
    - done: Final completion signal
    - error: Error messages
    """
    agent_logger.info(f"📨 /chat/stream request: {request.query[:80]}...")
    
    orchestrator = get_orchestrator()
    
    # Set workspace if provided
    if request.workspace:
        orchestrator.set_workspace(request.workspace)
    
    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events from orchestrator stream."""
        try:
            async for chunk in orchestrator.process_stream(
                query=request.query,
                current_file=request.current_file,
                file_content=request.file_content,
                selected_code=request.selected_code,
                terminal_output=request.terminal_output,
                error_message=request.error_message,
                selected_model=request.selected_model
            ):
                # SSE format: data: {json}\n\n
                yield f"data: {json.dumps(chunk)}\n\n"
                
        except Exception as e:
            agent_logger.error(f"❌ /chat/stream error: {type(e).__name__}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


class ClassifyRequest(BaseModel):
    """Request for classifying a task."""
    query: str
    current_file: Optional[str] = None


@router.post("/classify")
async def classify_task(request: ClassifyRequest):
    """
    Classify a query without executing.
    
    Useful for debugging or preview.
    """
    orchestrator = get_orchestrator()
    
    try:
        classification = await orchestrator.classify_task(
            query=request.query,
            current_file=request.current_file
        )
        
        return {
            "task_type": classification.task_type.value,
            "confidence": classification.confidence,
            "requires_file_context": classification.requires_file_context,
            "requires_terminal": classification.requires_terminal,
            "estimated_complexity": classification.estimated_complexity,
            "reasoning": classification.reasoning
        }
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"ERROR in classify_task endpoint:")
        print(f"Type: {type(e).__name__}")
        print(f"Message: {str(e)}")
        print(f"Traceback:\n{error_trace}")
        return {
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": error_trace
        }


@router.websocket("/ws")
async def websocket_agent(websocket: WebSocket):
    """
    WebSocket endpoint for real-time agent interaction.
    
    Message format (JSON):
    {
        "type": "chat" | "set_workspace" | "set_context",
        "query": "...",
        "workspace": "...",
        "file_path": "...",
        "file_content": "...",
        "selected_code": "...",
        "terminal_output": "...",
        "error_message": "..."
    }
    """
    await websocket.accept()
    
    orchestrator = get_orchestrator()
    context: Dict[str, Any] = {}
    
    try:
        while True:
            # Receive message
            raw_data = await websocket.receive_text()
            
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                # Treat as simple text query
                data = {"type": "chat", "query": raw_data}
            
            msg_type = data.get("type", "chat")
            
            # Handle different message types
            if msg_type == "set_workspace":
                workspace = data.get("workspace", "")
                if workspace:
                    orchestrator.set_workspace(workspace)
                    await websocket.send_json({
                        "type": "system",
                        "content": f"Workspace set to: {workspace}"
                    })
                continue
            
            elif msg_type == "set_context":
                # Update context
                context.update({
                    "file_path": data.get("file_path"),
                    "file_content": data.get("file_content"),
                    "selected_code": data.get("selected_code"),
                    "terminal_output": data.get("terminal_output"),
                    "error_message": data.get("error_message")
                })
                await websocket.send_json({
                    "type": "system",
                    "content": "Context updated"
                })
                continue
            
            elif msg_type == "chat":
                query = data.get("query", "")
                
                if not query:
                    await websocket.send_json({
                        "type": "error",
                        "content": "Empty query"
                    })
                    continue
                
                # Get context from message or stored context
                current_file = data.get("file_path") or context.get("file_path")
                file_content = data.get("file_content") or context.get("file_content")
                selected_code = data.get("selected_code") or context.get("selected_code")
                terminal_output = data.get("terminal_output") or context.get("terminal_output")
                error_message = data.get("error_message") or context.get("error_message")
                
                # Send "thinking" status
                await websocket.send_json({
                    "type": "status",
                    "content": "Classifying task..."
                })
                
                # Process through orchestrator
                result = await orchestrator.process(
                    query=query,
                    current_file=current_file,
                    file_content=file_content,
                    selected_code=selected_code,
                    terminal_output=terminal_output,
                    error_message=error_message
                )
                
                # Send response
                await websocket.send_json({
                    "type": "response",
                    "content": result.response,
                    "task_type": result.task_type,
                    "model": result.model_used,
                    "provider": result.provider,
                    "success": result.success,
                    "tools_used": result.tools_used or [],
                    "tool_calls_count": result.tool_calls_count,
                    "iterations": result.iterations
                })
                
    except WebSocketDisconnect:
        print("Agent WebSocket disconnected")
    except Exception as e:
        print(f"Agent WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "content": str(e)
            })
        except:
            pass

