/**
 * AI Code Editor - File Tree Module
 * Handles file browser functionality
 */

class FileTreeManager {
    constructor() {
        this.rootPath = null;
        this.fileTree = [];
        this.selectedItem = null;
        this.expandedFolders = new Set();
        this.pollingInterval = null;  // For real-time updates
        this.lastTreeHash = null;     // To detect changes
        this.isPollingActive = false;
    }

    /**
     * Initialize file tree
     */
    init() {
        this.setupEventListeners();
        this.showPlaceholder();
    }

    /**
     * Load file tree from API
     */
    async loadFileTree() {
        try {
            const response = await fetch(`${CONFIG.API_BASE_URL}/files/tree`);

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to load files');
            }

            const data = await response.json();
            this.rootPath = data.workspace;
            this.fileTree = data.tree;
            this.lastTreeHash = this.getTreeHash(data.tree);  // Initialize hash
            this.render();

            // Start polling for real-time updates
            this.startPolling();

        } catch (error) {
            console.error('Failed to load file tree:', error);
            this.showError(error.message || 'Failed to load files. Is the backend running?');
        }
    }

    /**
     * Open folder dialog - prompts user for folder path
     */
    async openFolderDialog() {
        const folderPath = prompt(
            'Enter the full path to your project folder:\n\nExample: C:\\Users\\YourName\\projects\\my-app'
        );

        if (!folderPath) return;

        try {
            const response = await fetch(`${CONFIG.API_BASE_URL}/files/open`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: folderPath })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to open folder');
            }

            const data = await response.json();
            this.rootPath = data.workspace;
            this.fileTree = data.tree;
            this.lastTreeHash = this.getTreeHash(data.tree);  // Initialize hash
            this.render();

            console.log('✅ Opened folder:', this.rootPath);

            // Start polling for real-time updates
            this.startPolling();

            // Reconnect terminal to use the new workspace path
            if (window.terminalManager) {
                window.terminalManager.connectWebSocket();
            }

        } catch (error) {
            console.error('Failed to open folder:', error);
            alert('Error: ' + error.message);
        }
    }

    /**
     * Get demo file tree for testing
     */
    getDemoFileTree() {
        return [
            {
                name: 'src',
                type: 'folder',
                path: '/workspace/src',
                children: [
                    { name: 'main.py', type: 'file', path: '/workspace/src/main.py' },
                    { name: 'utils.py', type: 'file', path: '/workspace/src/utils.py' },
                    {
                        name: 'components',
                        type: 'folder',
                        path: '/workspace/src/components',
                        children: [
                            { name: 'App.js', type: 'file', path: '/workspace/src/components/App.js' },
                            { name: 'Header.js', type: 'file', path: '/workspace/src/components/Header.js' }
                        ]
                    }
                ]
            },
            {
                name: 'tests',
                type: 'folder',
                path: '/workspace/tests',
                children: [
                    { name: 'test_main.py', type: 'file', path: '/workspace/tests/test_main.py' }
                ]
            },
            { name: 'README.md', type: 'file', path: '/workspace/README.md' },
            { name: 'requirements.txt', type: 'file', path: '/workspace/requirements.txt' },
            { name: 'package.json', type: 'file', path: '/workspace/package.json' },
            { name: '.gitignore', type: 'file', path: '/workspace/.gitignore' }
        ];
    }

    /**
     * Render the file tree
     */
    render() {
        const container = document.getElementById('fileTree');
        container.innerHTML = '';

        if (this.fileTree.length === 0) {
            this.showPlaceholder();
            return;
        }

        // Get workspace folder name
        const workspaceName = this.rootPath ? this.rootPath.split(/[\\/]/).pop() : 'Workspace';

        // Build HTML with workspace root header
        let html = `
            <div class="tree-root" data-path="" data-type="folder">
                <i data-lucide="folder-open"></i>
                <span class="tree-root-name">${workspaceName}</span>
            </div>
        `;

        html += this.renderItems(this.fileTree, 0);
        container.innerHTML = html;

        // Initialize icons
        if (window.lucide) {
            lucide.createIcons();
        }

        // Add click handlers
        this.attachClickHandlers(container);

        // Add right-click handler to root folder
        const rootEl = container.querySelector('.tree-root');
        if (rootEl) {
            rootEl.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                this.showContextMenu(e.clientX, e.clientY, '', 'folder');
            });
        }
    }

    /**
     * Render tree items recursively
     */
    renderItems(items, level) {
        let html = '';

        // Sort: folders first, then files, alphabetically
        const sorted = [...items].sort((a, b) => {
            if (a.type === 'folder' && b.type !== 'folder') return -1;
            if (a.type !== 'folder' && b.type === 'folder') return 1;
            return a.name.localeCompare(b.name);
        });

        for (const item of sorted) {
            const isFolder = item.type === 'folder';
            const isExpanded = this.expandedFolders.has(item.path);
            const icon = this.getItemIcon(item);
            const languageClass = this.getLanguageClass(item.name);

            html += `
                <div class="tree-item ${isFolder ? 'folder' : 'file'} ${languageClass}" 
                     data-path="${item.path}"
                     data-type="${item.type}"
                     style="--indent-level: ${level}">
                    ${isFolder ? `<i data-lucide="${isExpanded ? 'chevron-down' : 'chevron-right'}" class="tree-chevron"></i>` : '<span style="width: 16px; display: inline-block;"></span>'}
                    <i data-lucide="${icon}"></i>
                    <span class="tree-item-name">${item.name}</span>
                </div>
            `;

            // Render children if folder is expanded
            if (isFolder && isExpanded && item.children) {
                html += `<div class="tree-children">${this.renderItems(item.children, level + 1)}</div>`;
            }
        }

        return html;
    }

    /**
     * Get icon for item
     */
    getItemIcon(item) {
        if (item.type === 'folder') {
            return this.expandedFolders.has(item.path) ? 'folder-open' : 'folder';
        }
        return getFileIcon(item.name);
    }

    /**
     * Get language class for syntax coloring
     */
    getLanguageClass(filename) {
        const ext = filename.split('.').pop().toLowerCase();
        const classMap = {
            'py': 'python',
            'js': 'javascript',
            'ts': 'typescript',
            'html': 'html',
            'css': 'css',
            'json': 'json',
            'md': 'markdown'
        };
        return classMap[ext] || '';
    }

    /**
     * Attach click handlers to tree items
     */
    attachClickHandlers(container) {
        container.querySelectorAll('.tree-item').forEach(item => {
            item.addEventListener('click', (e) => this.handleItemClick(e, item));
            item.addEventListener('contextmenu', (e) => this.handleContextMenu(e, item));
        });
    }

    /**
     * Handle item click
     */
    handleItemClick(e, element) {
        const path = element.dataset.path;
        const type = element.dataset.type;

        // Remove selection from all items
        document.querySelectorAll('.tree-item').forEach(item => {
            item.classList.remove('active');
        });
        element.classList.add('active');
        this.selectedItem = path;

        if (type === 'folder') {
            this.toggleFolder(path);
        } else {
            this.openFile(path);
        }
    }

    /**
     * Toggle folder expansion
     */
    toggleFolder(path) {
        if (this.expandedFolders.has(path)) {
            this.expandedFolders.delete(path);
        } else {
            this.expandedFolders.add(path);
        }
        this.render();
    }

    /**
     * Open a file
     */
    async openFile(path) {
        try {
            // Fetch file content from backend API
            const response = await fetch(`${CONFIG.API_BASE_URL}/files/read?path=${encodeURIComponent(path)}`);

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to read file');
            }

            const data = await response.json();
            await window.editorManager?.openFile(path, data.content);

        } catch (error) {
            console.error('Failed to open file:', error);
            alert('Error opening file: ' + error.message);
        }
    }

    /**
     * Get demo file content for testing
     */
    getDemoFileContent(path) {
        const filename = path.split('/').pop();

        const demoContent = {
            'main.py': `#!/usr/bin/env python3
"""
Main application entry point.
"""

def main():
    """Main function."""
    print("Hello, World!")
    
    # Example loop
    for i in range(5):
        print(f"Count: {i}")

if __name__ == "__main__":
    main()
`,
            'utils.py': `"""
Utility functions for the application.
"""

def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b

def greet(name: str) -> str:
    """Return a greeting message."""
    return f"Hello, {name}!"
`,
            'App.js': `import React from 'react';

function App() {
  const [count, setCount] = React.useState(0);

  return (
    <div className="app">
      <h1>Welcome to AI Code Editor</h1>
      <p>Count: {count}</p>
      <button onClick={() => setCount(c => c + 1)}>
        Increment
      </button>
    </div>
  );
}

export default App;
`,
            'Header.js': `import React from 'react';

function Header({ title }) {
  return (
    <header className="header">
      <h1>{title}</h1>
    </header>
  );
}

export default Header;
`,
            'test_main.py': `import pytest
from src.main import main

def test_main():
    """Test the main function."""
    assert main() is None
`,
            'README.md': `# AI Code Editor

A VS Code-like code editor with AI assistance.

## Features

- 📁 File tree navigation
- ✏️ Monaco Editor
- 🖥️ Integrated terminal
- 🤖 AI assistant

## Getting Started

1. Open a file from the sidebar
2. Edit your code
3. Run with Ctrl+R
4. Ask AI for help!
`,
            'requirements.txt': `fastapi==0.104.1
uvicorn==0.24.0
python-dotenv==1.0.0
httpx==0.25.1
`,
            'package.json': `{
  "name": "ai-code-editor",
  "version": "1.0.0",
  "description": "AI-powered code editor",
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  },
  "dependencies": {
    "react": "^18.2.0"
  }
}
`,
            '.gitignore': `# Python
__pycache__/
*.pyc
.env
venv/

# Node
node_modules/
dist/
`
        };

        return demoContent[filename] || `// File: ${filename}\n// Content not available`;
    }

    /**
     * Handle context menu (right-click)
     */
    handleContextMenu(e, element) {
        e.preventDefault();
        const path = element.dataset.path;
        const type = element.dataset.type;

        this.showContextMenu(e.clientX, e.clientY, path, type);
    }

    /**
     * Show context menu
     */
    showContextMenu(x, y, path, type) {
        // Remove existing context menu
        this.hideContextMenu();

        const menu = document.createElement('div');
        menu.className = 'context-menu';
        menu.id = 'fileTreeContextMenu';
        menu.style.left = `${x}px`;
        menu.style.top = `${y}px`;

        const isFolder = type === 'folder';

        menu.innerHTML = `
            ${isFolder ? `
                <div class="context-menu-item" data-action="new-file">
                    <i data-lucide="file-plus"></i>
                    <span>New File</span>
                </div>
                <div class="context-menu-item" data-action="new-folder">
                    <i data-lucide="folder-plus"></i>
                    <span>New Folder</span>
                </div>
                <div class="context-menu-divider"></div>
            ` : ''}
            <div class="context-menu-item" data-action="rename">
                <i data-lucide="edit-2"></i>
                <span>Rename</span>
            </div>
            <div class="context-menu-item" data-action="copy-path">
                <i data-lucide="copy"></i>
                <span>Copy Path</span>
            </div>
            <div class="context-menu-divider"></div>
            <div class="context-menu-item danger" data-action="delete">
                <i data-lucide="trash-2"></i>
                <span>Delete</span>
            </div>
        `;

        document.body.appendChild(menu);
        if (window.lucide) lucide.createIcons();

        // Handle menu item clicks
        menu.querySelectorAll('.context-menu-item').forEach(item => {
            item.addEventListener('click', () => {
                const action = item.dataset.action;
                this.handleContextAction(action, path);
                this.hideContextMenu();
            });
        });

        // Close on click outside
        setTimeout(() => {
            document.addEventListener('click', this.hideContextMenu, { once: true });
        }, 100);
    }

    /**
     * Hide context menu
     */
    hideContextMenu() {
        const menu = document.getElementById('fileTreeContextMenu');
        if (menu) menu.remove();
    }

    /**
     * Handle context menu action
     */
    handleContextAction(action, path) {
        switch (action) {
            case 'new-file':
                this.createNewFile(path);
                break;
            case 'new-folder':
                this.createNewFolder(path);
                break;
            case 'rename':
                this.renameItem(path);
                break;
            case 'copy-path':
                navigator.clipboard.writeText(path);
                break;
            case 'delete':
                this.deleteItem(path);
                break;
        }
    }

    /**
     * Create new file
     */
    async createNewFile(parentPath) {
        const name = prompt('Enter file name:');
        if (!name) return;

        // Build the full path
        const newPath = parentPath ? `${parentPath}/${name}` : name;

        try {
            const response = await fetch(`${CONFIG.API_BASE_URL}/files/create`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: newPath, is_folder: false })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to create file');
            }

            console.log('✅ File created:', newPath);

            // Refresh the file tree
            await this.loadFileTree();

            // Open the new file
            await this.openFile(newPath);

        } catch (error) {
            console.error('Failed to create file:', error);
            alert('Error: ' + error.message);
        }
    }

    /**
     * Create new folder
     */
    async createNewFolder(parentPath) {
        const name = prompt('Enter folder name:');
        if (!name) return;

        // Build the full path
        const newPath = parentPath ? `${parentPath}/${name}` : name;

        try {
            const response = await fetch(`${CONFIG.API_BASE_URL}/files/create`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: newPath, is_folder: true })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to create folder');
            }

            console.log('✅ Folder created:', newPath);

            // Refresh the file tree
            await this.loadFileTree();

            // Expand the new folder
            this.expandedFolders.add(newPath);

        } catch (error) {
            console.error('Failed to create folder:', error);
            alert('Error: ' + error.message);
        }
    }

    /**
     * Rename item
     */
    async renameItem(path) {
        const currentName = path.split('/').pop();
        const newName = prompt('Enter new name:', currentName);
        if (!newName || newName === currentName) return;

        // Build the new path
        const pathParts = path.split('/');
        pathParts.pop();
        const newPath = pathParts.length > 0 ? `${pathParts.join('/')}/${newName}` : newName;

        try {
            const response = await fetch(`${CONFIG.API_BASE_URL}/files/rename`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ old_path: path, new_path: newPath })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to rename');
            }

            console.log('✅ Renamed:', path, '→', newPath);

            // Refresh the file tree
            await this.loadFileTree();

        } catch (error) {
            console.error('Failed to rename:', error);
            alert('Error: ' + error.message);
        }
    }

    /**
     * Delete item
     */
    async deleteItem(path) {
        const name = path.split('/').pop();
        if (!confirm(`Are you sure you want to delete "${name}"?`)) return;

        try {
            const response = await fetch(`${CONFIG.API_BASE_URL}/files/delete?path=${encodeURIComponent(path)}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to delete');
            }

            console.log('✅ Deleted:', path);

            // Close the file if it's open
            if (window.editorManager?.activeFile === path) {
                window.editorManager.closeTab(path);
            }

            // Refresh the file tree
            await this.loadFileTree();

        } catch (error) {
            console.error('Failed to delete:', error);
            alert('Error: ' + error.message);
        }
    }

    /**
     * Show placeholder when no folder is open
     */
    showPlaceholder() {
        const container = document.getElementById('fileTree');
        container.innerHTML = `
            <div class="tree-placeholder">
                <i data-lucide="folder-open"></i>
                <p>No folder open</p>
                <button class="btn-secondary" id="openFolderBtn">Open Folder</button>
            </div>
        `;
        if (window.lucide) lucide.createIcons();

        document.getElementById('openFolderBtn')?.addEventListener('click', () => {
            this.openFolderDialog();
        });
    }

    /**
     * Show error message
     */
    showError(message) {
        const container = document.getElementById('fileTree');
        container.innerHTML = `
            <div class="tree-placeholder">
                <i data-lucide="alert-circle"></i>
                <p>${message}</p>
                <button class="btn-secondary" onclick="fileTreeManager.loadFileTree()">Retry</button>
            </div>
        `;
        if (window.lucide) lucide.createIcons();
    }

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // New file button
        document.getElementById('newFileBtn')?.addEventListener('click', () => {
            this.createNewFile(this.selectedItem || this.rootPath);
        });

        // New folder button
        document.getElementById('newFolderBtn')?.addEventListener('click', () => {
            this.createNewFolder(this.selectedItem || this.rootPath);
        });

        // Refresh button
        document.getElementById('refreshTreeBtn')?.addEventListener('click', () => {
            this.loadFileTree();
        });

        // Keyboard shortcut for toggle
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'b') {
                e.preventDefault();
                this.togglePanel();
            }
        });
    }

    /**
     * Start polling for file tree changes (real-time updates)
     */
    startPolling() {
        if (this.isPollingActive) return;  // Already polling

        this.isPollingActive = true;
        console.log('🔄 Started file tree polling (every 2s)');

        this.pollingInterval = setInterval(async () => {
            try {
                const response = await fetch(`${CONFIG.API_BASE_URL}/files/tree`);
                if (!response.ok) return;  // Workspace might be closed

                const data = await response.json();
                const newHash = this.getTreeHash(data.tree);

                // Only update if tree changed
                if (this.lastTreeHash && newHash !== this.lastTreeHash) {
                    console.log('📁 File tree changed, updating...');
                    this.fileTree = data.tree;
                    this.render();
                }

                this.lastTreeHash = newHash;
            } catch (error) {
                // Silently handle errors (workspace might be closed)
            }
        }, 2000);  // Poll every 2 seconds
    }

    /**
     * Stop polling for file tree changes
     */
    stopPolling() {
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
            this.isPollingActive = false;
            this.lastTreeHash = null;
            console.log('⏸️  Stopped file tree polling');
        }
    }

    /**
     * Generate a hash of the file tree for change detection
     */
    getTreeHash(tree) {
        return JSON.stringify(tree);  // Simple hash using JSON string
    }

    /**
     * Toggle file tree panel visibility
     */
    togglePanel() {
        const panel = document.getElementById('fileTreePanel');
        const resizer = document.getElementById('resizerLeft');
        panel.classList.toggle('hidden');
        resizer.classList.toggle('hidden');
        window.editorManager?.layout();
    }
}

// Create global instance
window.fileTreeManager = new FileTreeManager();
