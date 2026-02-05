# 🚀 QUASAR - AI-Powered CLI Code Editor

An intelligent command-line assistant that can understand your codebase, generate code, fix bugs, and execute tasks using AI.

## Installation

```bash
pip install quasar-ai
```

## Setup API Keys

**IMPORTANT**: You must provide your own API keys. QUASAR does not include any API keys.

### Option 1: Using `.env` file (Recommended)

Create a `.env` file in your project directory:

```env
# Groq (recommended - fast inference)
GROQ_API_KEY_1=gsk_your_key_here
GROQ_API_KEY_2=gsk_your_second_key_here

# Cerebras
CEREBRAS_API_KEY_1=csk_your_key_here

# Ollama runs locally - no API key needed
```

### Option 2: Using Environment Variables

```bash
# Groq
export GROQ_API_KEY_1="gsk_your_key_here"
export GROQ_API_KEY_2="gsk_your_second_key_here"

# Cerebras
export CEREBRAS_API_KEY_1="csk_your_key_here"
```

### Multiple Keys & Fallback Behavior

You can add multiple keys per provider (e.g., `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3`).

**In Auto mode** (default):
- If the first key hits rate limits or fails, QUASAR automatically tries the second key
- If all keys for a provider fail, it falls back to the next provider
- Fallback chain: Groq → Cerebras → Ollama

**Get free API keys:**
- Groq: https://console.groq.com
- Cerebras: https://cloud.cerebras.ai

## Usage

### Interactive Mode (REPL)
```bash
quasar
# or
quasar --interactive
```

### Single Command
```bash
quasar "create a hello.py file that prints Hello World"
quasar "explain main.py"
quasar "fix the bug in utils.py"
quasar "list files in current directory"
```

### Specify Workspace
```bash
quasar --workspace /path/to/project "add tests for api.py"
```

### Custom Model Selection

By default, QUASAR automatically selects the best model for each task. You can override this with `--model`:

```bash
# Use a specific Cerebras model
quasar --model cerebras/qwen-3-32b "explain this code"

# Use Groq with a specific model
quasar --model groq/llama-3.3-70b-versatile "create a REST API"

# Use local Ollama model
quasar --model ollama/qwen2.5-coder:7b "fix the bug"

# Interactive mode with custom model
quasar -i -m cerebras/qwen-3-32b
```

> **Note**: When you select a model, it will be used for ALL tasks. Choose a model that supports tool calling and has good reasoning capabilities.

## Supported Tasks

QUASAR automatically classifies your request and uses the best model:

| Task | Example |
|------|---------|
| Chat | "What is machine learning?" |
| Code Generation | "Create a REST API endpoint" |
| Bug Fixing | "Fix the TypeError in app.py" |
| Code Explanation | "Explain this function" |
| Refactoring | "Improve the structure of utils.py" |
| Documentation | "Add docstrings to main.py" |
| Test Generation | "Write tests for calculator.py" |

## Web Tools (Beta)

QUASAR can search the web and read URLs to help with your tasks:

```bash
quasar "search for the latest Python best practices"
quasar "read the documentation at https://docs.python.org/3/library/asyncio.html"
```

### Web Search Configuration

Add to your `.env` file:

```env
# Tavily API Key - Get from https://tavily.com
TAVILY_API_KEY=your_tavily_api_key_here

# SearXNG Host (if self-hosting)
# SEARX_HOST=http://localhost:8080
```

> ⚠️ **Beta**: Web tools are in beta phase. Results may vary.

## Updating

```bash
pip install --upgrade quasar-ai
```

