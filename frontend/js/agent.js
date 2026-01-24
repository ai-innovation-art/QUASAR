/**
 * AI Code Editor - Agent Module
 * Handles AI chat functionality
 */

class AgentManager {
    constructor() {
        this.messages = [];
        this.isLoading = false;
        this.currentModel = 'auto'; // Model being used by AI (indicator)
        this.selectedModel = localStorage.getItem('quasar_selected_model') || 'Auto'; // User selected model
        this.streamingEnabled = true;  // Enable streaming by default
        this.currentStreamingElement = null;  // Track streaming message element
        this.currentEventSource = null;  // Track EventSource for cancellation
        this.currentAbortController = null;  // For stopping streaming
    }

    /**
     * Initialize the agent
     */
    init() {
        this.setupEventListeners();
        this.autoResizeTextarea();
        this.updateModelSelectionUI();
        this.loadAvailableModels();
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

            // Use streaming if enabled
            if (this.streamingEnabled) {
                await this.sendMessageStream(message, context);
            } else {
                // Fallback to regular API
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

                    // Auto-refresh file tree if files were modified
                    if (response.tools_used && response.tools_used.length > 0) {
                        const fileModifyingTools = ['create_file', 'modify_file', 'delete_file'];
                        const shouldRefresh = response.tools_used.some(tool =>
                            fileModifyingTools.includes(tool)
                        );

                        if (shouldRefresh && window.fileTreeManager) {
                            console.log('Auto-refreshing file tree after file modification');
                            setTimeout(() => {
                                window.fileTreeManager.loadFileTree();
                            }, 500); // Small delay to ensure file is written
                        }
                    }
                } else {
                    this.addMessage('assistant', `Error: ${response.error || 'Unknown error'}`);
                }
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
            workspace: window.fileTreeManager?.rootPath || null,  // Use opened folder, not CONFIG
            current_file: context.filePath || null,
            file_content: context.fileContent || null,
            selected_code: context.selection || null,
            terminal_output: window.terminalManager?.getLastOutput?.() || null,
            selected_model: this.selectedModel === 'Auto' ? null : this.selectedModel
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
     * Send message with streaming response (SSE)
     */
    async sendMessageStream(message, context) {
        const baseUrl = window.CONFIG?.API_URL || 'http://localhost:8000';

        const body = {
            query: message,
            workspace: window.fileTreeManager?.rootPath || null,
            current_file: context.filePath || null,
            file_content: context.fileContent || null,
            selected_code: context.selection || null,
            terminal_output: window.terminalManager?.getLastOutput?.() || null,
            selected_model: this.selectedModel === 'Auto' ? null : this.selectedModel
        };

        // Create streaming message placeholder
        this.createStreamingMessage();

        // Create abort controller for cancellation
        this.currentAbortController = new AbortController();

        try {
            const response = await fetch(`${baseUrl}/api/agent/chat/stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(body),
                signal: this.currentAbortController.signal
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            // Read the stream
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let currentContent = '';
            let toolsUsed = [];

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Process SSE events (lines starting with "data: ")
                const lines = buffer.split('\n');
                buffer = lines.pop(); // Keep incomplete line in buffer

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            this.handleStreamEvent(data, currentContent, toolsUsed);

                            if (data.type === 'token' && data.content) {
                                currentContent += data.content;
                                this.updateStreamingMessage(currentContent);
                            } else if (data.type === 'tool_complete') {
                                if (data.tool && !toolsUsed.includes(data.tool)) {
                                    toolsUsed.push(data.tool);
                                }
                            } else if (data.type === 'done') {
                                this.finalizeStreamingMessage(currentContent);

                                // Update model indicator
                                if (data.model) {
                                    this.setModel(`${data.provider}/${data.model}`);
                                }

                                // NOTE: File tree refresh now happens immediately in tool_complete handler
                                // No need for delayed refresh here
                            } else if (data.type === 'error') {
                                this.finalizeStreamingMessage(`Error: ${data.message}`);
                            }
                        } catch (e) {
                            console.warn('Failed to parse SSE event:', e);
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Streaming error:', error);
            this.finalizeStreamingMessage(`Error: ${error.message}`);
        }
    }

    /**
     * Create streaming message placeholder
     */
    createStreamingMessage() {
        // Remove welcome message if present
        const welcome = document.querySelector('.welcome-message');
        if (welcome) welcome.remove();

        const messagesContainer = document.getElementById('chatMessages');
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message assistant streaming';
        messageDiv.id = 'streamingMessage';
        messageDiv.innerHTML = `
            <div class="streaming-actions">
                <button class="stop-streaming-btn" title="Stop generating">
                    ⏹ Stop
                </button>
            </div>
            <div class="message-content streaming-content">
                <span class="streaming-cursor">▊</span>
            </div>
        `;
        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        // Add stop button handler
        const stopBtn = messageDiv.querySelector('.stop-streaming-btn');
        stopBtn.addEventListener('click', () => this.stopStreaming());

        // Remove typing indicator if present
        document.getElementById('typingIndicator')?.remove();

        this.currentStreamingElement = messageDiv;
    }

    /**
     * Stop current streaming response
     */
    stopStreaming() {
        if (this.currentAbortController) {
            this.currentAbortController.abort();
            this.currentAbortController = null;
            console.log('⏹ Streaming stopped by user');

            // Finalize with current content
            const contentEl = this.currentStreamingElement?.querySelector('.message-content');
            if (contentEl) {
                const currentText = contentEl.textContent.replace('▊', '');
                this.finalizeStreamingMessage(currentText + '\n\n[Stopped by user]');
            }
        }
    }

    /**
     * Update streaming message with new content (appends to streaming area only)
     */
    updateStreamingMessage(content) {
        if (!this.currentStreamingElement) return;

        const contentEl = this.currentStreamingElement.querySelector('.message-content');
        if (contentEl) {
            // Strip think tags from streaming content
            const cleanContent = this.stripThinkTags(content);

            // Find or create the streaming text area (separate from action cards)
            let streamingText = contentEl.querySelector('.streaming-text');
            if (!streamingText) {
                streamingText = document.createElement('div');
                streamingText.className = 'streaming-text';
                contentEl.appendChild(streamingText);
            }

            // Update only the streaming text area, not the action cards
            const formattedContent = this.formatMessage(cleanContent);
            streamingText.innerHTML = formattedContent + '<span class="streaming-cursor">▊</span>';

            // Auto-scroll
            const messagesContainer = document.getElementById('chatMessages');
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }

    /**
     * Handle different stream event types
     */
    handleStreamEvent(data, currentContent, toolsUsed) {
        switch (data.type) {
            case 'classification':
                console.log(`📋 Task: ${data.task_type} (confidence: ${data.confidence})`);
                break;
            case 'iteration':
                console.log(`🔄 Iteration ${data.current}/${data.max}`);
                break;
            case 'message':
                // Display narrative message inline
                console.log(`💬 ${data.content}`);
                this.appendProgressMessage(data.content);
                break;
            case 'tool_start':
                console.log(`🔧 Starting tool: ${data.tool}`);
                this.showActionCard(data.tool, data.args || {}, 'running');
                break;
            case 'tool_complete':
                console.log(`✅ Tool complete: ${data.tool}`);
                this.updateActionCard(data.tool, 'complete', data.result);

                // Immediately refresh file tree for file-modifying tools
                const fileTools = ['create_file', 'modify_file', 'delete_file', 'move_file'];
                if (fileTools.includes(data.tool) && window.fileTreeManager) {
                    console.log(`🔄 Refreshing file tree after ${data.tool}`);
                    window.fileTreeManager.loadFileTree();
                }
                break;
            case 'file_tree_updated':
                // Explicit event from backend when file tree changes
                console.log('📁 File tree update event received');
                if (window.fileTreeManager) {
                    window.fileTreeManager.loadFileTree();
                }
                break;
            case 'tool_error':
                console.log(`❌ Tool error: ${data.tool}`);
                this.updateActionCard(data.tool, 'error', data.error);
                break;
        }
    }

    /**
     * Append a narrative/progress message to the streaming content
     */
    appendProgressMessage(message) {
        if (!this.currentStreamingElement) return;

        const contentEl = this.currentStreamingElement.querySelector('.message-content');
        if (contentEl) {
            // Create narrative text paragraph
            const narrativeEl = document.createElement('p');
            narrativeEl.className = 'agent-narrative';
            narrativeEl.innerHTML = this.formatInlineCode(message);

            // Insert before cursor
            const cursor = contentEl.querySelector('.streaming-cursor');
            if (cursor) {
                cursor.insertAdjacentElement('beforebegin', narrativeEl);
            } else {
                contentEl.appendChild(narrativeEl);
            }

            // Auto-scroll
            const messagesContainer = document.getElementById('chatMessages');
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }

    /**
     * Format inline code in messages (text wrapped in backticks)
     */
    formatInlineCode(text) {
        return text.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
    }

    /**
     * Get tool display info (icon, label, description)
     */
    getToolDisplayInfo(toolName, args) {
        const toolInfo = {
            'read_file': {
                icon: '📖',
                label: 'Read file(s)',
                getDetail: (a) => a.path || a.file_path || 'file'
            },
            'create_file': {
                icon: '📝',
                label: 'Creating file',
                getDetail: (a) => a.path || a.file_path || 'file'
            },
            'modify_file': {
                icon: '✏️',
                label: 'Modifying file',
                getDetail: (a) => a.path || a.file_path || 'file'
            },
            'delete_file': {
                icon: '🗑️',
                label: 'Deleting file',
                getDetail: (a) => a.path || a.file_path || 'file'
            },
            'patch_file': {
                icon: '🩹',
                label: 'Patching file',
                getDetail: (a) => a.path || a.file_path || 'file'
            },
            'move_file': {
                icon: '📦',
                label: 'Moving file',
                getDetail: (a) => `${a.source || 'file'} → ${a.destination || 'destination'}`
            },
            'list_files': {
                icon: '🔍',
                label: 'Searched workspace',
                getDetail: (a) => a.description || 'Scanning directory structure'
            },
            'search_code': {
                icon: '🔍',
                label: 'Searched workspace',
                getDetail: (a) => a.pattern ? `Searching for "${a.pattern}"` : 'Searching codebase'
            },
            'run_terminal_command': {
                icon: '⌨️',
                label: 'Command',
                getDetail: (a) => a.command || 'terminal command',
                isCommand: true
            },
            'run_python_file': {
                icon: '🐍',
                label: 'Running Python',
                getDetail: (a) => a.file_path || 'script'
            },
            'run_pip_command': {
                icon: '📦',
                label: 'Package Manager',
                getDetail: (a) => `pip ${a.action || ''} ${a.packages || ''}`.trim()
            }
        };

        return toolInfo[toolName] || {
            icon: '⚙️',
            label: toolName.replace(/_/g, ' '),
            getDetail: () => 'Executing...'
        };
    }

    /**
     * Show styled action card for tool execution
     */
    showActionCard(toolName, args, status) {
        if (!this.currentStreamingElement) return;

        const contentEl = this.currentStreamingElement.querySelector('.message-content');
        if (!contentEl) return;

        const info = this.getToolDisplayInfo(toolName, args);
        const detail = info.getDetail(args);

        // Create action card
        const card = document.createElement('div');
        card.className = `action-card action-card-${status}`;
        card.id = `action-${toolName}-${Date.now()}`;
        card.dataset.tool = toolName;

        if (info.isCommand) {
            // Special styling for terminal commands
            card.innerHTML = `
                <div class="action-header">
                    <span class="action-icon">${info.icon}</span>
                    <span class="action-label">${info.label}</span>
                    <span class="action-status-badge running">Running</span>
                </div>
                <div class="command-box">
                    <code>${this.escapeHtml(detail)}</code>
                </div>
            `;
        } else {
            // Standard action card
            const fileName = this.extractFileName(detail);
            card.innerHTML = `
                <div class="action-header">
                    <span class="action-icon">${info.icon}</span>
                    <span class="action-label">${info.label}</span>
                    ${fileName ? `<span class="file-badge">${fileName}</span>` : ''}
                    <span class="action-status-badge running">⏳</span>
                </div>
                ${!fileName && detail ? `<div class="action-detail">${this.escapeHtml(detail)}</div>` : ''}
            `;
        }

        // Insert before cursor
        const cursor = contentEl.querySelector('.streaming-cursor');
        if (cursor) {
            cursor.insertAdjacentElement('beforebegin', card);
        } else {
            contentEl.appendChild(card);
        }

        // Store reference
        this.currentActionCard = card;

        // Auto-scroll
        const messagesContainer = document.getElementById('chatMessages');
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    /**
     * Update action card status
     */
    updateActionCard(toolName, status, result) {
        // Find the most recent card for this tool
        const cards = document.querySelectorAll(`[data-tool="${toolName}"]`);
        const card = cards[cards.length - 1];

        if (!card) return;

        card.className = `action-card action-card-${status}`;

        const statusBadge = card.querySelector('.action-status-badge');
        if (statusBadge) {
            if (status === 'complete') {
                statusBadge.textContent = '✓';
                statusBadge.className = 'action-status-badge complete';
            } else if (status === 'error') {
                statusBadge.textContent = '✗';
                statusBadge.className = 'action-status-badge error';
            }
        }

        // Show command output if present
        if (result && card.querySelector('.command-box')) {
            const outputEl = document.createElement('div');
            outputEl.className = 'command-output';
            outputEl.innerHTML = `<pre>${this.escapeHtml(result.substring(0, 500))}</pre>`;
            card.appendChild(outputEl);
        }
    }

    /**
     * Extract filename from path
     */
    extractFileName(path) {
        if (!path) return '';
        return path.replace(/\\/g, '/').split('/').pop();
    }

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Show tool execution indicator (legacy - redirects to action card)
     */
    showToolIndicator(toolName) {
        this.showActionCard(toolName, {}, 'running');
    }

    /**
     * Hide tool execution indicator (legacy - redirects to update)
     */
    hideToolIndicator(toolName) {
        this.updateActionCard(toolName, 'complete');
    }

    /**
     * Finalize streaming message - preserve action cards and append final text
     */
    finalizeStreamingMessage(content) {
        if (!this.currentStreamingElement) return;

        this.currentStreamingElement.classList.remove('streaming');
        const contentEl = this.currentStreamingElement.querySelector('.message-content');

        if (contentEl) {
            contentEl.classList.remove('streaming-content');

            // Remove streaming cursor
            const cursor = contentEl.querySelector('.streaming-cursor');
            if (cursor) cursor.remove();

            // Remove the streaming-text wrapper cursor if present
            const streamingText = contentEl.querySelector('.streaming-text');
            if (streamingText) {
                const innerCursor = streamingText.querySelector('.streaming-cursor');
                if (innerCursor) innerCursor.remove();
            }

            // NOTE: Content is already rendered by updateStreamingMessage during streaming
            // We just need to finalize (remove cursor, add buttons) - no need to re-append content

            // Add action buttons
            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'message-actions';
            actionsDiv.innerHTML = `
                <button data-action="copy">Copy</button>
                <button data-action="insert">Insert</button>
            `;
            contentEl.parentElement.appendChild(actionsDiv);

            // Add handlers
            const contentToUse = this.stripThinkTags(content);
            actionsDiv.querySelectorAll('button').forEach(btn => {
                btn.addEventListener('click', () => {
                    const action = btn.dataset.action;
                    const code = this.extractCode(contentToUse);
                    if (action === 'copy') {
                        navigator.clipboard.writeText(code || contentToUse);
                    } else if (action === 'insert' && code) {
                        window.editorManager?.insertAtCursor(code);
                    }
                });
            });
        }

        // Store in messages (without think tags)
        const cleanForStorage = this.stripThinkTags(content);
        this.messages.push({ role: 'assistant', content: cleanForStorage, timestamp: new Date() });

        this.currentStreamingElement = null;
    }

    /**
     * Strip <think>...</think> tags from content
     */
    stripThinkTags(content) {
        if (!content) return '';
        // Remove <think>...</think> blocks (including multiline)
        return content.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();
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

        // Model Selector click
        const modelSelector = document.getElementById('modelSelector');
        modelSelector?.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleModelDropdown();
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', () => {
            const dropdown = document.getElementById('modelDropdown');
            if (dropdown) dropdown.style.display = 'none';
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
     * Set current model (indicator update only)
     */
    setModel(model) {
        this.currentModel = model;
        // Update the small indicator below input
        const indicator = document.getElementById('currentModel');
        if (indicator) {
            indicator.textContent = model === 'auto' ? 'Auto' : model;
        }
    }

    /**
     * Load available models from backend
     */
    async loadAvailableModels() {
        try {
            const baseUrl = window.CONFIG?.API_URL || 'http://localhost:8000';
            const response = await fetch(`${baseUrl}/api/agent/models/list`);
            if (response.ok) {
                const data = await response.json();
                this.renderModelOptions(data.models);
            }
        } catch (error) {
            console.warn('Failed to load models:', error);
        }
    }

    /**
     * Render model options in dropdown
     */
    renderModelOptions(models) {
        const optionsContainer = document.getElementById('modelDropdownOptions');
        if (!optionsContainer) return;

        // Reserve Auto option
        const autoOption = `
            <div class="model-option ${this.selectedModel === 'Auto' ? 'selected' : ''}" data-model="Auto">
                <i data-lucide="zap"></i>
                <span>Auto (Recommended)</span>
            </div>
        `;

        let html = autoOption;

        models.forEach(m => {
            const modelValue = `${m.provider}/${m.model_key}`;
            const isSelected = this.selectedModel === modelValue;
            html += `
                <div class="model-option ${isSelected ? 'selected' : ''}" data-model="${modelValue}">
                    <i data-lucide="cpu"></i>
                    <span>${m.display_name}</span>
                </div>
            `;
        });

        optionsContainer.innerHTML = html;

        // Re-initialize icons
        if (window.lucide) {
            window.lucide.createIcons({
                attrs: {
                    class: 'lucide-icon'
                },
                nameAttr: 'data-lucide'
            });
        }

        // Add click listeners to options
        optionsContainer.querySelectorAll('.model-option').forEach(opt => {
            opt.addEventListener('click', () => {
                this.selectModel(opt.dataset.model);
            });
        });
    }

    /**
     * Toggle model selection dropdown
     */
    toggleModelDropdown() {
        const dropdown = document.getElementById('modelDropdown');
        if (!dropdown) return;

        if (dropdown.style.display === 'none') {
            dropdown.style.display = 'flex';
        } else {
            dropdown.style.display = 'none';
        }
    }

    /**
     * Select a model
     */
    selectModel(modelValue) {
        this.selectedModel = modelValue;
        localStorage.setItem('quasar_selected_model', modelValue);

        // Update UI
        this.updateModelSelectionUI();

        // Refresh dropdown selection classes
        document.querySelectorAll('.model-option').forEach(opt => {
            opt.classList.toggle('selected', opt.dataset.model === modelValue);
        });

        // Hide dropdown
        document.getElementById('modelDropdown').style.display = 'none';
    }

    /**
     * Update model selection text in status bar
     */
    updateModelSelectionUI() {
        const displayEl = document.getElementById('selectedModel');
        if (displayEl) {
            displayEl.textContent = this.selectedModel;
        }
    }
}

// Create global instance
window.agentManager = new AgentManager();
