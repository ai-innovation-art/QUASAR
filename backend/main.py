"""
AI Code Editor - FastAPI Backend
Main application entry point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import files, execute, terminal, agent

# Import logging
from logging_config import api_logger

app = FastAPI(
    title="AI Code Editor API",
    description="Backend API for the AI-powered code editor",
    version="1.0.0"
)

# CORS - Allow frontend to access backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(files.router, prefix="/api/files", tags=["Files"])
app.include_router(execute.router, prefix="/api/execute", tags=["Execute"])
app.include_router(terminal.router, prefix="/api/terminal", tags=["Terminal"])
app.include_router(agent.router, prefix="/api/agent", tags=["Agent"])

# Log startup
api_logger.info("🚀 AI Code Editor API starting...")
api_logger.info("📁 Routers loaded: files, execute, terminal, agent")

@app.get("/")
def root():
    """Health check endpoint"""
    api_logger.debug("Health check requested at /")
    return {
        "status": "ok",
        "message": "AI Code Editor API is running",
        "version": "1.0.0"
    }

@app.get("/api/health")
def health_check():
    """API health check"""
    api_logger.debug("API health check requested")
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_excludes=["logs/*", "*.log"]  # Exclude logs from watch
    )
