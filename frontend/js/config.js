/**
 * AI Code Editor - Configuration
 * Central configuration for the application
 */

const CONFIG = {
    // API Configuration
    API_BASE_URL: 'http://localhost:8000/api',
    
    // Editor Settings
    EDITOR: {
        defaultLanguage: 'python',
        theme: 'vs-dark',
        fontSize: 14,
        tabSize: 4,
        wordWrap: 'off',
        minimap: { enabled: true },
        automaticLayout: true,
        scrollBeyondLastLine: false,
        lineNumbers: 'on',
        renderWhitespace: 'selection',
        bracketPairColorization: { enabled: true }
    },
    
    // Terminal Settings
    TERMINAL: {
        theme: {
            background: '#1e1e1e',
            foreground: '#cccccc',
            cursor: '#ffffff',
            cursorAccent: '#1e1e1e',
            selectionBackground: '#264f78',
            black: '#000000',
            red: '#cd3131',
            green: '#0dbc79',
            yellow: '#e5e510',
            blue: '#2472c8',
            magenta: '#bc3fbc',
            cyan: '#11a8cd',
            white: '#e5e5e5',
            brightBlack: '#666666',
            brightRed: '#f14c4c',
            brightGreen: '#23d18b',
            brightYellow: '#f5f543',
            brightBlue: '#3b8eea',
            brightMagenta: '#d670d6',
            brightCyan: '#29b8db',
            brightWhite: '#ffffff'
        },
        fontFamily: '"Cascadia Code", "Fira Code", Consolas, monospace',
        fontSize: 13,
        cursorBlink: true,
        cursorStyle: 'block'
    },
    
    // File Tree Settings
    FILE_TREE: {
        rootPath: './workspace', // Default workspace path
        excludePatterns: [
            '__pycache__',
            '.git',
            'node_modules',
            '.DS_Store',
            '*.pyc',
            '.env'
        ]
    },
    
    // Auto-save Settings
    AUTO_SAVE: {
        enabled: true,
        delay: 1000 // milliseconds
    },
    
    // Agent Settings
    AGENT: {
        defaultModel: 'auto',
        maxContextLength: 4000,
        streamingEnabled: true
    },
    
    // Keyboard Shortcuts
    SHORTCUTS: {
        save: 'Ctrl+S',
        run: 'Ctrl+R',
        commandPalette: 'Ctrl+K',
        toggleFileTree: 'Ctrl+B',
        toggleTerminal: 'Ctrl+J',
        toggleAgent: 'Ctrl+/',
        newFile: 'Ctrl+N',
        closeTab: 'Ctrl+W'
    },
    
    // Language configurations
    LANGUAGES: {
        python: {
            extension: '.py',
            icon: 'file-code',
            color: '#3572A5'
        },
        javascript: {
            extension: '.js',
            icon: 'file-code',
            color: '#f7df1e'
        },
        typescript: {
            extension: '.ts',
            icon: 'file-code',
            color: '#3178c6'
        },
        html: {
            extension: '.html',
            icon: 'file-code',
            color: '#e34c26'
        },
        css: {
            extension: '.css',
            icon: 'file-code',
            color: '#264de4'
        },
        json: {
            extension: '.json',
            icon: 'file-json',
            color: '#cbcb41'
        },
        markdown: {
            extension: '.md',
            icon: 'file-text',
            color: '#083fa1'
        }
    }
};

// Language detection helper
function detectLanguage(filename) {
    const extension = filename.split('.').pop().toLowerCase();
    const languageMap = {
        'py': 'python',
        'js': 'javascript',
        'ts': 'typescript',
        'jsx': 'javascript',
        'tsx': 'typescript',
        'html': 'html',
        'htm': 'html',
        'css': 'css',
        'scss': 'scss',
        'json': 'json',
        'md': 'markdown',
        'txt': 'plaintext',
        'sh': 'shell',
        'bash': 'shell',
        'sql': 'sql',
        'yaml': 'yaml',
        'yml': 'yaml',
        'xml': 'xml',
        'java': 'java',
        'c': 'c',
        'cpp': 'cpp',
        'h': 'c',
        'hpp': 'cpp',
        'cs': 'csharp',
        'go': 'go',
        'rs': 'rust',
        'rb': 'ruby',
        'php': 'php'
    };
    return languageMap[extension] || 'plaintext';
}

// File icon helper
function getFileIcon(filename, isFolder = false) {
    if (isFolder) return 'folder';
    
    const extension = filename.split('.').pop().toLowerCase();
    const iconMap = {
        'py': 'file-code',
        'js': 'file-code',
        'ts': 'file-code',
        'html': 'file-code',
        'css': 'file-code',
        'json': 'file-json',
        'md': 'file-text',
        'txt': 'file-text',
        'png': 'image',
        'jpg': 'image',
        'jpeg': 'image',
        'gif': 'image',
        'svg': 'image'
    };
    return iconMap[extension] || 'file';
}

// Export for use in other modules
window.CONFIG = CONFIG;
window.detectLanguage = detectLanguage;
window.getFileIcon = getFileIcon;
