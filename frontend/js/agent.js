/**
 * AI Code Editor - Agent Module
 * Handles AI chat functionality
 */

class AgentManager {
    constructor() {
        this.messages = [];
        this.isLoading = false;
        this.currentModel = 'auto';
    }

    /**
     * Initialize the agent
     */
    init() {
        this.setupEventListeners();
        this.autoResizeTextarea();
    }

    /**
     * Send a message to the AI
     */
    async sendMessage(message) {
        if (!message.trim() || this.isLoading) return;

        // Add user message to UI
        this.addMessage('user', message);

        // Clear input
        const input = document.getElementById('chatInput');
        input.value = '';
        this.autoResizeTextarea();

        // Show loading
        this.setLoading(true);

        try {
            // Build context from editor
            const context = this.buildContext();

            // Call backend API
            const response = await this.callBackendAPI(message, context);

            // Update model indicator
            if (response.model && response.model !== 'unknown') {
                this.setModel(`${response.provider}/${response.model}`);
            } else if (response.provider) {
                this.setModel(response.provider);
            }

            // Add response to UI
            if (response.success) {
                this.addMessage('assistant', response.response);
            } else {
                this.addMessage('assistant', `Error: ${response.error || 'Unknown error'}`);
            }

        } catch (error) {
            console.error('Agent error:', error);
            this.addMessage('assistant', `Sorry, I encountered an error: ${error.message}`);
        } finally {
            this.setLoading(false);
        }
    }

    /**
     * Call backend chat API
     */
    async callBackendAPI(message, context) {
        const baseUrl = window.CONFIG?.API_URL || 'http://localhost:8000';

        const body = {
            query: message,
            workspace: window.CONFIG?.WORKSPACE || '',
            current_file: context.filePath || null,
            file_content: context.fileContent || null,
            selected_code: context.selection || null,
            terminal_output: window.terminalManager?.getLastOutput?.() || null
        };

        const response = await fetch(`${baseUrl}/api/agent/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(body)
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        return await response.json();
    }

    /**
     * Simulate AI response (for demo/fallback purposes)
     */
    async simulateResponse(userMessage, context) {
        // Simulate network delay
        await new Promise(resolve => setTimeout(resolve, 1000 + Math.random() * 1000));

        let response = '';
        const lowerMessage = userMessage.toLowerCase();

        // Handle slash commands
        if (lowerMessage.startsWith('/explain')) {
            const selection = window.editorManager?.getSelection();
            if (selection) {
                response = `## Code Explanation

Here's what this code does:

\`\`\`
${selection}
\`\`\`

This code appears to be a ${context.language} snippet. Let me break it down:

1. **Purpose**: This code handles specific functionality
2. **Key components**: Variables, functions, and logic
3. **How it works**: Step by step execution

*Note: This is a demo response. Connect to a real LLM API for actual explanations.*`;
            } else {
                response = 'Please select some code first, then use `/explain` to get an explanation.';
            }
        } else if (lowerMessage.startsWith('/generate')) {
            const prompt = userMessage.replace('/generate', '').trim();
            response = `## Generated Code

Based on your request: "${prompt}"

\`\`\`python
# Generated code for: ${prompt}
def example_function():
    """
    This is a placeholder function.
    Replace with actual AI-generated code.
    """
    print("Hello from AI!")
    return True
\`\`\`

*Note: This is a demo. Connect to DeepSeek or another LLM for actual code generation.*`;
        } else if (lowerMessage.startsWith('/fix')) {
            response = `## Code Fix Suggestion

I analyzed your code and found potential issues:

1. ⚠️ **Issue**: Potential error found
2. ✅ **Fix**: Here's the corrected version

\`\`\`python
# Fixed code
def improved_function():
    try:
        # Your code here
        pass
    except Exception as e:
        print(f"Error: {e}")
\`\`\`

*Note: Connect to an LLM API for actual code fixes.*`;
        } else if (lowerMessage.startsWith('/refactor')) {
            response = `## Refactoring Suggestions

Here are some improvements for your code:

### 1. Extract Functions
Split large functions into smaller, reusable pieces.

### 2. Add Type Hints
\`\`\`python
def greet(name: str) -> str:
    return f"Hello, {name}!"
\`\`\`

### 3. Use Meaningful Names
- \`x\` → \`user_count\`
- \`temp\` → \`result_buffer\`

*Note: Connect to an LLM for actual refactoring suggestions.*`;
        } else {
            // General chat response
            response = `Thanks for your message! 

I received: "${userMessage}"

I'm the AI assistant for this code editor. I can help you with:

- 📝 **Explain code**: Use \`/explain\` with selected code
- ✨ **Generate code**: Use \`/generate <description>\`
- 🔧 **Fix errors**: Use \`/fix\` with your code
- ♻️ **Refactor**: Use \`/refactor\` for improvements

Currently running in demo mode. To enable full AI features:
1. Set up the backend server
2. Configure your LLM API keys
3. Connect the frontend to the backend API

How can I help you today?`;
        }

        this.addMessage('assistant', response);
    }

    /**
     * Build context for AI request
     */
    buildContext() {
        const editor = window.editorManager;
        return {
            filePath: editor?.getActiveFilePath() || null,
            fileContent: editor?.getContent() || '',
            selection: editor?.getSelection() || '',
            language: editor?.getActiveFilePath() ?
                detectLanguage(editor.getActiveFilePath()) : 'plaintext'
        };
    }

    /**
     * Add message to chat
     */
    addMessage(role, content) {
        // Store message
        this.messages.push({ role, content, timestamp: new Date() });

        // Remove welcome message if present
        const welcome = document.querySelector('.welcome-message');
        if (welcome) welcome.remove();

        // Create message element
        const messagesContainer = document.getElementById('chatMessages');
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${role}`;

        // Parse markdown-like content for code blocks
        const formattedContent = this.formatMessage(content);

        messageDiv.innerHTML = `
            <div class="message-content">
                ${formattedContent}
            </div>
            ${role === 'assistant' ? `
                <div class="message-actions">
                    <button data-action="copy">Copy</button>
                    <button data-action="insert">Insert</button>
                </div>
            ` : ''}
        `;

        // Add action handlers for assistant messages
        if (role === 'assistant') {
            messageDiv.querySelectorAll('.message-actions button').forEach(btn => {
                btn.addEventListener('click', () => {
                    const action = btn.dataset.action;
                    const code = this.extractCode(content);
                    if (action === 'copy') {
                        navigator.clipboard.writeText(code || content);
                    } else if (action === 'insert' && code) {
                        window.editorManager?.insertAtCursor(code);
                    }
                });
            });
        }

        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    /**
     * Format message content (basic markdown)
     */
    formatMessage(content) {
        // Escape HTML
        let formatted = content
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        // Code blocks
        formatted = formatted.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
            return `<pre><code class="language-${lang}">${code.trim()}</code></pre>`;
        });

        // Inline code
        formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Bold
        formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

        // Italic
        formatted = formatted.replace(/\*([^*]+)\*/g, '<em>$1</em>');

        // Headers
        formatted = formatted.replace(/^### (.+)$/gm, '<h4>$1</h4>');
        formatted = formatted.replace(/^## (.+)$/gm, '<h3>$1</h3>');

        // Lists
        formatted = formatted.replace(/^- (.+)$/gm, '<li>$1</li>');
        formatted = formatted.replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>');

        // Line breaks
        formatted = formatted.replace(/\n/g, '<br>');

        return formatted;
    }

    /**
     * Extract code from message
     */
    extractCode(content) {
        const codeMatch = content.match(/```\w*\n([\s\S]*?)```/);
        return codeMatch ? codeMatch[1].trim() : null;
    }

    /**
     * Set loading state
     */
    setLoading(loading) {
        this.isLoading = loading;
        const sendBtn = document.getElementById('sendBtn');

        if (loading) {
            sendBtn.disabled = true;

            // Add typing indicator
            const messagesContainer = document.getElementById('chatMessages');
            const typingDiv = document.createElement('div');
            typingDiv.id = 'typingIndicator';
            typingDiv.className = 'chat-message assistant';
            typingDiv.innerHTML = `
                <div class="typing-indicator">
                    <span></span><span></span><span></span>
                </div>
            `;
            messagesContainer.appendChild(typingDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        } else {
            sendBtn.disabled = false;
            document.getElementById('typingIndicator')?.remove();
        }
    }

    /**
     * Clear chat history
     */
    clearChat() {
        this.messages = [];
        const container = document.getElementById('chatMessages');
        container.innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">
                    <i data-lucide="bot"></i>
                </div>
                <h3>AI Assistant</h3>
                <p>I can help you with:</p>
                <ul>
                    <li><code>/explain</code> - Explain selected code</li>
                    <li><code>/generate</code> - Generate code</li>
                    <li><code>/fix</code> - Fix errors</li>
                    <li><code>/refactor</code> - Improve code</li>
                </ul>
            </div>
        `;
        if (window.lucide) lucide.createIcons();
    }

    /**
     * Auto-resize textarea
     */
    autoResizeTextarea() {
        const textarea = document.getElementById('chatInput');
        if (!textarea) return;

        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
    }

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        const input = document.getElementById('chatInput');
        const sendBtn = document.getElementById('sendBtn');
        const clearBtn = document.getElementById('clearChatBtn');
        const toggleBtn = document.getElementById('toggleAgentBtn');

        // Send message on button click
        sendBtn?.addEventListener('click', () => {
            this.sendMessage(input.value);
        });

        // Send on Enter, new line on Shift+Enter
        input?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage(input.value);
            }
        });

        // Auto-resize textarea
        input?.addEventListener('input', () => {
            this.autoResizeTextarea();
        });

        // Clear chat
        clearBtn?.addEventListener('click', () => {
            if (confirm('Clear all chat messages?')) {
                this.clearChat();
            }
        });

        // Toggle panel
        toggleBtn?.addEventListener('click', () => {
            this.togglePanel();
        });

        // Keyboard shortcut
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === '/') {
                e.preventDefault();
                this.togglePanel();
            }
        });
    }

    /**
     * Toggle agent panel visibility
     */
    togglePanel() {
        const panel = document.getElementById('agentPanel');
        const resizer = document.getElementById('resizerRight');
        panel.classList.toggle('collapsed');
        resizer.classList.toggle('hidden');
        window.editorManager?.layout();
    }

    /**
     * Set current model
     */
    setModel(model) {
        this.currentModel = model;
        document.getElementById('currentModel').textContent =
            model === 'auto' ? 'Auto' : model;
    }
}

// Create global instance
window.agentManager = new AgentManager();
