/**
 * AI Code Editor - Agent Module
 * Handles AI chat functionality
 */

class AgentManager {
    constructor() {
        this.messages = [];
        this.chatHistory = []; // Store conversation sessions
        this.isLoading = false;
        this.isStreaming = false;  // Track if currently streaming (for button toggle)
        this.currentModel = 'auto'; // Model being used by AI (indicator)
        this.selectedModel = localStorage.getItem('quasar_selected_model') || 'Auto'; // User selected model
        this.streamingEnabled = true;  // Enable streaming by default
        this.currentStreamingElement = null;  // Track streaming message element
        this.currentEventSource = null;  // Track EventSource for cancellation
        this.currentAbortController = null;  // For stopping streaming

        this.STORAGE_KEY = 'quasar_chat_history';
        this.MAX_HISTORY_SESSIONS = 20; // Keep last 20 conversations
        this.currentSessionId = Date.now().toString();

        this.toolState = new Map(); // Track state between tool_start and tool_complete
    }

    /**
     * Initialize the agent
     */
    init() {
        this.setupEventListeners();
        this.autoResizeTextarea();
        this.updateModelSelectionUI();
        this.loadAvailableModels();
        this.loadChatHistory();
        this.configureMarkdown();
    }

    configureMarkdown() {
        if (!window.marked) return;

        const codeRenderer = (codeOrToken, language) => {
            let code, lang;
            if (typeof codeOrToken === 'object' && codeOrToken !== null) {
                code = codeOrToken.text || '';
                lang = codeOrToken.lang || '';
            } else {
                code = codeOrToken || '';
                lang = language || '';
            }

            const validLanguage = (window.hljs && hljs.getLanguage(lang)) ? lang : 'plaintext';
            const highlighted = (window.hljs && code) ? hljs.highlight(code, { language: validLanguage }).value : code;

            return `<pre style="position: relative;"><div class="code-copy-btn" title="Copy code" style="opacity: 0.8 !important;"><i data-lucide="copy"></i></div><code class="hljs language-${validLanguage}">${highlighted}</code></pre>`;
        };

        const options = {
            highlight: (code, lang) => {
                if (window.hljs && hljs.getLanguage(lang)) {
                    return hljs.highlight(code, { language: lang }).value;
                }
                return code;
            },
            headerIds: false,
            mangle: false,
            breaks: true,
            sanitize: false
        };

        // Modern marked (v4+) uses marked.use()
        if (typeof marked.use === 'function') {
            marked.use({
                renderer: {
                    code: codeRenderer
                }
            });
        }

        // Fallback for older versions or additional options
        const renderer = new marked.Renderer();
        renderer.code = codeRenderer;
        options.renderer = renderer;

        marked.setOptions(options);
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

        // Show thinking toast
        this.thinkingToast = window.toast?.info('AI is thinking...', { duration: 0 });

        // Create abort controller for cancellation
        this.currentAbortController = new AbortController();

        // Set streaming state and update button
        this.isStreaming = true;
        this.updateSendButton();

        try {
            // Get user API keys from settings
            const apiKeys = window.settingsManager?.getApiKeys() || {};

            const response = await fetch(`${baseUrl}/api/agent/chat/stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Groq-Api-Keys': JSON.stringify(apiKeys.groq || []),
                    'X-OpenAI-Api-Keys': JSON.stringify(apiKeys.openai || []),
                    'X-Anthropic-Api-Keys': JSON.stringify(apiKeys.anthropic || []),
                    'X-Cerebras-Api-Keys': JSON.stringify(apiKeys.cerebras || []),
                    'X-Ollama-Url': apiKeys.ollamaUrl || ''
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
                                // Dismiss thinking toast on first token
                                if (this.thinkingToast) {
                                    window.toast?.dismiss(this.thinkingToast);
                                    this.thinkingToast = null;
                                }
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

            // Handle case where stream ends without 'done' event
            if (this.isStreaming) {
                this.finalizeStreamingMessage(currentContent);
            }
        } catch (error) {
            console.error('Streaming error:', error);
            if (this.isStreaming) {
                this.finalizeStreamingMessage(`Error: ${error.message}`);
            }
        } finally {
            this.isStreaming = false;
            this.updateSendButton();
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
            <div class="message-content streaming-content">
                <span class="streaming-cursor">▊</span>
            </div>
        `;
        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

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
        this.isStreaming = false;
        this.updateSendButton();
    }

    /**
     * Update send button appearance based on streaming state
     */
    updateSendButton() {
        const btn = document.getElementById('sendBtn');
        if (!btn) return;

        if (this.isStreaming) {
            btn.innerHTML = '<i data-lucide="square"></i>';
            btn.title = 'Stop';
            btn.classList.add('stop-mode');
            // Ensure button is enabled for stopping even if setLoading(true) disabled it
            btn.disabled = false;
        } else {
            btn.innerHTML = '<i data-lucide="send"></i>';
            btn.title = 'Send';
            btn.classList.remove('stop-mode');
        }
        if (window.lucide) lucide.createIcons();
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
                console.log(`🔄 Iteration ${data.current}/${data.max} (${data.remaining} remaining)`);
                break;
            case 'iteration_warning':
                console.log(`⚠️ Iteration warning: ${data.message}`);
                // Show toast warning
                if (window.toast) {
                    window.toast.warning(`⚠️ Last tool iteration! Agent will summarize progress.`);
                }
                break;
            case 'message':
                // Display narrative message inline
                console.log(`💬 ${data.content}`);
                this.appendProgressMessage(data.content);
                break;
            case 'tool_start':
                console.log(`🔧 Starting tool: ${data.tool}`);
                const cardId = this.showActionCard(data.tool, data.args || {}, 'running');

                // For file-modifying tools, try to capture "before" state (must await)
                const modificationTools = ['modify_file', 'patch_file', 'write_to_file', 'create_file'];
                if (modificationTools.includes(data.tool)) {
                    const filePath = data.args?.path || data.args?.file_path;
                    if (filePath && cardId) {
                        // Capture before state immediately (don't await to avoid blocking stream)
                        this.captureBeforeState(cardId, filePath).catch(err => console.warn('captureBeforeState error:', err));
                    }
                }
                break;
            case 'tool_complete':
                console.log(`✅ Tool complete: ${data.tool}`);
                this.updateActionCard(data.tool, 'complete', data.result);

                // Special handling for suggest_command - render as copyable command
                if (data.tool === 'suggest_command') {
                    let result = data.result;
                    if (typeof result === 'string') {
                        try { result = JSON.parse(result); } catch (e) { }
                    }
                    if (result && result.command) {
                        this.appendSuggestedCommand(result.command, result.description);
                    }
                }

                // Immediately refresh file tree for file-modifying tools
                const fileTools = ['create_file', 'modify_file', 'delete_file', 'move_file', 'patch_file'];
                if (fileTools.includes(data.tool) && window.fileTreeManager) {
                    console.log(`🔄 Refreshing file tree after ${data.tool}`);
                    window.fileTreeManager.loadFileTree();

                    // Parse result if it's a string
                    let result = data.result;
                    if (typeof result === 'string') {
                        try {
                            result = JSON.parse(result);
                        } catch (e) {
                            console.log('⚠ Could not parse result:', e);
                        }
                    }

                    // If a file was modified, reload it in the editor if it's open
                    if (result && result.path && window.editorManager && window.fileTreeManager?.rootPath) {
                        // Convert relative path to absolute
                        let absolutePath = result.path;
                        if (!absolutePath.includes(':\\') && !absolutePath.startsWith('/')) {
                            // It's a relative path, make it absolute using Windows backslashes
                            absolutePath = `${window.fileTreeManager.rootPath}\\${result.path}`;
                        }
                        console.log(`📝 Auto-reload triggered for: ${absolutePath}`);
                        window.editorManager.reloadFile(absolutePath);

                        // Mark new files with badge
                        if (data.tool === 'create_file') {
                            window.fileTreeManager.markAsNew(result.path);
                        }
                    } else {
                        console.log(`⚠ No path to reload. result:`, result, 'rootPath:', window.fileTreeManager?.rootPath);
                    }
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
     * Append a suggested command block with copy button
     */
    appendSuggestedCommand(command, description = '') {
        if (!this.currentStreamingElement) return;

        const contentEl = this.currentStreamingElement.querySelector('.message-content');
        if (contentEl) {
            const commandId = `cmd-${Date.now()}`;
            const commandEl = document.createElement('div');
            commandEl.className = 'suggested-command-block';
            commandEl.innerHTML = `
                <div class="suggested-command-header">
                    <span class="suggested-command-label">
                        <i data-lucide="terminal"></i>
                        ${description || 'Run in terminal'}
                    </span>
                    <button class="copy-command-btn" data-command="${this.escapeHtml(command)}" title="Copy command">
                        <i data-lucide="copy"></i>
                        <span>Copy</span>
                    </button>
                </div>
                <pre class="suggested-command-code"><code>${this.escapeHtml(command)}</code></pre>
            `;

            // Add click handler for copy button
            const copyBtn = commandEl.querySelector('.copy-command-btn');
            copyBtn.addEventListener('click', () => {
                navigator.clipboard.writeText(command);
                copyBtn.innerHTML = '<i data-lucide="check"></i><span>Copied!</span>';
                if (window.lucide) lucide.createIcons();
                setTimeout(() => {
                    copyBtn.innerHTML = '<i data-lucide="copy"></i><span>Copy</span>';
                    if (window.lucide) lucide.createIcons();
                }, 2000);
            });

            contentEl.appendChild(commandEl);
            if (window.lucide) lucide.createIcons();

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
     * Capture the "before" state of a file before a tool modifies it
     */
    async captureBeforeState(cardId, filePath) {
        try {
            // Check if open in editor first (faster, has unsaved changes)
            let content = null;
            if (window.editorManager) {
                const openFiles = window.editorManager.openFiles;
                // Try to find matching path
                for (const [path, data] of openFiles.entries()) {
                    if (path === filePath || path.endsWith(filePath) || filePath.endsWith(path)) {
                        content = data.model.getValue();
                        break;
                    }
                }
            }

            // If not in editor, fetch from API
            if (content === null) {
                const response = await fetch(`${CONFIG.API_BASE_URL}/files/read?path=${encodeURIComponent(filePath)}`);
                if (response.ok) {
                    const data = await response.json();
                    content = data.content;
                }
            }

            if (content !== null) {
                this.toolState.set(cardId, { beforeContent: content, filePath });
            }
        } catch (error) {
            console.warn('Failed to capture before state:', error);
        }
    }

    /**
     * Show styled action card for tool execution
     */
    showActionCard(toolName, args, status) {
        if (!this.currentStreamingElement) return null;

        const contentEl = this.currentStreamingElement.querySelector('.message-content');
        if (!contentEl) return null;

        const info = this.getToolDisplayInfo(toolName, args);
        const detail = info.getDetail(args);
        const cardId = `action-${toolName}-${Date.now()}`;

        // Create action card
        const card = document.createElement('div');
        card.className = `action-card action-card-${status}`;
        card.id = cardId;
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
        if (messagesContainer) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }

        return cardId;
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

        // Handle diff display for file modifications
        const toolInfo = this.toolState.get(card.id);
        if (status === 'complete' && toolInfo && window.diffViewer) {
            // Try to get afterContent from result or fetch from API
            this.getAfterContentAndShowDiff(card, toolInfo, result, toolName);
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
     * Get after content and show diff button
     */
    async getAfterContentAndShowDiff(card, toolInfo, result, toolName) {
        let afterContent = null;

        // Extract afterContent from result if possible
        if (result) {
            let parsedResult = result;
            if (typeof result === 'string' && (result.startsWith('{') || result.startsWith('['))) {
                try { parsedResult = JSON.parse(result); } catch (e) { }
            }

            if (parsedResult.content) afterContent = parsedResult.content;
            else if (typeof parsedResult === 'string' && toolName === 'read_file') afterContent = parsedResult;
        }

        // If we couldn't get afterContent from result, fetch from file API
        if (afterContent === null && toolInfo.filePath) {
            try {
                const response = await fetch(`${CONFIG.API_BASE_URL}/files/read?path=${encodeURIComponent(toolInfo.filePath)}`);
                if (response.ok) {
                    const data = await response.json();
                    afterContent = data.content;
                }
            } catch (error) {
                console.warn('Failed to fetch after content:', error);
            }
        }

        if (afterContent !== null && afterContent !== toolInfo.beforeContent) {
            const diffBtn = document.createElement('button');
            diffBtn.className = 'btn-show-diff';
            diffBtn.innerHTML = '<i data-lucide="diff"></i><span>Show Changes</span>';
            card.appendChild(diffBtn);

            if (window.lucide) lucide.createIcons();

            let diffContainer = null;
            diffBtn.addEventListener('click', () => {
                if (diffContainer) {
                    diffContainer.style.display = diffContainer.style.display === 'none' ? 'block' : 'none';
                    diffBtn.querySelector('span').textContent = diffContainer.style.display === 'none' ? 'Show Changes' : 'Hide Changes';
                    return;
                }

                diffContainer = document.createElement('div');
                diffContainer.innerHTML = window.diffViewer.renderLineDiff(toolInfo.beforeContent, afterContent, toolInfo.filePath);
                card.appendChild(diffContainer);
                diffBtn.querySelector('span').textContent = 'Hide Changes';
            });
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

            if (window.lucide) lucide.createIcons();
        }

        // Store in messages (without think tags)
        const cleanForStorage = this.stripThinkTags(content);
        this.messages.push({ role: 'assistant', content: cleanForStorage, timestamp: new Date() });

        this.currentStreamingElement = null;

        // Reset streaming state and update button
        this.isStreaming = false;
        this.updateSendButton();
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

        // Auto-save chat history
        this.saveChatHistory();
    }

    /**
     * Format message content (Advanced markdown with syntax highlighting)
     */
    formatMessage(content) {
        if (!content) return '';

        let html = '';
        if (window.marked) {
            try {
                // Use marked for high-fidelity parsing
                html = marked.parse(content);
            } catch (error) {
                console.error('Markdown parsing error:', error);
                html = this.fallbackFormatMessage(content);
            }
        } else {
            html = this.fallbackFormatMessage(content);
        }

        // BRUTE FORCE: If copy button is missing from any <pre> tags, inject it
        // This handles cases where marked renderer is ignored
        if (html.includes('<pre>') && !html.includes('code-copy-btn')) {
            html = html.replace(/<pre>/g, '<pre style="position: relative;"><div class="code-copy-btn" title="Copy code" style="opacity: 0.8 !important;"><i data-lucide="copy"></i></div>');
        }

        // After parsing, we might need to re-initialize Lucide icons in the generated HTML
        setTimeout(() => {
            if (window.lucide) lucide.createIcons();
        }, 0);

        return html;
    }

    /**
     * Fallback formatter if marked.js is not loaded
     */
    fallbackFormatMessage(content) {
        // Escape HTML
        let formatted = content
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        // Basic Code blocks with Copy Button
        formatted = formatted.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
            return `<pre style="position: relative;"><div class="code-copy-btn" title="Copy code" style="opacity: 0.8 !important;"><i data-lucide="copy"></i></div><code class="language-${lang}">${code.trim()}</code></pre>`;
        });

        // Inline code
        formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Bold/Italic
        formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        formatted = formatted.replace(/\*([^*]+)\*/g, '<em>$1</em>');

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

        // Send/Stop toggle button click
        sendBtn?.addEventListener('click', () => {
            if (this.isStreaming) {
                // Currently streaming - stop it
                this.stopStreaming();
            } else {
                // Not streaming - send message
                this.sendMessage(input.value);
            }
        });

        // Send on Enter, new line on Shift+Enter
        input?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (!this.isStreaming) {
                    this.sendMessage(input.value);
                }
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

        // New Chat button
        const newChatBtn = document.getElementById('newChatBtn');
        newChatBtn?.addEventListener('click', () => {
            this.startNewSession();
        });

        // Chat History button
        const chatHistoryBtn = document.getElementById('chatHistoryBtn');
        chatHistoryBtn?.addEventListener('click', () => {
            this.showHistoryModal();
        });

        // Close history modal
        const closeHistoryBtn = document.getElementById('closeChatHistoryBtn');
        closeHistoryBtn?.addEventListener('click', () => {
            this.hideHistoryModal();
        });

        // Clear all history button
        const clearHistoryBtn = document.getElementById('clearHistoryBtn');
        clearHistoryBtn?.addEventListener('click', () => {
            if (confirm('Clear all chat history? This cannot be undone.')) {
                this.clearAllHistory();
                this.hideHistoryModal();
            }
        });

        // Close modal on overlay click
        const historyModal = document.getElementById('chatHistoryModal');
        historyModal?.addEventListener('click', (e) => {
            if (e.target === historyModal) {
                this.hideHistoryModal();
            }
        });

        // Event Delegation for Code Copy Buttons
        document.getElementById('chatMessages')?.addEventListener('click', (e) => {
            const copyBtn = e.target.closest('.code-copy-btn');
            if (copyBtn) {
                e.preventDefault();
                e.stopPropagation();

                const pre = copyBtn.closest('pre');
                const codeEl = pre?.querySelector('code');

                if (codeEl) {
                    const code = codeEl.innerText || codeEl.textContent;
                    navigator.clipboard.writeText(code).then(() => {
                        copyBtn.classList.add('copied');
                        const originalHTML = copyBtn.innerHTML;
                        copyBtn.innerHTML = '<i data-lucide="check"></i>';
                        if (window.lucide) lucide.createIcons();

                        setTimeout(() => {
                            copyBtn.classList.remove('copied');
                            copyBtn.innerHTML = originalHTML;
                            if (window.lucide) lucide.createIcons();
                        }, 2000);
                    }).catch(err => {
                        console.error('Failed to copy code:', err);
                        window.toast?.error('Failed to copy code');
                    });
                }
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

    // ==========================================
    // Chat History Persistence Methods
    // ==========================================

    /**
     * Load chat history from localStorage
     */
    loadChatHistory() {
        try {
            const stored = localStorage.getItem(this.STORAGE_KEY);
            if (stored) {
                this.chatHistory = JSON.parse(stored);
                console.log(`📚 Loaded ${this.chatHistory.length} chat sessions from history`);
            }
        } catch (error) {
            console.error('Failed to load chat history:', error);
            this.chatHistory = [];
        }
    }

    /**
     * Save current messages to chat history
     */
    saveChatHistory() {
        if (this.messages.length === 0) return;

        try {
            // Find or create current session
            let sessionIndex = this.chatHistory.findIndex(s => s.id === this.currentSessionId);

            const session = {
                id: this.currentSessionId,
                timestamp: new Date().toISOString(),
                messages: this.messages.map(m => ({
                    role: m.role,
                    content: m.content,
                    timestamp: m.timestamp?.toISOString() || new Date().toISOString()
                })),
                // Create a title from first user message
                title: this.getSessionTitle()
            };

            if (sessionIndex >= 0) {
                // Update existing session
                this.chatHistory[sessionIndex] = session;
            } else {
                // Add new session
                this.chatHistory.unshift(session);

                // Trim to max sessions
                if (this.chatHistory.length > this.MAX_HISTORY_SESSIONS) {
                    this.chatHistory = this.chatHistory.slice(0, this.MAX_HISTORY_SESSIONS);
                }
            }

            localStorage.setItem(this.STORAGE_KEY, JSON.stringify(this.chatHistory));
            console.log('💾 Chat saved to history');
        } catch (error) {
            console.error('Failed to save chat history:', error);
        }
    }

    /**
     * Get session title from first user message
     */
    getSessionTitle() {
        const firstUserMsg = this.messages.find(m => m.role === 'user');
        if (firstUserMsg) {
            const title = firstUserMsg.content.substring(0, 50);
            return title.length < firstUserMsg.content.length ? title + '...' : title;
        }
        return 'New Chat';
    }

    /**
     * Restore a previous chat session
     */
    restoreSession(sessionId) {
        const session = this.chatHistory.find(s => s.id === sessionId);
        if (!session) {
            console.error('Session not found:', sessionId);
            return;
        }

        // Clear current chat UI
        const messagesContainer = document.getElementById('chatMessages');
        messagesContainer.innerHTML = '';

        // Restore messages
        this.messages = [];
        this.currentSessionId = session.id;

        session.messages.forEach(msg => {
            this.addMessage(msg.role, msg.content);
        });

        console.log(`📖 Restored session: ${session.title}`);
    }

    /**
     * Start a new chat session
     */
    startNewSession() {
        // Save current session first
        this.saveChatHistory();

        // Clear current chat
        this.messages = [];
        this.currentSessionId = Date.now().toString();

        // Clear UI
        const messagesContainer = document.getElementById('chatMessages');
        messagesContainer.innerHTML = `
            <div class="welcome-message">
                <h3>👋 Hello! I'm your AI coding assistant.</h3>
                <p>I can help you with:</p>
                <ul>
                    <li>📝 Writing and editing code</li>
                    <li>🐛 Debugging and fixing issues</li>
                    <li>💡 Explaining code concepts</li>
                    <li>🚀 Running terminal commands</li>
                </ul>
                <p>Open a folder to get started, then ask me anything!</p>
            </div>
        `;

        console.log('🆕 Started new chat session');
    }

    /**
     * Clear all chat history
     */
    clearAllHistory() {
        this.chatHistory = [];
        localStorage.removeItem(this.STORAGE_KEY);
        console.log('🗑️ Cleared all chat history');
    }

    /**
     * Get chat history for display
     */
    getChatHistory() {
        return this.chatHistory.map(session => ({
            id: session.id,
            title: session.title,
            timestamp: session.timestamp,
            messageCount: session.messages.length
        }));
    }

    /**
     * Show chat history modal
     */
    showHistoryModal() {
        const modal = document.getElementById('chatHistoryModal');
        if (modal) {
            modal.classList.add('active');
            this.renderHistoryList();
            // Re-init lucide icons
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
        }
    }

    /**
     * Hide chat history modal
     */
    hideHistoryModal() {
        const modal = document.getElementById('chatHistoryModal');
        if (modal) {
            modal.classList.remove('active');
        }
    }

    /**
     * Render chat history list in modal
     */
    renderHistoryList() {
        const listEl = document.getElementById('historyList');
        if (!listEl) return;

        const history = this.getChatHistory();

        if (history.length === 0) {
            listEl.innerHTML = `
                <div class="history-empty">
                    <i data-lucide="message-circle"></i>
                    <p>No chat history yet</p>
                    <span>Your conversations will appear here</span>
                </div>
            `;
            return;
        }

        listEl.innerHTML = history.map(session => {
            const date = new Date(session.timestamp);
            const dateStr = date.toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
            const isCurrent = session.id === this.currentSessionId;

            return `
                <div class="history-item ${isCurrent ? 'current' : ''}" data-session-id="${session.id}">
                    <div class="history-item-content">
                        <div class="history-title">${this.escapeHtml(session.title)}</div>
                        <div class="history-meta">
                            <span class="history-date">${dateStr}</span>
                            <span class="history-count">${session.messageCount} messages</span>
                        </div>
                    </div>
                    ${isCurrent ? '<span class="current-badge">Current</span>' : ''}
                </div>
            `;
        }).join('');

        // Add click handlers
        listEl.querySelectorAll('.history-item:not(.current)').forEach(item => {
            item.addEventListener('click', () => {
                const sessionId = item.dataset.sessionId;
                this.restoreSession(sessionId);
                this.hideHistoryModal();
            });
        });
    }
}

// Create global instance
window.agentManager = new AgentManager();
