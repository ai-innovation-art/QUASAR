/**
 * AI Code Editor - Resizer Module
 * Handles panel resizing functionality
 */

class ResizerManager {
    constructor() {
        this.isResizing = false;
        this.currentResizer = null;
        this.startX = 0;
        this.startY = 0;
        this.startWidth = 0;
        this.startHeight = 0;
    }

    /**
     * Initialize resizers
     */
    init() {
        this.setupLeftResizer();
        this.setupRightResizer();
        this.setupBottomResizer();

        // Global mouse event handlers
        document.addEventListener('mousemove', (e) => this.handleMouseMove(e));
        document.addEventListener('mouseup', () => this.handleMouseUp());

        // Load saved sizes from localStorage
        this.loadSavedSizes();
    }

    /**
     * Setup left resizer (file tree <-> editor)
     */
    setupLeftResizer() {
        const resizer = document.getElementById('resizerLeft');
        const panel = document.getElementById('fileTreePanel');

        if (!resizer || !panel) return;

        resizer.addEventListener('mousedown', (e) => {
            this.isResizing = true;
            this.currentResizer = 'left';
            this.startX = e.clientX;
            this.startWidth = panel.offsetWidth;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
        });
    }

    /**
     * Setup right resizer (editor <-> agent)
     */
    setupRightResizer() {
        const resizer = document.getElementById('resizerRight');
        const panel = document.getElementById('agentPanel');

        if (!resizer || !panel) return;

        resizer.addEventListener('mousedown', (e) => {
            this.isResizing = true;
            this.currentResizer = 'right';
            this.startX = e.clientX;
            this.startWidth = panel.offsetWidth;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
        });
    }

    /**
     * Setup bottom resizer (editor <-> terminal)
     */
    setupBottomResizer() {
        const resizer = document.getElementById('resizerBottom');
        const panel = document.getElementById('terminalWrapper');

        if (!resizer || !panel) return;

        resizer.addEventListener('mousedown', (e) => {
            this.isResizing = true;
            this.currentResizer = 'bottom';
            this.startY = e.clientY;
            this.startHeight = panel.offsetHeight;
            document.body.style.cursor = 'row-resize';
            document.body.style.userSelect = 'none';
        });
    }

    /**
     * Handle mouse move during resize
     */
    handleMouseMove(e) {
        if (!this.isResizing) return;

        switch (this.currentResizer) {
            case 'left':
                this.resizeLeft(e);
                break;
            case 'right':
                this.resizeRight(e);
                break;
            case 'bottom':
                this.resizeBottom(e);
                break;
        }
    }

    /**
     * Resize left panel (file tree)
     */
    resizeLeft(e) {
        const panel = document.getElementById('fileTreePanel');
        if (!panel) return;

        const diff = e.clientX - this.startX;
        const newWidth = Math.max(150, Math.min(500, this.startWidth + diff));
        panel.style.width = `${newWidth}px`;

        // Re-layout editor
        window.editorManager?.layout();
    }

    /**
     * Resize right panel (agent)
     */
    resizeRight(e) {
        const panel = document.getElementById('agentPanel');
        if (!panel) return;

        const diff = this.startX - e.clientX;
        const newWidth = Math.max(250, Math.min(600, this.startWidth + diff));
        panel.style.width = `${newWidth}px`;

        // Re-layout editor
        window.editorManager?.layout();
    }

    /**
     * Resize bottom panel (terminal)
     */
    resizeBottom(e) {
        const panel = document.getElementById('terminalWrapper');
        if (!panel) return;

        const diff = this.startY - e.clientY;
        const newHeight = Math.max(100, Math.min(500, this.startHeight + diff));
        panel.style.height = `${newHeight}px`;

        // Re-layout editor and terminal
        window.editorManager?.layout();
        window.terminalManager?.fit();
    }

    /**
     * Handle mouse up (end resize)
     */
    handleMouseUp() {
        if (this.isResizing) {
            this.isResizing = false;
            this.currentResizer = null;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';

            // Save sizes
            this.saveSizes();
        }
    }

    /**
     * Save panel sizes to localStorage
     */
    saveSizes() {
        const sizes = {
            fileTree: document.getElementById('fileTreePanel')?.offsetWidth,
            agent: document.getElementById('agentPanel')?.offsetWidth,
            terminal: document.getElementById('terminalWrapper')?.offsetHeight
        };
        localStorage.setItem('panelSizes', JSON.stringify(sizes));
    }

    /**
     * Load panel sizes from localStorage
     */
    loadSavedSizes() {
        try {
            const saved = localStorage.getItem('panelSizes');
            if (!saved) return;

            const sizes = JSON.parse(saved);

            if (sizes.fileTree) {
                document.getElementById('fileTreePanel').style.width = `${sizes.fileTree}px`;
            }
            if (sizes.agent) {
                document.getElementById('agentPanel').style.width = `${sizes.agent}px`;
            }
            if (sizes.terminal) {
                document.getElementById('terminalWrapper').style.height = `${sizes.terminal}px`;
            }
        } catch (e) {
            console.warn('Could not load saved panel sizes:', e);
        }
    }

    /**
     * Reset panel sizes to defaults
     */
    resetSizes() {
        localStorage.removeItem('panelSizes');
        document.getElementById('fileTreePanel').style.width = '';
        document.getElementById('agentPanel').style.width = '';
        document.getElementById('terminalWrapper').style.height = '';
        window.editorManager?.layout();
        window.terminalManager?.fit();
    }
}

// Create global instance
window.resizerManager = new ResizerManager();
