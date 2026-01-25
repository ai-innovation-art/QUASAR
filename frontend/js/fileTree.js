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
        this.recentFolders = JSON.parse(localStorage.getItem('quasar_recent_folders') || '[]');
        this.newFiles = new Set(); // Track newly created files for badge display
    }

    /**
     * Initialize file tree
     */
    init() {
        this.setupEventListeners();
        this.setupModalEventListeners();

        // Try to load the last opened folder
        const lastFolder = localStorage.getItem('quasar_last_folder');
        if (lastFolder) {
            console.log('📂 Attempting to auto-load last folder:', lastFolder);
            this.openFolder(lastFolder);
        } else {
            this.showPlaceholder();
        }
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
            this.render();

        } catch (error) {
            console.error('Failed to load file tree:', error);
            this.showError(error.message || 'Failed to load files. Is the backend running?');
        }
    }

    /**
     * Show the folder selection modal
     */
    showOpenFolderModal() {
        const modal = document.getElementById('folderModalOverlay');
        const input = document.getElementById('folderPathInput');
        const recentList = document.getElementById('recentFoldersList');

        if (!modal) {
            console.error('❌ Folder modal not found! Check if folderModalOverlay exists in HTML.');
            return;
        }

        // Set input value if exists
        if (input) {
            input.value = this.rootPath || '';
        }

        // Render recent folders if list exists
        if (recentList) {
            this.renderRecentFolders();
        }

        // Show modal using class like settings modal does
        modal.classList.add('active');
        if (input) input.focus();

        console.log('📂 Open folder modal shown');
    }

    /**
     * Render the list of recent folders in the modal
     */
    renderRecentFolders() {
        const recentList = document.getElementById('recentFoldersList');
        const recentSection = document.getElementById('recentFoldersSection');

        if (!recentList || !recentSection) return;

        if (this.recentFolders.length === 0) {
            recentSection.style.display = 'none';
            return;
        }

        recentSection.style.display = 'block';

        recentList.innerHTML = this.recentFolders.map(path => {
            const name = path.split(/[\\/]/).pop() || path;
            return `
                <div class="recent-folder-item" data-path="${path}">
                    <i data-lucide="folder" class="recent-folder-icon"></i>
                    <div class="recent-folder-info">
                        <span class="recent-folder-name">${name}</span>
                        <span class="recent-folder-path">${path}</span>
                    </div>
                </div>
            `;
        }).join('');

        if (window.lucide) lucide.createIcons();

        // Add click handlers to recent items
        recentList.querySelectorAll('.recent-folder-item').forEach(item => {
            item.addEventListener('click', () => {
                document.getElementById('folderPathInput').value = item.dataset.path;
                this.handleConfirmFolder();
            });
        });
    }

    /**
     * Handle folder confirmation from modal
     */
    async handleConfirmFolder() {
        const folderPath = document.getElementById('folderPathInput').value.trim();
        if (!folderPath) return;

        await this.openFolder(folderPath);
        this.closeFolderModal();
    }

    /**
     * Close the folder selection modal
     */
    closeFolderModal() {
        const modal = document.getElementById('folderModalOverlay');
        if (modal) modal.classList.remove('active');
    }

    /**
     * Open a specific folder by path
     */
    async openFolder(folderPath) {
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
            this.render();

            console.log('✅ Opened folder:', this.rootPath);
            window.toast?.success(`Opened folder: ${this.rootPath.split(/[\\/]/).pop()}`);

            // Save to persistence
            this.saveToPersistence(this.rootPath);

            // Reconnect terminal to use the new workspace path
            if (window.terminalManager) {
                // Change directory in all terminals to the new workspace
                window.terminalManager.terminals.forEach((data, id) => {
                    window.terminalManager.changeDirectory(this.rootPath, id);
                });
            }

        } catch (error) {
            console.error('Failed to open folder:', error);
            window.toast?.error(`Failed to open folder: ${error.message}`);
            // If auto-loading failed, show placeholder or error
            if (!this.rootPath) {
                this.showError('Could not open folder. ' + error.message);
            }
        }
    }

    /**
     * Save current folder to localStorage and update recent history
     */
    saveToPersistence(path) {
        // Save as last opened
        localStorage.setItem('quasar_last_folder', path);

        // Update recent folders (max 3, unique)
        let recent = this.recentFolders.filter(p => p !== path);
        recent.unshift(path);
        this.recentFolders = recent.slice(0, 3);

        localStorage.setItem('quasar_recent_folders', JSON.stringify(this.recentFolders));
    }

    /**
     * Open folder dialog - now shows our custom modal instead of prompt
     */
    async openFolderDialog() {
        this.showOpenFolderModal();
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
            const iconColorClass = this.getIconColorClass(item);
            const badge = this.getFileBadge(item.path);

            html += `
                <div class="tree-item ${isFolder ? 'folder' : 'file'} ${languageClass}" 
                     data-path="${item.path}"
                     data-type="${item.type}"
                     style="--indent-level: ${level}">
                    ${isFolder ? `<i data-lucide="${isExpanded ? 'chevron-down' : 'chevron-right'}" class="tree-chevron folder-arrow"></i>` : '<span style="width: 16px; display: inline-block;"></span>'}
                    <span class="file-icon ${iconColorClass}"><i data-lucide="${icon}"></i></span>
                    <span class="tree-item-name">${item.name}</span>
                    ${badge}
                </div>
            `;

            // Render children if folder is expanded
            if (isFolder && isExpanded && item.children) {
                html += `<div class="tree-children folder-children ${isExpanded ? 'expanded' : 'collapsed'}">${this.renderItems(item.children, level + 1)}</div>`;
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
     * Get icon color class based on file type
     */
    getIconColorClass(item) {
        if (item.type === 'folder') {
            return this.expandedFolders.has(item.path) ? 'folder-open' : 'folder';
        }

        const filename = item.name.toLowerCase();
        const ext = filename.split('.').pop();

        // Special files
        if (filename === '.gitignore' || filename === '.git') return 'git';
        if (filename === '.env' || filename.startsWith('.env')) return 'env';

        // Extension mapping
        const colorMap = {
            'py': 'python',
            'js': 'javascript',
            'jsx': 'javascript',
            'ts': 'typescript',
            'tsx': 'typescript',
            'html': 'html',
            'htm': 'html',
            'css': 'css',
            'scss': 'css',
            'json': 'json',
            'md': 'markdown',
            'yml': 'json',
            'yaml': 'json'
        };

        return colorMap[ext] || 'default';
    }

    /**
     * Get badge HTML for a file based on its state
     */
    getFileBadge(filePath) {
        // Check if file is new
        if (this.newFiles.has(filePath)) {
            return '<span class="tree-badge new" title="New">N</span>';
        }

        // Check if file is modified (has unsaved changes in editor)
        if (window.editorManager) {
            const fileData = window.editorManager.openFiles.get(filePath);
            if (fileData && fileData.dirty) {
                return '<span class="tree-badge modified" title="Modified">M</span>';
            }
        }

        return '';
    }

    /**
     * Mark a file as new (just created)
     */
    markAsNew(filePath) {
        this.newFiles.add(filePath);
        // Auto-clear after 30 seconds
        setTimeout(() => {
            this.newFiles.delete(filePath);
            this.render(); // Re-render to remove badge
        }, 30000);
    }

    /**
     * Clear new badge from a file
     */
    clearNewBadge(filePath) {
        if (this.newFiles.has(filePath)) {
            this.newFiles.delete(filePath);
            this.render();
        }
    }

    /**
     * Update badge for a specific file (called when dirty state changes)
     */
    updateFileBadge(filePath) {
        const treeItem = document.querySelector(`.tree-item[data-path="${CSS.escape(filePath)}"]`);
        if (!treeItem) return;

        // Remove existing badge
        const existingBadge = treeItem.querySelector('.tree-badge');
        if (existingBadge) existingBadge.remove();

        // Add new badge if needed
        const badge = this.getFileBadge(filePath);
        if (badge) {
            const nameSpan = treeItem.querySelector('.tree-item-name');
            if (nameSpan) {
                nameSpan.insertAdjacentHTML('afterend', badge);
            }
        }
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
     * Highlight a file in the tree (called when file is opened programmatically)
     */
    highlightFile(filePath) {
        if (!filePath) return;

        // Remove selection from all items
        document.querySelectorAll('.tree-item').forEach(item => {
            item.classList.remove('active');
        });

        // Try to find matching tree item - handle both exact match and partial match
        let treeItem = document.querySelector(`.tree-item[data-path="${filePath}"]`);

        // If not found, try with normalized path (replace backslashes)
        if (!treeItem) {
            const normalizedPath = filePath.replace(/\\\\/g, '/');
            treeItem = document.querySelector(`.tree-item[data-path="${normalizedPath}"]`);
        }

        // Try matching by filename if full path doesn't work
        if (!treeItem) {
            const fileName = filePath.split(/[\\\\/]/).pop();
            document.querySelectorAll('.tree-item').forEach(item => {
                const itemPath = item.dataset.path || '';
                if (itemPath.endsWith(fileName) || itemPath.split(/[\\\\/]/).pop() === fileName) {
                    treeItem = item;
                }
            });
        }

        if (treeItem) {
            treeItem.classList.add('active');
            this.selectedItem = treeItem.dataset.path;
            // Scroll into view if needed
            treeItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
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
        // Guard: Ensure workspace is set
        if (!this.rootPath) {
            console.warn('⚠️ Cannot open file: No workspace folder is open.');
            return;
        }

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
     * Setup modal specific event listeners
     */
    setupModalEventListeners() {
        const modal = document.getElementById('folderModalOverlay');
        const closeBtn = document.getElementById('closeFolderModalBtn');
        const cancelBtn = document.getElementById('cancelFolderBtn');
        const confirmBtn = document.getElementById('confirmFolderBtn');
        const input = document.getElementById('folderPathInput');

        closeBtn?.addEventListener('click', () => this.closeFolderModal());
        cancelBtn?.addEventListener('click', () => this.closeFolderModal());
        confirmBtn?.addEventListener('click', () => this.handleConfirmFolder());

        // Close on overlay click
        modal?.addEventListener('click', (e) => {
            if (e.target === modal) this.closeFolderModal();
        });

        // Enter key in input
        input?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.handleConfirmFolder();
            }
        });
    }

    /**
     * Create a new file
     */
    async createNewFile(parentPath = null) {
        if (!this.rootPath) {
            alert('Please open a folder first');
            return;
        }

        const fileName = prompt('Enter file name:');
        if (!fileName) return;

        const basePath = parentPath || this.rootPath;
        const fullPath = `${basePath}/${fileName}`;

        try {
            const response = await fetch(`${CONFIG.API_BASE_URL}/files/create`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    path: fullPath,
                    is_folder: false
                })
            });

            if (!response.ok) throw new Error('Failed to create file');

            console.log('✅ Created file:', fullPath);
            window.toast?.success(`File created: ${fileName}`);
            this.loadFileTree();
        } catch (error) {
            console.error('Failed to create file:', error);
            window.toast?.error(`Failed to create file: ${error.message}`);
        }
    }

    /**
     * Create a new folder
     */
    async createNewFolder(parentPath = null) {
        if (!this.rootPath) {
            alert('Please open a folder first');
            return;
        }

        const folderName = prompt('Enter folder name:');
        if (!folderName) return;

        const basePath = parentPath || this.rootPath;
        const fullPath = `${basePath}/${folderName}`;

        try {
            const response = await fetch(`${CONFIG.API_BASE_URL}/files/create`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    path: fullPath,
                    is_folder: true
                })
            });

            if (!response.ok) throw new Error('Failed to create folder');

            console.log('✅ Created folder:', fullPath);
            window.toast?.success(`Folder created: ${folderName}`);
            this.loadFileTree();
        } catch (error) {
            console.error('Failed to create folder:', error);
            window.toast?.error(`Failed to create folder: ${error.message}`);
        }
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

        // Open folder button
        document.getElementById('openFolderActionBtn')?.addEventListener('click', () => {
            this.openFolderDialog();
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
