# 🚀 QUASAR - AI-Powered CLI Code Editor

An intelligent command-line assistant that can understand your codebase, generate code, fix bugs, and execute tasks using AI.

## Installation

```bash
pip install quasar-ai
```

## Setup API Keys

**IMPORTANT**: You must provide your own API keys. QUASAR does not include any API keys.

Set at least ONE of these environment variables:

```bash
# Groq (recommended - fast inference)
export GROQ_API_KEY_1="gsk_your_key_here"

# Cerebras
export CEREBRAS_API_KEY_1="csk_your_key_here"

# OpenAI
export OPENAI_API_KEY="sk-your_key_here"
```

**Get free API keys:**
- Groq: https://console.groq.com
- Cerebras: https://cloud.cerebras.ai
- OpenAI: https://platform.openai.com

### Multiple Keys (Optional)
For higher rate limits, add multiple keys per provider:
```bash
export GROQ_API_KEY_1="gsk_..."
export GROQ_API_KEY_2="gsk_..."
```

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

## Updating

```bash
pip install --upgrade quasar-ai
```

## License

MIT License
