/**
 * AI Code Editor - Monaco Editor Module
 * Handles all Monaco Editor functionality
 */

class EditorManager {
    constructor() {
        this.mainEditor = null;
        this.secondaryEditor = null;
        this.openFiles = new Map(); // path -> { content, model, viewState, dirty }

        this.activeFileLeft = null;
        this.activeFileRight = null;
        this.focusedPane = 'left'; // 'left' or 'right'

        this.isSplit = false;
        this.monacoLoaded = false;
        this.fontSize = 14;
        this.isWordWrap = false;
    }

    /**
     * Get the currently focused editor instance
     */
    get editor() {
        return this.focusedPane === 'left' ? this.mainEditor : (this.secondaryEditor || this.mainEditor);
    }

    /**
     * Get the currently active file path
     */
    get activeFile() {
        return this.focusedPane === 'left' ? this.activeFileLeft : this.activeFileRight;
    }

    set activeFile(val) {
        if (this.focusedPane === 'left') {
            this.activeFileLeft = val;
        } else {
            this.activeFileRight = val;
        }
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
                this.mainEditor = this.createEditorInstance('editorContainer');
                this.setupEventListeners();
                this.setupPaneListeners();
                this.setFocusedPane('left');
                resolve();
            });
        });
    }

    /**
     * Create a Monaco Editor instance
     */
    createEditorInstance(containerId) {
        const container = document.getElementById(containerId);
        const settings = window.settingsManager?.settings || {};
        const editor = monaco.editor.create(container, {
            value: containerId === 'editorContainer' ? this.getWelcomeMessage() : '',
            language: 'markdown',
            ...CONFIG.EDITOR,
            fontSize: settings.fontSize || 14,
            wordWrap: settings.wordWrap ? 'on' : 'off',
            minimap: { enabled: !!settings.minimap },
            lineNumbers: settings.lineNumbers ? 'on' : 'off'
        });

        // Update cursor position in status bar
        editor.onDidChangeCursorPosition((e) => {
            if (this.isFocused(editor)) {
                const position = e.position;
                document.getElementById('statusPosition').textContent =
                    `Ln ${position.lineNumber}, Col ${position.column}`;
            }
        });

        // Track content changes for dirty state
        editor.onDidChangeModelContent(() => {
            const model = editor.getModel();
            const filePath = this.getFilePathFromModel(model);
            if (filePath) {
                const fileData = this.openFiles.get(filePath);
                if (fileData) {
                    fileData.dirty = true;
                    this.updateTabDirtyState(filePath, true);
                    // Update file tree badge
                    window.fileTreeManager?.updateFileBadge(filePath);
                }
            }
        });

        // Focus events
        editor.onDidFocusEditorWidget(() => {
            const pane = containerId === 'editorContainer' ? 'left' : 'right';
            this.setFocusedPane(pane);
        });

        return editor;
    }

    /**
 * Set focused pane
 */
    setFocusedPane(pane) {
        this.focusedPane = pane;

        // Update UI
        document.getElementById('paneLeft')?.classList.toggle('active', pane === 'left');
        document.getElementById('paneRight')?.classList.toggle('active', pane === 'right');

        // Update status bar
        const activeFile = pane === 'left' ? this.activeFileLeft : this.activeFileRight;
        if (activeFile) {
            this.updateStatusBar(activeFile);
            this.setActiveTab(activeFile);
            this.updateBreadcrumb(activeFile);
            document.getElementById('currentFileName').textContent = this.getFileName(activeFile);
        } else {
            document.getElementById('currentFileName').textContent = 'Untitled';
            const breadcrumb = document.getElementById('breadcrumb');
            if (breadcrumb) breadcrumb.innerHTML = '';
        }
    }

    /**
     * Check if an editor is the currently focused one
     */
    isFocused(editor) {
        return (this.focusedPane === 'left' && editor === this.mainEditor) ||
            (this.focusedPane === 'right' && editor === this.secondaryEditor);
    }

    /**
     * Get file path assigned to a model
     */
    getFilePathFromModel(model) {
        for (const [path, data] of this.openFiles.entries()) {
            if (data.model === model) return path;
        }
        return null;
    }

    /**
     * Toggle split screen
     */
    toggleSplit() {
        const paneRight = document.getElementById('paneRight');
        const splitResizer = document.getElementById('splitResizer');
        const splitBtn = document.getElementById('splitBtn');

        if (this.isSplit) {
            // Close split
            this.isSplit = false;
            paneRight.style.display = 'none';
            splitResizer.style.display = 'none';
            if (splitBtn) {
                splitBtn.innerHTML = '<i data-lucide="columns"></i><span>Split</span>';
                lucide.createIcons();
            }
            this.setFocusedPane('left');
        } else {
            // Open split
            this.isSplit = true;
            paneRight.style.display = 'flex';
            splitResizer.style.display = 'block';

            if (!this.secondaryEditor) {
                this.secondaryEditor = this.createEditorInstance('secondaryEditorContainer');
            }

            if (splitBtn) {
                splitBtn.innerHTML = '<i data-lucide="layout"></i><span>Unsplit</span>';
                lucide.createIcons();
            }

            // If a file is open on left, clone it to right for start
            if (this.activeFileLeft) {
                this.openFileInPane(this.activeFileLeft, 'right');
            }

            this.setFocusedPane('right');
        }

        this.layout();
        window.toast?.info(this.isSplit ? 'Editor split' : 'Split closed');
    }

    /**
     * Open a file in the active editor pane
     */
    async openFile(filePath, content) {
        return this.openFileInPane(filePath, this.focusedPane, content);
    }

    /**
     * Open a file in a specific pane
     */
    async openFileInPane(filePath, pane, content = null) {
        const editor = pane === 'left' ? this.mainEditor : (this.secondaryEditor || this.mainEditor);

        // Save current file's view state for this editor
        const currentFile = pane === 'left' ? this.activeFileLeft : this.activeFileRight;
        if (currentFile) {
            const currentFileData = this.openFiles.get(currentFile);
            if (currentFileData) {
                // We should store view state per editor instance? 
                // For simplicity, let's just store it in the fileData
                currentFileData.viewState = editor.saveViewState();
            }
        }

        // Check if file is already open somewhere
        let fileData = this.openFiles.get(filePath);

        if (!fileData) {
            // Create new model if not open
            if (content === null) {
                // Fetch if content not provided
                try {
                    const response = await fetch(`${CONFIG.API_BASE_URL}/files/read?path=${encodeURIComponent(filePath)}`);
                    if (!response.ok) throw new Error('Failed to read file');
                    const data = await response.json();
                    content = data.content;
                } catch (err) {
                    console.error('Error opening file:', err);
                    window.toast?.error(`Failed to open file: ${filePath}`);
                    return;
                }
            }

            const language = detectLanguage(filePath);
            const model = monaco.editor.createModel(content, language);

            fileData = {
                content: content,
                model: model,
                viewState: null,
                dirty: false
            };
            this.openFiles.set(filePath, fileData);
            this.createTab(filePath);
        }

        // Apply model to editor
        editor.setModel(fileData.model);
        if (fileData.viewState) {
            editor.restoreViewState(fileData.viewState);
        }

        // Update pane state
        if (pane === 'left') {
            this.activeFileLeft = filePath;
        } else {
            this.activeFileRight = filePath;
        }

        // If this is the focused pane, update global UI
        if (this.focusedPane === pane) {
            this.setActiveTab(filePath);
            this.updateStatusBar(filePath);
            this.updateBreadcrumb(filePath);
            document.getElementById('currentFileName').textContent = this.getFileName(filePath);
            // Highlight file in tree
            window.fileTreeManager?.highlightFile(filePath);
        }
    }

    /**
     * Switch to a specific tab
     */
    async switchToTab(filePath) {
        // Always switches in the focused pane
        this.openFileInPane(filePath, this.focusedPane);
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
                this.saveFile(); // Saves currently active file
            }
        }

        // If this file is open in LEFT or RIGHT, clear those panes
        if (this.activeFileLeft === filePath) {
            this.activeFileLeft = null;
            if (this.mainEditor) this.mainEditor.setModel(monaco.editor.createModel(this.getWelcomeMessage(), 'markdown'));
        }
        if (this.activeFileRight === filePath) {
            this.activeFileRight = null;
            if (this.secondaryEditor) this.secondaryEditor.setModel(monaco.editor.createModel('', 'markdown'));
        }

        // Dispose the model
        fileData.model.dispose();
        this.openFiles.delete(filePath);

        // Remove tab from UI - use CSS.escape for proper path escaping
        const escapedPath = CSS.escape(filePath);
        const tab = document.querySelector(`.tab[data-path="${escapedPath}"]`);
        if (tab) {
            tab.remove();
        } else {
            // Fallback: try to find by iterating
            document.querySelectorAll('.tab').forEach(t => {
                if (t.dataset.path === filePath) {
                    t.remove();
                }
            });
        }

        // UI Updates if needed
        if (!this.activeFileLeft && !this.activeFileRight) {
            document.getElementById('currentFileName').textContent = 'Untitled';
        }
    }

    /**
     * Save current focused editor's file
     */
    async saveFile() {
        const activeFile = this.activeFile;
        if (!activeFile) return null;

        const fileData = this.openFiles.get(activeFile);
        if (!fileData) return null;

        const editor = this.editor;
        const content = editor.getValue();

        try {
            const response = await fetch(`${CONFIG.API_BASE_URL}/files/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    path: activeFile,
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
            this.updateTabDirtyState(activeFile, false);

            console.log('✅ File saved:', activeFile);
            window.toast?.success(`Saved: ${this.getFileName(activeFile)}`);

            return { path: activeFile, content: content };

        } catch (error) {
            console.error('Failed to save file:', error);
            window.toast?.error(`Error saving file: ${error.message}`);
            return null;
        }
    }

    /**
     * Get welcome message
     */
    getWelcomeMessage() {
        return `# Welcome to QUASAR 🚀\n\nOpen a file to start coding or use **Split** to edit side-by-side.`;
    }

    /**
     * Setup split resizer and other pane-specific listeners
     */
    setupPaneListeners() {
        const resizer = document.getElementById('splitResizer');
        const paneLeft = document.getElementById('paneLeft');
        const container = document.getElementById('editorSplitView');

        if (!resizer) return;

        let isResizing = false;

        resizer.addEventListener('mousedown', (e) => {
            isResizing = true;
            document.body.style.cursor = 'col-resize';
            e.preventDefault();
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;

            const containerRect = container.getBoundingClientRect();
            const relativeX = e.clientX - containerRect.left;
            const percentage = (relativeX / containerRect.width) * 100;

            if (percentage > 10 && percentage < 90) {
                paneLeft.style.flex = `0 0 ${percentage}%`;
                this.layout();
            }
        });

        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                document.body.style.cursor = '';
                this.layout();
            }
        });

        // Click on pane wrapper to focus
        paneLeft.addEventListener('click', () => this.setFocusedPane('left'));
        document.getElementById('paneRight')?.addEventListener('click', () => this.setFocusedPane('right'));
    }

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // toolbar button listeners
        document.getElementById('formatCodeBtn')?.addEventListener('click', () => {
            this.editor?.getAction('editor.action.formatDocument')?.run();
        });

        document.getElementById('toggleWordWrapBtn')?.addEventListener('click', () => {
            this.isWordWrap = !this.isWordWrap;
            const option = this.isWordWrap ? 'on' : 'off';
            this.mainEditor?.updateOptions({ wordWrap: option });
            this.secondaryEditor?.updateOptions({ wordWrap: option });
            window.toast?.info(`Word wrap: ${option}`);
        });

        document.getElementById('fontMoreBtn')?.addEventListener('click', () => {
            this.updateFontSize(this.fontSize + 1);
        });

        document.getElementById('fontLessBtn')?.addEventListener('click', () => {
            this.updateFontSize(this.fontSize - 1);
        });

        // Split button
        document.getElementById('splitBtn')?.addEventListener('click', () => {
            this.toggleSplit();
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Ctrl+\ - Split
            if (e.ctrlKey && e.key === '\\') {
                e.preventDefault();
                this.toggleSplit();
            }
            // Ctrl+S - Save
            if (e.ctrlKey && e.key === 's') {
                e.preventDefault();
                this.saveFile();
            }
            // Ctrl+W - Close
            if (e.ctrlKey && e.key === 'w') {
                e.preventDefault();
                if (this.activeFile) this.closeTab(this.activeFile);
            }
        });

        // Handle window resize
        window.addEventListener('resize', () => this.layout());
    }

    /**
     * Update editor font size
     */
    updateFontSize(newSize) {
        if (newSize < 8 || newSize > 32) return;
        this.fontSize = newSize;
        this.mainEditor?.updateOptions({ fontSize: newSize });
        this.secondaryEditor?.updateOptions({ fontSize: newSize });

        const label = document.getElementById('fontSizeLabel');
        if (label) label.textContent = `${newSize}px`;
    }

    /**
     * Update breadcrumb based on file path
     */
    updateBreadcrumb(filePath) {
        const container = document.getElementById('breadcrumb');
        if (!container) return;

        const parts = filePath.split(/[\\/]/).filter(p => p);
        container.innerHTML = '';

        parts.forEach((part, index) => {
            const item = document.createElement('span');
            item.className = 'breadcrumb-item';
            item.textContent = part;

            // In a real app, clicking this would open the folder in Explorer
            item.addEventListener('click', () => {
                const folderPath = '/' + parts.slice(0, index + 1).join('/');
                console.log('Navigating to:', folderPath);
            });

            container.appendChild(item);

            if (index < parts.length - 1) {
                const sep = document.createElement('span');
                sep.className = 'breadcrumb-separator';
                sep.textContent = '›';
                container.appendChild(sep);
            }
        });
    }

    /**
     * Various UI utility methods (keeping existing logic but adapted)
     */
    createTab(filePath) {
        const tabsContainer = document.getElementById('tabs');
        if (!tabsContainer) return;

        const fileName = this.getFileName(filePath);
        const icon = getFileIcon(fileName);

        const tab = document.createElement('div');
        tab.className = 'tab';
        tab.dataset.path = filePath;
        tab.innerHTML = `
            <i data-lucide="${icon}"></i>
            <span class="tab-title">${fileName}</span>
            <span class="tab-close"><i data-lucide="x"></i></span>
        `;

        tab.addEventListener('click', (e) => {
            if (!e.target.closest('.tab-close')) this.switchToTab(filePath);
        });

        // Tab close handler
        tab.querySelector('.tab-close').addEventListener('click', (e) => {
            e.stopPropagation();
            this.closeTab(filePath);
        });

        // Context menu handler
        tab.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.showTabContextMenu(e, filePath);
        });

        tabsContainer.appendChild(tab);
        if (window.lucide) lucide.createIcons();
    }

    /**
     * Show context menu for a tab
     */
    showTabContextMenu(e, filePath) {
        const items = [
            {
                label: 'Close',
                icon: 'x',
                action: () => this.closeTab(filePath)
            },
            {
                label: 'Close Others',
                action: () => this.closeOthers(filePath)
            },
            {
                label: 'Close All',
                action: () => this.closeAll()
            },
            { separator: true },
            {
                label: this.isSplit ? 'Move to Other Pane' : 'Split Right',
                icon: 'columns',
                action: () => {
                    if (!this.isSplit) this.toggleSplit();
                    this.openFileInPane(filePath, this.focusedPane === 'left' ? 'right' : 'left');
                }
            },
            { separator: true },
            {
                label: 'Copy Path',
                icon: 'copy',
                action: () => {
                    navigator.clipboard.writeText(filePath);
                    window.toast?.success('Path copied to clipboard');
                }
            },
            {
                label: 'Copy Relative Path',
                action: () => {
                    const relPath = window.fileTreeManager?.rootPath ?
                        filePath.replace(window.fileTreeManager.rootPath, '').replace(/^[\\/]/, '') :
                        filePath;
                    navigator.clipboard.writeText(relPath);
                    window.toast?.success('Relative path copied');
                }
            }
        ];

        window.contextMenu?.show(e.clientX, e.clientY, items);
    }

    /**
     * Close all tabs except one
     */
    closeOthers(exceptPath) {
        const paths = Array.from(this.openFiles.keys());
        paths.forEach(p => {
            if (p !== exceptPath) this.closeTab(p);
        });
    }

    /**
     * Close all tabs
     */
    closeAll() {
        const paths = Array.from(this.openFiles.keys());
        paths.forEach(p => this.closeTab(p));
    }

    setActiveTab(filePath) {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        const tab = document.querySelector(`.tab[data-path="${filePath}"]`);
        if (tab) tab.classList.add('active');
    }

    updateTabDirtyState(filePath, isDirty) {
        const tab = document.querySelector(`.tab[data-path="${filePath}"]`);
        if (tab) tab.classList.toggle('dirty', isDirty);
    }

    updateStatusBar(filePath) {
        const language = detectLanguage(filePath);
        const el = document.getElementById('statusLanguage');
        if (el) el.textContent = language.charAt(0).toUpperCase() + language.slice(1);
    }

    getFileName(filePath) {
        return filePath.split(/[\\/]/).pop();
    }

    layout() {
        if (this.mainEditor) this.mainEditor.layout();
        if (this.secondaryEditor) this.secondaryEditor.layout();
    }

    setTheme(theme) {
        monaco.editor.setTheme(theme);
    }

    getActiveFilePath() {
        return this.activeFile;
    }

    isDirty(filePath) {
        const f = this.openFiles.get(filePath || this.activeFile);
        return f ? f.dirty : false;
    }

    getContent() { return this.editor ? this.editor.getValue() : ''; }
    getSelection() {
        if (!this.editor) return '';
        const model = this.editor.getModel();
        if (!model) return '';
        return model.getValueInRange(this.editor.getSelection());
    }
    insertAtCursor(text) {
        if (!this.editor) return;
        this.editor.executeEdits('ai-insert', [{
            range: this.editor.getSelection(),
            text: text,
            forceMoveMarkers: true
        }]);
    }
    replaceSelection(text) {
        if (!this.editor) return;
        this.editor.executeEdits('ai-replace', [{
            range: this.editor.getSelection(),
            text: text,
            forceMoveMarkers: true
        }]);
    }

    async reloadFile(filePath) {
        const fileName = this.getFileName(filePath);
        let matchedPath = null;
        for (const p of this.openFiles.keys()) {
            if (p === filePath || this.getFileName(p) === fileName) {
                matchedPath = p; break;
            }
        }

        if (!matchedPath) {
            if (window.fileTreeManager) window.fileTreeManager.openFile(filePath);
            return;
        }

        try {
            const resp = await fetch(`${CONFIG.API_BASE_URL}/files/read?path=${encodeURIComponent(filePath)}`);
            if (!resp.ok) return;
            const data = await resp.json();
            const fileData = this.openFiles.get(matchedPath);
            if (fileData && fileData.model && fileData.model.getValue() !== data.content) {
                fileData.model.setValue(data.content);
                fileData.content = data.content;
                fileData.dirty = false;
                this.updateTabDirtyState(matchedPath, false);
            }
        } catch (e) { console.error(e); }
    }
}

window.editorManager = new EditorManager();
