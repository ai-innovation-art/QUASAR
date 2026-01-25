/**
 * QUASAR - Settings Module
 * Handles user preferences and workspace configuration
 */

class SettingsManager {
    constructor() {
        this.defaults = {
            theme: 'dark',
            fontSize: 14,
            wordWrap: false,
            minimap: true,
            lineNumbers: true,
            aiStreaming: true,
            aiThinking: true
        };

        this.settings = JSON.parse(localStorage.getItem('quasar_settings')) || { ...this.defaults };
    }

    init() {
        this.setupEventListeners();
        this.syncUI();
        this.applySettings();
        this.loadApiKeys();
    }

    /**
     * Save settings to localStorage
     */
    save() {
        localStorage.setItem('quasar_settings', JSON.stringify(this.settings));
    }

    /**
     * Apply all settings to the application
     */
    applySettings() {
        // Apply theme
        this.applyTheme(this.settings.theme);

        // Apply editor settings if editor is loaded
        if (window.editorManager) {
            this.applyEditorSettings();
        }

        // Apply AI settings
        if (window.agentManager) {
            window.agentManager.streamingEnabled = this.settings.aiStreaming;
        }
    }

    /**
     * Apply theme to the application body
     */
    applyTheme(theme) {
        document.body.className = `theme-${theme}`;

        // Update Monaco theme (only if monaco is loaded)
        if (typeof monaco !== 'undefined' && window.editorManager) {
            const monacoTheme = theme === 'light' ? 'vs' : 'vs-dark';
            window.editorManager.setTheme(monacoTheme);
        }
    }

    /**
     * Update Monaco editor options based on current settings
     */
    applyEditorSettings() {
        if (!window.editorManager) return;

        const options = {
            fontSize: this.settings.fontSize,
            wordWrap: this.settings.wordWrap ? 'on' : 'off',
            minimap: { enabled: this.settings.minimap },
            lineNumbers: this.settings.lineNumbers ? 'on' : 'off'
        };

        // Apply globally to all editor instances (only if they exist)
        if (window.editorManager.mainEditor) {
            window.editorManager.mainEditor.updateOptions(options);
        }
        if (window.editorManager.secondaryEditor) {
            window.editorManager.secondaryEditor.updateOptions(options);
        }

        // Update UI labels if needed
        const fontSizeLabel = document.getElementById('fontSizeLabel');
        if (fontSizeLabel) {
            fontSizeLabel.textContent = `${this.settings.fontSize}px`;
        }
    }

    /**
     * Open the settings modal
     */
    openModal() {
        const modal = document.getElementById('settingsModal');
        if (modal) {
            modal.classList.add('active');
            this.syncUI();
        }
    }

    /**
     * Close the settings modal
     */
    closeModal() {
        const modal = document.getElementById('settingsModal');
        if (modal) {
            modal.classList.remove('active');
        }
    }

    /**
     * Sync the settings UI with current settings values
     */
    syncUI() {
        const themeSelect = document.getElementById('setting-theme');
        if (themeSelect) themeSelect.value = this.settings.theme;

        const fontSizeRange = document.getElementById('setting-fontSize');
        if (fontSizeRange) {
            fontSizeRange.value = this.settings.fontSize;
            document.getElementById('setting-fontSizeValue').textContent = `${this.settings.fontSize}px`;
        }

        const wordWrapCheck = document.getElementById('setting-wordWrap');
        if (wordWrapCheck) wordWrapCheck.checked = this.settings.wordWrap;

        const minimapCheck = document.getElementById('setting-minimap');
        if (minimapCheck) minimapCheck.checked = this.settings.minimap;

        const lineNumbersCheck = document.getElementById('setting-lineNumbers');
        if (lineNumbersCheck) lineNumbersCheck.checked = this.settings.lineNumbers;

        const aiStreamingCheck = document.getElementById('setting-aiStreaming');
        if (aiStreamingCheck) aiStreamingCheck.checked = this.settings.aiStreaming;
    }

    /**
     * Setup event listeners for modal and settings controls
     */
    setupEventListeners() {
        // Modal toggles
        document.getElementById('settingsBtn')?.addEventListener('click', () => this.openModal());
        document.getElementById('closeSettingsBtn')?.addEventListener('click', () => this.closeModal());
        document.getElementById('settingsModal')?.addEventListener('click', (e) => {
            if (e.target === document.getElementById('settingsModal')) this.closeModal();
        });

        // Tab switching
        const navItems = document.querySelectorAll('.settings-nav-item');
        navItems.forEach(item => {
            item.addEventListener('click', () => {
                const targetId = item.dataset.target;

                // Update nav
                navItems.forEach(nav => nav.classList.remove('active'));
                item.classList.add('active');

                // Update content
                const sections = document.querySelectorAll('.settings-section');
                sections.forEach(section => section.classList.remove('active'));
                document.getElementById(targetId)?.classList.add('active');
            });
        });

        // Setting changes
        document.getElementById('setting-theme')?.addEventListener('change', (e) => {
            this.settings.theme = e.target.value;
            this.applyTheme(this.settings.theme);
            this.save();
        });

        document.getElementById('setting-fontSize')?.addEventListener('input', (e) => {
            const val = parseInt(e.target.value);
            this.settings.fontSize = val;
            document.getElementById('setting-fontSizeValue').textContent = `${val}px`;
            this.applyEditorSettings();
            this.save();
        });

        document.getElementById('setting-wordWrap')?.addEventListener('change', (e) => {
            this.settings.wordWrap = e.target.checked;
            this.applyEditorSettings();
            this.save();
        });

        document.getElementById('setting-minimap')?.addEventListener('change', (e) => {
            this.settings.minimap = e.target.checked;
            this.applyEditorSettings();
            this.save();
        });

        document.getElementById('setting-lineNumbers')?.addEventListener('change', (e) => {
            this.settings.lineNumbers = e.target.checked;
            this.applyEditorSettings();
            this.save();
        });

        document.getElementById('setting-aiStreaming')?.addEventListener('change', (e) => {
            this.settings.aiStreaming = e.target.checked;
            if (window.agentManager) {
                window.agentManager.streamingEnabled = this.settings.aiStreaming;
            }
            this.save();
        });

        // API Keys event listeners
        document.getElementById('saveApiKeysBtn')?.addEventListener('click', () => this.saveApiKeys());
        document.getElementById('clearApiKeysBtn')?.addEventListener('click', () => this.clearApiKeys());

        // Multi-key add buttons
        document.querySelectorAll('.add-key-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const provider = btn.dataset.provider;
                this.addKeyRow(provider);
            });
        });
    }

    /**
     * Add a key row to the UI
     */
    addKeyRow(provider, value = '') {
        const list = document.getElementById(`${provider}KeysList`);
        if (!list) return;

        const row = document.createElement('div');
        row.className = 'key-row';
        row.innerHTML = `
            <input type="password" class="api-key-input" placeholder="Enter key..." value="${value}">
            <button class="remove-key-btn" title="Remove key">
                <i data-lucide="trash-2"></i>
            </button>
        `;

        row.querySelector('.remove-key-btn').addEventListener('click', () => {
            row.remove();
        });

        list.appendChild(row);
        if (window.lucide) lucide.createIcons();
    }

    /**
     * Get keys from the UI for a provider
     */
    getKeysFromUI(provider) {
        const list = document.getElementById(`${provider}KeysList`);
        if (!list) return [];
        const inputs = list.querySelectorAll('input');
        return Array.from(inputs).map(i => i.value.trim()).filter(v => v !== '');
    }

    /**
     * Save API keys to localStorage
     */
    saveApiKeys() {
        const apiKeys = {
            groq: this.getKeysFromUI('groq'),
            openai: this.getKeysFromUI('openai'),
            anthropic: this.getKeysFromUI('anthropic'),
            cerebras: this.getKeysFromUI('cerebras'),
            ollamaUrl: document.getElementById('setting-ollamaUrl')?.value?.trim() || ''
        };

        localStorage.setItem('quasar_api_keys', JSON.stringify(apiKeys));

        if (window.toast) {
            window.toast.success('API keys saved successfully');
        }
        console.log('✅ API keys saved to localStorage');
    }

    /**
     * Load API keys from localStorage
     */
    loadApiKeys() {
        const saved = localStorage.getItem('quasar_api_keys');

        // Clear existing lists first
        ['groq', 'openai', 'anthropic', 'cerebras'].forEach(p => {
            const list = document.getElementById(`${p}KeysList`);
            if (list) list.innerHTML = '';
        });

        if (saved) {
            try {
                const apiKeys = JSON.parse(saved);

                // Load multiple keys
                if (Array.isArray(apiKeys.groq)) apiKeys.groq.forEach(key => this.addKeyRow('groq', key));
                else if (typeof apiKeys.groq === 'string' && apiKeys.groq) this.addKeyRow('groq', apiKeys.groq);

                if (Array.isArray(apiKeys.openai)) apiKeys.openai.forEach(key => this.addKeyRow('openai', key));
                else if (typeof apiKeys.openai === 'string' && apiKeys.openai) this.addKeyRow('openai', apiKeys.openai);

                if (Array.isArray(apiKeys.anthropic)) apiKeys.anthropic.forEach(key => this.addKeyRow('anthropic', key));
                else if (typeof apiKeys.anthropic === 'string' && apiKeys.anthropic) this.addKeyRow('anthropic', apiKeys.anthropic);

                if (Array.isArray(apiKeys.cerebras)) apiKeys.cerebras.forEach(key => this.addKeyRow('cerebras', key));
                else if (typeof apiKeys.cerebras === 'string' && apiKeys.cerebras) this.addKeyRow('cerebras', apiKeys.cerebras);

                if (apiKeys.ollamaUrl && document.getElementById('setting-ollamaUrl')) {
                    document.getElementById('setting-ollamaUrl').value = apiKeys.ollamaUrl;
                }

                console.log('🔑 API keys loaded from localStorage');
            } catch (e) {
                console.warn('Failed to parse saved API keys:', e);
            }
        }

        // Add at least one empty row if none loaded
        ['groq', 'openai', 'anthropic', 'cerebras'].forEach(p => {
            const list = document.getElementById(`${p}KeysList`);
            if (list && list.children.length === 0) {
                this.addKeyRow(p);
            }
        });
    }

    /**
     * Clear all API keys
     */
    clearApiKeys() {
        ['groq', 'openai', 'anthropic', 'cerebras'].forEach(p => {
            const list = document.getElementById(`${p}KeysList`);
            if (list) {
                list.innerHTML = '';
                this.addKeyRow(p);
            }
        });

        if (document.getElementById('setting-ollamaUrl')) {
            document.getElementById('setting-ollamaUrl').value = '';
        }

        localStorage.removeItem('quasar_api_keys');

        if (window.toast) {
            window.toast.info('API keys cleared');
        }
        console.log('🗑️ API keys cleared');
    }

    /**
     * Get API keys for use in requests
     */
    getApiKeys() {
        const saved = localStorage.getItem('quasar_api_keys');
        if (saved) {
            try {
                return JSON.parse(saved);
            } catch (e) {
                return {};
            }
        }
        return {};
    }


}

// Global instance
window.settingsManager = new SettingsManager();
