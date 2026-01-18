# AI Code Editor

An AI-powered code editor with an intelligent agent system for code generation, explanation, bug fixing, and refactoring.

## Features

- 🤖 **AI Agent Orchestrator** - Routes queries to specialized models based on task type
- 📝 **Monaco Editor** - VS Code-like editing experience
- 💻 **Integrated Terminal** - WebSocket-based interactive terminal
- 📁 **File Explorer** - Browse and manage project files
- 🔄 **Model Fallback** - Automatic failover across multiple LLM providers

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ File Tree│  │  Editor  │  │ Terminal │  │ AI Panel │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    Orchestrator                       │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐ │   │
│  │  │Classify │→ │ Route   │→ │ Execute │→ │ Respond │ │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘ │   │
│  └──────────────────────────────────────────────────────┘   │
│                              │                               │
│  ┌───────────────────────────┴───────────────────────────┐  │
│  │                  Model Providers                       │  │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────────────┐  │  │
│  │  │ Ollama │ │Cerebras│ │  Groq  │ │  Cloudflare    │  │  │
│  │  │(Local) │ │ (API)  │ │ (API)  │ │    (API)       │  │  │
│  │  └────────┘ └────────┘ └────────┘ └────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Task Types

| Task | Primary Model | Fallback |
|------|--------------|----------|
| Chat | Ollama 7B | Groq 8B |
| Code Explain | Ollama 32B | Groq 70B |
| Code Generation | DeepSeek R1 | Cerebras GLM |
| Bug Fixing | Ollama 32B | Cerebras |
| Refactor | Cerebras 32B | Groq 70B |
| Test Generation | Ollama 32B | Groq 70B |

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+ (optional, for frontend dev server)
- Ollama (for local models)

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Create .env file with API keys
cp .env.example .env
# Edit .env with your API keys
```

### Environment Variables

Create a `.env` file in the `backend` folder:

```env
# Cerebras API Keys (get from https://cloud.cerebras.ai)
CEREBRAS_API_KEY_1=your_key_here
CEREBRAS_API_KEY_2=optional_backup_key

# Groq API Keys (get from https://console.groq.com)
GROQ_API_KEY_1=your_key_here
GROQ_API_KEY_2=optional_backup_key

# Cloudflare Workers AI (get from https://dash.cloudflare.com)
CLOUDFLARE_ACCOUNT_ID_1=your_account_id
CLOUDFLARE_API_TOKEN_1=your_token
```

### Download Ollama Models

```bash
ollama pull qwen2.5-coder:7b
ollama pull qwen2.5-coder:32b
ollama pull deepseek-r1:7b
```

### Run the Backend

```bash
cd backend
python main.py
```

Server starts at `http://localhost:8000`

### Run the Frontend

Open `frontend/index.html` in a browser, or use Live Server extension in VS Code.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/agent/chat` | POST | Send chat message to AI |
| `/api/agent/classify` | POST | Classify task type |
| `/api/agent/health` | GET | Health check |
| `/api/files/open` | POST | Open workspace folder |
| `/api/files/read` | GET | Read file content |
| `/api/files/save` | POST | Save file |
| `/api/terminal/ws` | WS | WebSocket terminal |

## Project Structure

```
Editor/
├── frontend/
│   ├── index.html
│   ├── css/main.css
│   └── js/
│       ├── agent.js      # AI chat functionality
│       ├── editor.js     # Monaco editor
│       ├── terminal.js   # xterm.js terminal
│       └── fileTree.js   # File explorer
├── backend/
│   ├── main.py           # FastAPI entry point
│   ├── routers/
│   │   ├── agent.py      # AI endpoints
│   │   ├── files.py      # File operations
│   │   └── terminal.py   # Terminal WebSocket
│   └── services/agent/
│       ├── orchestrator.py    # Task routing
│       ├── config.py          # Model config
│       ├── models/
│       │   ├── credentials.py # API key management
│       │   ├── providers.py   # LLM providers
│       │   └── router.py      # Model selection
│       ├── context/
│       │   └── manager.py     # Context management
│       ├── specialists/       # Task-specific agents
│       └── tools/             # File & terminal tools
└── README.md
```

## Roadmap

- [x] Phase 1: Agent Foundation
- [x] Phase 2: File & Terminal Tools
- [x] Phase 3: Orchestrator + Specialists
- [x] Phase 4: Context Management
- [x] Phase 5: Frontend Integration
- [ ] Phase 6: Agentic Tool Calling Loop
- [ ] Phase 7: Streaming Responses
- [ ] Phase 8: RAG for Large Projects

## License

MIT
