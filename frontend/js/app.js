/**
 * AI Code Editor - Main Application
 * Entry point that initializes all modules
 */

class App {
    constructor() {
        this.initialized = false;
        this.theme = 'dark';
    }

    /**
     * Initialize the application
     */
    async init() {
        console.log('🚀 Initializing AI Code Editor...');

        try {
            // Show loading state
            this.showLoading(true);

            // Initialize Monaco Editor first (async)
            console.log('📝 Loading Monaco Editor...');
            await window.editorManager.init();
            console.log('✅ Monaco Editor ready');

            // Initialize Terminal
            console.log('🖥️ Initializing Terminal...');
            window.terminalManager.init();
            console.log('✅ Terminal ready');

            // Initialize File Tree
            console.log('📁 Initializing File Tree...');
            window.fileTreeManager.init();
            console.log('✅ File Tree ready');

            // Initialize Agent
            console.log('🤖 Initializing AI Agent...');
            window.agentManager.init();
            console.log('✅ AI Agent ready');

            // Initialize Resizers
            console.log('↔️ Initializing Resizers...');
            window.resizerManager.init();
            console.log('✅ Resizers ready');

            // Setup global event listeners
            this.setupEventListeners();

            // Initialize Lucide icons
            if (window.lucide) {
                lucide.createIcons();
            }

            // Load saved theme
            this.loadTheme();

            // Mark as initialized
            this.initialized = true;
            this.showLoading(false);

            console.log('✅ AI Code Editor initialized successfully!');

            // Update status bar
            this.updateConnectionStatus('connected');

        } catch (error) {
            console.error('❌ Failed to initialize:', error);
            this.showError('Failed to initialize the editor. Please refresh the page.');
        }
    }

    /**
     * Setup global event listeners
     */
    setupEventListeners() {
        // Save button
        document.getElementById('saveBtn')?.addEventListener('click', async () => {
            await this.saveCurrentFile();
        });

        // Run button
        document.getElementById('runBtn')?.addEventListener('click', () => {
            this.runCurrentFile();
        });

        // Theme toggle
        document.getElementById('themeToggle')?.addEventListener('click', () => {
            this.toggleTheme();
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Prevent browser defaults for our shortcuts
            if (e.ctrlKey && ['s', 'r', 'k', 'b', 'j', '/'].includes(e.key)) {
                e.preventDefault();
            }
        });

        // Handle page unload with unsaved changes
        window.addEventListener('beforeunload', (e) => {
            if (this.hasUnsavedChanges()) {
                e.preventDefault();
                e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
            }
        });

        // Handle window resize
        window.addEventListener('resize', () => {
            window.editorManager?.layout();
            window.terminalManager?.fit();
        });
    }

    /**
     * Save current file
     */
    async saveCurrentFile() {
        const fileData = await window.editorManager?.saveFile();

        if (fileData) {
            // TODO: Send to backend API
            console.log('Saving file:', fileData.path);

            window.terminalManager?.writeSuccess(`✓ Saved: ${fileData.path}`);

            // Show toast notification
            this.showToast('File saved successfully');
        } else {
            window.terminalManager?.writeWarning('⚠ No file to save');
        }
    }

    /**
     * Run current file (executes in the terminal like VS Code)
     */
    async runCurrentFile() {
        const editor = window.editorManager;
        const terminal = window.terminalManager;

        if (!editor?.getActiveFilePath()) {
            terminal?.writeWarning('⚠ No file open to run');
            return;
        }

        const filePath = editor.getActiveFilePath();
        const fileName = filePath.split(/[\\/]/).pop();
        const language = detectLanguage(filePath);

        // Check if language is supported
        if (!['python', 'javascript'].includes(language)) {
            terminal?.writeWarning(`⚠ Language "${language}" execution not supported yet.`);
            terminal?.writeInfo('Supported languages: Python (.py), JavaScript (.js)');
            return;
        }

        // Save file first before running
        await this.saveCurrentFile();

        // Build the run command based on language
        let command = '';
        if (language === 'python') {
            command = `python "${filePath}"`;
        } else if (language === 'javascript') {
            command = `node "${filePath}"`;
        }

        // Execute in the terminal (like VS Code)
        terminal?.runCommand(command);

        console.log('▶ Running:', command);
    }

    /**
     * Toggle theme
     */
    toggleTheme() {
        this.theme = this.theme === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', this.theme);

        // Update Monaco theme
        window.editorManager?.setTheme(this.theme === 'dark' ? 'vs-dark' : 'vs');

        // Update toggle button icon
        const btn = document.getElementById('themeToggle');
        const icon = btn?.querySelector('[data-lucide]');
        if (icon) {
            icon.setAttribute('data-lucide', this.theme === 'dark' ? 'moon' : 'sun');
            lucide.createIcons();
        }

        // Save preference
        localStorage.setItem('theme', this.theme);
    }

    /**
     * Load saved theme
     */
    loadTheme() {
        const saved = localStorage.getItem('theme');
        if (saved && saved !== this.theme) {
            this.toggleTheme();
        }
    }

    /**
     * Check for unsaved changes
     */
    hasUnsavedChanges() {
        // Check if any open file has unsaved changes
        return window.editorManager?.isDirty() || false;
    }

    /**
     * Update connection status in status bar
     */
    updateConnectionStatus(status) {
        const element = document.getElementById('statusConnection');
        const icon = element?.querySelector('[data-lucide]');
        const text = element?.querySelector('span:last-child');

        if (status === 'connected') {
            element?.classList.add('connected');
            element?.classList.remove('disconnected');
            if (icon) icon.setAttribute('data-lucide', 'wifi');
            if (text) text.textContent = 'Ready';
        } else {
            element?.classList.remove('connected');
            element?.classList.add('disconnected');
            if (icon) icon.setAttribute('data-lucide', 'wifi-off');
            if (text) text.textContent = 'Offline';
        }

        lucide?.createIcons();
    }

    /**
     * Show loading state
     */
    showLoading(show) {
        // Could add a loading overlay here if needed
        if (show) {
            document.body.style.cursor = 'wait';
        } else {
            document.body.style.cursor = '';
        }
    }

    /**
     * Show error message
     */
    showError(message) {
        console.error(message);
        window.terminalManager?.writeError(message);
    }

    /**
     * Show toast notification
     */
    showToast(message, duration = 3000) {
        // Remove existing toast
        document.querySelector('.toast')?.remove();

        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            bottom: 50px;
            left: 50%;
            transform: translateX(-50%);
            padding: 10px 20px;
            background: var(--bg-tertiary);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            font-size: 13px;
            z-index: 1000;
            animation: fadeInUp 0.2s ease;
        `;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'fadeOut 0.2s ease';
            setTimeout(() => toast.remove(), 200);
        }, duration);
    }
}

// Add toast animation styles
const toastStyles = document.createElement('style');
toastStyles.textContent = `
    @keyframes fadeInUp {
        from { opacity: 0; transform: translate(-50%, 10px); }
        to { opacity: 1; transform: translate(-50%, 0); }
    }
    @keyframes fadeOut {
        from { opacity: 1; }
        to { opacity: 0; }
    }
`;
document.head.appendChild(toastStyles);

// Create and initialize app
const app = new App();
document.addEventListener('DOMContentLoaded', () => app.init());
