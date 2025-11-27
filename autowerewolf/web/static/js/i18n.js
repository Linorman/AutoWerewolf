const I18N = {
    currentLanguage: 'en',
    translations: {},

    async load(lang) {
        try {
            const res = await fetch(`/api/translations/${lang}`);
            const data = await res.json();
            this.translations = data.translations;
            this.currentLanguage = lang;
            this.apply();
            localStorage.setItem('werewolf_lang', lang);
        } catch (e) {
            console.error('Failed to load translations:', e);
        }
    },

    t(key, fallback) {
        return this.translations[key] || fallback || key;
    },

    apply() {
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            const text = this.t(key);
            if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                el.placeholder = text;
            } else {
                el.textContent = text;
            }
        });

        document.querySelectorAll('[data-i18n-title]').forEach(el => {
            const key = el.getAttribute('data-i18n-title');
            const text = this.t(key);
            if (text) el.title = text;
        });

        document.querySelectorAll('select option[data-i18n]').forEach(opt => {
            const key = opt.getAttribute('data-i18n');
            opt.textContent = this.t(key);
        });
    },

    init() {
        const savedLang = localStorage.getItem('werewolf_lang') || 'en';
        const langSelect = document.getElementById('language-select');
        if (langSelect) {
            langSelect.value = savedLang;
            langSelect.addEventListener('change', (e) => this.load(e.target.value));
        }
        this.load(savedLang);
    }
};

document.addEventListener('DOMContentLoaded', () => I18N.init());

