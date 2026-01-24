/**
 * AI Code Editor - Monaco Editor Module
 * Handles all Monaco Editor functionality
 */

class EditorManager {
    constructor() {
        this.editor = null;
        this.openFiles = new Map(); // path -> { content, model, viewState, dirty }
        this.activeFile = null;
        this.monacoLoaded = false;
    }

    /**
     * Initialize Monaco Editor
     */
    async init() {
        return new Promise((resolve, reject) => {
            // Configure Monaco loader
            require.config({
                paths: {
                    'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs'
                }
            });

            // Load Monaco
            require(['vs/editor/editor.main'], () => {
                this.monacoLoaded = true;
                this.createEditor();
                this.setupEventListeners();
                resolve();
            });
        });
    }

    /**
     * Create the Monaco Editor instance
     */
    createEditor() {
        const container = document.getElementById('editorContainer');

        // Create editor with default configuration
        this.editor = monaco.editor.create(container, {
            value: this.getWelcomeMessage(),
            language: 'markdown',
            ...CONFIG.EDITOR
        });

        // Update cursor position in status bar
        this.editor.onDidChangeCursorPosition((e) => {
            const position = e.position;
            document.getElementById('statusPosition').textContent =
                `Ln ${position.lineNumber}, Col ${position.column}`;
        });

        // Track content changes for dirty state
        this.editor.onDidChangeModelContent(() => {
            if (this.activeFile) {
                const fileData = this.openFiles.get(this.activeFile);
                if (fileData) {
                    fileData.dirty = true;
                    this.updateTabDirtyState(this.activeFile, true);
                }
            }
        });
    }

    /**
     * Get welcome message for empty editor
     */
    getWelcomeMessage() {
        return `# Welcome to AI Code Editor! 🚀

## Getting Started

1. **Open a file** from the file tree on the left
2. **Create a new file** using the + button
3. **Run your code** with Ctrl+R or the Run button
4. **Ask AI for help** in the right panel

## Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Save | Ctrl+S |
| Run Code | Ctrl+R |
| Command Palette | Ctrl+K |
| Toggle File Tree | Ctrl+B |
| Toggle Terminal | Ctrl+J |
| Toggle AI Panel | Ctrl+/ |

## Supported Languages

- Python 🐍
- JavaScript ⚡
- TypeScript 📘
- HTML/CSS 🎨
- And many more...

Happy coding! 💻
`;
    }

    /**
     * Open a file in the editor
     */
    async openFile(filePath, content) {
        // Save current file's view state
        if (this.activeFile) {
            const currentFileData = this.openFiles.get(this.activeFile);
            if (currentFileData) {
                currentFileData.viewState = this.editor.saveViewState();
            }
        }

        // Check if file is already open
        if (this.openFiles.has(filePath)) {
            const fileData = this.openFiles.get(filePath);
            this.editor.setModel(fileData.model);
            if (fileData.viewState) {
                this.editor.restoreViewState(fileData.viewState);
            }
        } else {
            // Create new model for the file
            const language = detectLanguage(filePath);
            const model = monaco.editor.createModel(content, language);

            this.openFiles.set(filePath, {
                content: content,
                model: model,
                viewState: null,
                dirty: false
            });

            this.editor.setModel(model);
            this.createTab(filePath);
        }

        this.activeFile = filePath;
        this.setActiveTab(filePath);
        this.updateStatusBar(filePath);
        document.getElementById('currentFileName').textContent = this.getFileName(filePath);
    }

    /**
     * Save current file
     */
    async saveFile() {
        if (!this.activeFile) return null;

        const fileData = this.openFiles.get(this.activeFile);
        if (!fileData) return null;

        const content = this.editor.getValue();

        try {
            // Save to backend API
            const response = await fetch(`${CONFIG.API_BASE_URL}/files/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    path: this.activeFile,
                    content: content
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to save file');
            }

            // Update local state
            fileData.content = content;
            fileData.dirty = false;
            this.updateTabDirtyState(this.activeFile, false);

            console.log('✅ File saved:', this.activeFile);

            return {
                path: this.activeFile,
                content: content
            };

        } catch (error) {
            console.error('Failed to save file:', error);
            alert('Error saving file: ' + error.message);
            return null;
        }
    }

    /**
     * Get current editor content
     */
    getContent() {
        return this.editor ? this.editor.getValue() : '';
    }

    /**
     * Get selected text
     */
    getSelection() {
        if (!this.editor) return '';
        const model = this.editor.getModel();
        if (!model) return '';  // No file open
        const selection = this.editor.getSelection();
        return model.getValueInRange(selection);
    }

    /**
     * Insert text at cursor position
     */
    insertAtCursor(text) {
        if (!this.editor) return;

        const selection = this.editor.getSelection();
        const id = { major: 1, minor: 1 };
        const op = {
            identifier: id,
            range: selection,
            text: text,
            forceMoveMarkers: true
        };
        this.editor.executeEdits('ai-insert', [op]);
    }

    /**
     * Replace selection with text
     */
    replaceSelection(text) {
        if (!this.editor) return;

        const selection = this.editor.getSelection();
        this.editor.executeEdits('ai-replace', [{
            range: selection,
            text: text,
            forceMoveMarkers: true
        }]);
    }

    /**
     * Create a new tab for a file
     */
    createTab(filePath) {
        const tabsContainer = document.getElementById('tabs');
        const fileName = this.getFileName(filePath);
        const icon = getFileIcon(fileName);

        const tab = document.createElement('div');
        tab.className = 'tab';
        tab.dataset.path = filePath;
        tab.innerHTML = `
            <i data-lucide="${icon}"></i>
            <span class="tab-title">${fileName}</span>
            <span class="tab-close">
                <i data-lucide="x"></i>
            </span>
        `;

        // Tab click handler
        tab.addEventListener('click', (e) => {
            if (!e.target.closest('.tab-close')) {
                this.switchToTab(filePath);
            }
        });

        // Close button handler
        tab.querySelector('.tab-close').addEventListener('click', (e) => {
            e.stopPropagation();
            this.closeTab(filePath);
        });

        tabsContainer.appendChild(tab);

        // Re-initialize Lucide icons
        if (window.lucide) {
            lucide.createIcons();
        }
    }

    /**
     * Switch to a specific tab
     */
    async switchToTab(filePath) {
        const fileData = this.openFiles.get(filePath);
        if (!fileData) return;

        // Save current view state
        if (this.activeFile) {
            const currentData = this.openFiles.get(this.activeFile);
            if (currentData) {
                currentData.viewState = this.editor.saveViewState();
            }
        }

        // Switch to new file
        this.editor.setModel(fileData.model);
        if (fileData.viewState) {
            this.editor.restoreViewState(fileData.viewState);
        }

        this.activeFile = filePath;
        this.setActiveTab(filePath);
        this.updateStatusBar(filePath);
        document.getElementById('currentFileName').textContent = this.getFileName(filePath);
    }

    /**
     * Close a tab
     */
    closeTab(filePath) {
        const fileData = this.openFiles.get(filePath);
        if (!fileData) return;

        // Check for unsaved changes
        if (fileData.dirty) {
            if (!confirm(`Do you want to save changes to ${this.getFileName(filePath)}?`)) {
                // Don't save, just close
            } else {
                this.saveFile();
            }
        }

        // Dispose the model
        fileData.model.dispose();
        this.openFiles.delete(filePath);

        // Remove tab from UI
        const tab = document.querySelector(`.tab[data-path="${filePath}"]`);
        if (tab) tab.remove();

        // If this was the active file, switch to another
        if (this.activeFile === filePath) {
            const remainingFiles = Array.from(this.openFiles.keys());
            if (remainingFiles.length > 0) {
                this.switchToTab(remainingFiles[0]);
            } else {
                this.activeFile = null;
                this.editor.setValue(this.getWelcomeMessage());
                document.getElementById('currentFileName').textContent = 'Untitled';
            }
        }
    }

    /**
     * Set active tab styling
     */
    setActiveTab(filePath) {
        // Remove active class from all tabs
        document.querySelectorAll('.tab').forEach(tab => {
            tab.classList.remove('active');
        });

        // Add active class to current tab
        const activeTab = document.querySelector(`.tab[data-path="${filePath}"]`);
        if (activeTab) {
            activeTab.classList.add('active');
        }
    }

    /**
     * Update tab dirty state
     */
    updateTabDirtyState(filePath, isDirty) {
        const tab = document.querySelector(`.tab[data-path="${filePath}"]`);
        if (tab) {
            tab.classList.toggle('dirty', isDirty);
        }
    }

    /**
     * Update status bar with file info
     */
    updateStatusBar(filePath) {
        const language = detectLanguage(filePath);
        document.getElementById('statusLanguage').textContent =
            language.charAt(0).toUpperCase() + language.slice(1);
    }

    /**
     * Get filename from path
     */
    getFileName(filePath) {
        return filePath.split(/[\\/]/).pop();
    }

    /**
     * Setup keyboard and other event listeners
     */
    setupEventListeners() {
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Ctrl+S - Save
            if (e.ctrlKey && e.key === 's') {
                e.preventDefault();
                document.getElementById('saveBtn').click();
            }
            // Ctrl+R - Run
            if (e.ctrlKey && e.key === 'r') {
                e.preventDefault();
                document.getElementById('runBtn').click();
            }
            // Ctrl+W - Close tab
            if (e.ctrlKey && e.key === 'w') {
                e.preventDefault();
                if (this.activeFile) {
                    this.closeTab(this.activeFile);
                }
            }
        });

        // Handle window resize
        window.addEventListener('resize', () => {
            if (this.editor) {
                this.editor.layout();
            }
        });
    }

    /**
     * Re-layout editor (call after panel resizes)
     */
    layout() {
        if (this.editor) {
            this.editor.layout();
        }
    }

    /**
     * Set editor theme
     */
    setTheme(theme) {
        if (this.editor) {
            monaco.editor.setTheme(theme);
        }
    }

    /**
     * Get active file path
     */
    getActiveFilePath() {
        return this.activeFile;
    }

    /**
     * Check if file has unsaved changes
     */
    isDirty(filePath) {
        const fileData = this.openFiles.get(filePath || this.activeFile);
        return fileData ? fileData.dirty : false;
    }
}

// Create global instance
window.editorManager = new EditorManager();
