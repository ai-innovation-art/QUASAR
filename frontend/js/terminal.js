/**
 * AI Code Editor - Terminal Module
 * Handles xterm.js terminal functionality with WebSocket connection
 */

class TerminalManager {
    constructor() {
        this.terminal = null;
        this.fitAddon = null;
        this.isCollapsed = false;
        this.commandHistory = [];
        this.historyIndex = -1;
        this.websocket = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
    }

    /**
     * Initialize the terminal
     */
    init() {
        const container = document.getElementById('terminalContainer');

        // Create terminal instance
        this.terminal = new Terminal({
            ...CONFIG.TERMINAL,
            cols: 80,
            rows: 10,
            cursorBlink: true
        });

        // Create fit addon for auto-sizing
        this.fitAddon = new FitAddon.FitAddon();
        this.terminal.loadAddon(this.fitAddon);

        // Open terminal in container
        this.terminal.open(container);

        // Fit to container
        this.fit();

        // Write initial message
        this.writeWelcome();

        // Setup event listeners
        this.setupEventListeners();

        // Connect to WebSocket terminal
        this.connectWebSocket();
    }

    /**
     * Connect to WebSocket terminal
     */
    connectWebSocket() {
        // Close existing connection first
        if (this.websocket) {
            this.websocket.onclose = null; // Prevent auto-reconnect
            this.websocket.close();
            this.websocket = null;
            this.isConnected = false;
        }

        // Clear terminal and show connecting message
        if (this.terminal) {
            this.terminal.clear();
            this.terminal.writeln('\x1b[33m🔄 Connecting to terminal...\x1b[0m');
        }

        const wsUrl = CONFIG.API_BASE_URL.replace('http', 'ws') + '/terminal/ws/terminal';

        try {
            this.websocket = new WebSocket(wsUrl);

            this.websocket.onopen = () => {
                this.isConnected = true;
                this.reconnectAttempts = 0;
                console.log('✅ Terminal WebSocket connected');
            };

            this.websocket.onmessage = (event) => {
                // Write received data to terminal
                this.terminal.write(event.data);
            };

            this.websocket.onclose = () => {
                this.isConnected = false;
                console.log('🔌 Terminal WebSocket disconnected');

                // Try to reconnect only if not manually disconnected
                if (this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.reconnectAttempts++;
                    setTimeout(() => this.connectWebSocket(), 2000);
                }
            };

            this.websocket.onerror = (error) => {
                console.error('Terminal WebSocket error:', error);
            };

        } catch (error) {
            console.error('Failed to connect WebSocket:', error);
        }
    }

    /**
     * Send data to WebSocket
     */
    sendToWebSocket(data) {
        if (this.websocket && this.isConnected) {
            this.websocket.send(data);
        }
    }

    /**
     * Run a command in the terminal (like VS Code)
     * This sends the command to WebSocket and executes it
     */
    runCommand(command) {
        if (!this.isConnected) {
            this.writeWarning('Terminal not connected. Trying to reconnect...');
            this.connectWebSocket();
            return;
        }

        // Send the command followed by Enter
        this.sendToWebSocket(command + '\r');
    }

    /**
     * Change directory in terminal
     */
    changeDirectory(path) {
        this.runCommand(`cd "${path}"`);
    }

    /**
     * Write welcome message
     */
    writeWelcome() {
        this.terminal.writeln('\x1b[1;36m╔════════════════════════════════════════╗\x1b[0m');
        this.terminal.writeln('\x1b[1;36m║\x1b[0m   \x1b[1;33mAI Code Editor Terminal\x1b[0m              \x1b[1;36m║\x1b[0m');
        this.terminal.writeln('\x1b[1;36m╚════════════════════════════════════════╝\x1b[0m');
        this.terminal.writeln('');
        this.terminal.writeln('\x1b[32m✓\x1b[0m Terminal ready. Connecting to backend...');
        this.terminal.writeln('');
    }

    /**
     * Write text to terminal
     */
    write(text) {
        if (this.terminal) {
            this.terminal.write(text);
        }
    }

    /**
     * Write line to terminal
     */
    writeln(text) {
        if (this.terminal) {
            this.terminal.writeln(text);
        }
    }

    /**
     * Write success message (green)
     */
    writeSuccess(text) {
        this.writeln(`\x1b[32m${text}\x1b[0m`);
    }

    /**
     * Write error message (red)
     */
    writeError(text) {
        this.writeln(`\x1b[31m${text}\x1b[0m`);
    }

    /**
     * Write warning message (yellow)
     */
    writeWarning(text) {
        this.writeln(`\x1b[33m${text}\x1b[0m`);
    }

    /**
     * Write info message (blue)
     */
    writeInfo(text) {
        this.writeln(`\x1b[34m${text}\x1b[0m`);
    }

    /**
     * Write command with timestamp
     */
    writeCommand(command) {
        const timestamp = new Date().toLocaleTimeString();
        this.writeln(`\x1b[90m[${timestamp}]\x1b[0m \x1b[1;36m$\x1b[0m ${command}`);
    }

    /**
     * Write execution result
     */
    writeResult(output, error = false) {
        if (error) {
            this.writeError(output);
        } else {
            this.writeln(output);
        }
    }

    /**
     * Write execution header
     */
    writeExecutionHeader(filename, language) {
        this.writeln('');
        this.writeln('\x1b[90m─────────────────────────────────────────\x1b[0m');
        this.writeln(`\x1b[1;35m▶ Running:\x1b[0m ${filename} \x1b[90m(${language})\x1b[0m`);
        this.writeln('\x1b[90m─────────────────────────────────────────\x1b[0m');
    }

    /**
     * Write execution footer
     */
    writeExecutionFooter(exitCode, duration) {
        this.writeln('');
        this.writeln('\x1b[90m─────────────────────────────────────────\x1b[0m');
        if (exitCode === 0) {
            this.writeln(`\x1b[32m✓ Process finished\x1b[0m \x1b[90m(${duration}ms)\x1b[0m`);
        } else {
            this.writeln(`\x1b[31m✗ Process failed with exit code ${exitCode}\x1b[0m \x1b[90m(${duration}ms)\x1b[0m`);
        }
        this.writeln('');
    }

    /**
     * Clear terminal
     */
    clear() {
        if (this.terminal) {
            this.terminal.clear();
            // Send clear command to backend if connected
            if (this.isConnected) {
                this.sendToWebSocket('clear\r');
            }
        }
    }

    /**
     * Toggle terminal visibility
     */
    toggle() {
        const wrapper = document.getElementById('terminalWrapper');
        const toggleBtn = document.getElementById('toggleTerminalBtn');

        this.isCollapsed = !this.isCollapsed;
        wrapper.classList.toggle('collapsed', this.isCollapsed);

        // Update toggle button icon
        const icon = toggleBtn.querySelector('[data-lucide]');
        if (icon) {
            icon.setAttribute('data-lucide', this.isCollapsed ? 'chevron-up' : 'chevron-down');
            lucide.createIcons();
        }

        // Re-layout editor
        setTimeout(() => {
            window.editorManager?.layout();
            if (!this.isCollapsed) {
                this.fit();
            }
        }, 100);
    }

    /**
     * Fit terminal to container
     */
    fit() {
        if (this.fitAddon && !this.isCollapsed) {
            try {
                this.fitAddon.fit();
            } catch (e) {
                // Ignore fit errors during initialization
            }
        }
    }

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // Send terminal input to WebSocket
        this.terminal.onData(data => {
            this.sendToWebSocket(data);
        });

        // Clear button
        document.getElementById('clearTerminalBtn')?.addEventListener('click', () => {
            this.clear();
        });

        // Toggle button
        document.getElementById('toggleTerminalBtn')?.addEventListener('click', () => {
            this.toggle();
        });

        // Handle resize
        window.addEventListener('resize', () => {
            this.fit();
        });

        // Keyboard shortcut for toggle
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'j') {
                e.preventDefault();
                this.toggle();
            }
        });
    }

    /**
     * Dispose terminal
     */
    dispose() {
        if (this.websocket) {
            this.websocket.close();
        }
        if (this.terminal) {
            this.terminal.dispose();
        }
    }
}

// Create global instance
window.terminalManager = new TerminalManager();
