/**
 * 🔗 Gopher Minigolf - QR Share Module
 * Modulare QR-Code Funktion für Game Sharing
 * 
 * Usage: Einfach in score_detail.html einbinden:
 *   <script src="/static/js/qr-share.js"></script>
 * 
 * Das Script initialisiert sich automatisch und fügt den QR-Button/Modal hinzu.
 */

(function() {
    'use strict';

    // ==========================================
    // KONFIGURATION
    // ==========================================
    const CONFIG = {
        qrSize: 200,           // QR-Code Größe (klein)
        qrSizeLarge: 280,      // QR-Code Größe (Modal)
        buttonPosition: 'header', // Wo der Button erscheint
        debug: false
    };

    // ==========================================
    // QR CODE LIBRARY (Inline - keine externe Abhängigkeit)
    // Minimale QR-Code Generierung mit Canvas
    // ==========================================
    
    // Wir nutzen eine CDN-Bibliothek für bessere QR-Codes
    const QR_LIB_URL = 'https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js';

    // ==========================================
    // STYLES (Inline CSS)
    // ==========================================
    const STYLES = `
        /* QR Button im Header */
        .qr-share-btn {
            background: rgba(255, 255, 255, 0.15);
            border: none;
            color: white;
            width: 40px;
            height: 40px;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2em;
            flex-shrink: 0;
        }

        .qr-share-btn:hover {
            background: rgba(255, 255, 255, 0.25);
            transform: scale(1.05);
        }

        .qr-share-btn:active {
            transform: scale(0.95);
        }

        /* QR Preview (klein im Header) */
        .qr-preview {
            width: 40px;
            height: 40px;
            background: white;
            border-radius: 8px;
            padding: 3px;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
            flex-shrink: 0;
        }

        .qr-preview:hover {
            transform: scale(1.1);
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.25);
        }

        .qr-preview img,
        .qr-preview canvas {
            width: 100%;
            height: 100%;
            border-radius: 5px;
        }

        /* QR Modal Overlay */
        .qr-modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.7);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 3000;
            backdrop-filter: blur(5px);
            -webkit-backdrop-filter: blur(5px);
        }

        .qr-modal-overlay.show {
            display: flex;
            animation: fadeIn 0.3s ease-out;
        }

        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }

        .qr-modal {
            background: white;
            border-radius: 20px;
            padding: 30px;
            text-align: center;
            box-shadow: 0 25px 80px rgba(0, 0, 0, 0.4);
            max-width: 350px;
            width: 90%;
            animation: slideUp 0.3s ease-out;
        }

        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateY(30px) scale(0.95);
            }
            to {
                opacity: 1;
                transform: translateY(0) scale(1);
            }
        }

        .qr-modal-header {
            margin-bottom: 20px;
        }

        .qr-modal-title {
            font-size: 1.4em;
            font-weight: 700;
            color: #3b5c6c;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }

        .qr-modal-subtitle {
            font-size: 0.9em;
            color: #64748b;
        }

        .qr-code-container {
            background: #f8fafc;
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 20px;
            border: 2px solid #e2e8f0;
        }

        .qr-code-container canvas,
        .qr-code-container img {
            display: block;
            margin: 0 auto;
            border-radius: 8px;
        }

        .qr-url-display {
            background: #f1f5f9;
            border-radius: 10px;
            padding: 12px 15px;
            margin-bottom: 20px;
            font-family: monospace;
            font-size: 0.8em;
            color: #64748b;
            word-break: break-all;
            border: 1px solid #e2e8f0;
        }

        .qr-modal-actions {
            display: flex;
            gap: 10px;
            flex-direction: column;
        }

        .qr-action-btn {
            padding: 14px 20px;
            border: none;
            border-radius: 12px;
            font-size: 0.95em;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }

        .qr-btn-primary {
            background: #f8c098;
            color: #2d3748;
        }

        .qr-btn-primary:hover {
            background: #f2bc91;
            transform: translateY(-2px);
        }

        .qr-btn-secondary {
            background: #f1f5f9;
            color: #64748b;
        }

        .qr-btn-secondary:hover {
            background: #e2e8f0;
        }

        .qr-btn-close {
            background: #3b5c6c;
            color: white;
        }

        .qr-btn-close:hover {
            background: #2a4a58;
        }

        /* Copy Success Animation */
        .qr-copy-success {
            color: #10b981;
            font-weight: 600;
        }

        /* Toast Notification */
        .qr-toast {
            position: fixed;
            bottom: 80px;
            left: 50%;
            transform: translateX(-50%) translateY(100px);
            background: #10b981;
            color: white;
            padding: 12px 24px;
            border-radius: 10px;
            font-weight: 600;
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.2);
            transition: transform 0.3s ease, opacity 0.3s ease, visibility 0.3s ease;
            z-index: 3100;
            visibility: hidden;
            opacity: 0;
        }

        .qr-toast.show {
            transform: translateX(-50%) translateY(0);
            visibility: visible;
            opacity: 1;
        }

        /* Mobile Optimierung */
        @media (max-width: 768px) {
            .qr-preview {
                width: 35px;
                height: 35px;
            }

            .qr-share-btn {
                width: 35px;
                height: 35px;
                font-size: 1em;
            }

            .qr-modal {
                padding: 25px 20px;
                margin: 15px;
            }

            .qr-modal-title {
                font-size: 1.2em;
            }

            .qr-code-container {
                padding: 15px;
            }
        }
    `;

    // ==========================================
    // HAUPT-KLASSE
    // ==========================================
    class QRShare {
        constructor() {
            this.gameUrl = window.location.href;
            this.gameId = this.extractGameId();
            this.qrLibLoaded = false;
            this.modalOpen = false;
            this.toastTimeout = null;  // Timeout-Referenz für Toast

            this.init();
        }

        // Game ID aus URL extrahieren
        extractGameId() {
            const match = window.location.pathname.match(/\/score\/(\d+)/);
            return match ? match[1] : null;
        }

        // Initialisierung
        async init() {
            if (!this.gameId) {
                this.log('Keine Game ID gefunden - QR Share nicht aktiviert');
                return;
            }

            this.log('QR Share initialisiert für Game #' + this.gameId);

            // Styles einfügen
            this.injectStyles();

            // QR Library laden
            await this.loadQRLibrary();

            // UI erstellen
            this.createUI();

            // Event Listeners
            this.bindEvents();
        }

        log(message) {
            if (CONFIG.debug) {
                console.log('🔗 QR Share:', message);
            }
        }

        // Styles in DOM einfügen
        injectStyles() {
            const styleEl = document.createElement('style');
            styleEl.id = 'qr-share-styles';
            styleEl.textContent = STYLES;
            document.head.appendChild(styleEl);
        }

        // QR Code Library laden
        loadQRLibrary() {
            return new Promise((resolve, reject) => {
                // Prüfen ob bereits geladen
                if (window.QRCode) {
                    this.qrLibLoaded = true;
                    resolve();
                    return;
                }

                const script = document.createElement('script');
                script.src = QR_LIB_URL;
                script.onload = () => {
                    this.qrLibLoaded = true;
                    this.log('QR Library geladen');
                    resolve();
                };
                script.onerror = () => {
                    console.error('QR Library konnte nicht geladen werden');
                    reject(new Error('QR Library load failed'));
                };
                document.head.appendChild(script);
            });
        }

        // UI Elemente erstellen
        createUI() {
            // 1. QR Button/Preview im Header einfügen
            this.createHeaderButton();

            // 2. Modal erstellen
            this.createModal();

            // 3. Toast für Feedback
            this.createToast();
        }

        // Header Button erstellen
        createHeaderButton() {
            const header = document.querySelector('.header');
            if (!header) {
                this.log('Header nicht gefunden');
                return;
            }

            // Container für QR Preview
            const qrContainer = document.createElement('div');
            qrContainer.id = 'qr-header-container';
            qrContainer.style.cssText = `
                position: absolute;
                top: 15px;
                right: 15px;
                display: flex;
                align-items: center;
                gap: 10px;
                z-index: 101;
            `;

            // QR Preview (kleines Bild)
            const qrPreview = document.createElement('div');
            qrPreview.id = 'qr-preview';
            qrPreview.className = 'qr-preview';
            qrPreview.title = 'QR-Code zum Teilen';
            qrPreview.innerHTML = '<div id="qr-preview-code"></div>';

            qrContainer.appendChild(qrPreview);

            // Header muss position: relative haben
            header.style.position = 'relative';
            header.appendChild(qrContainer);

            // Kleinen QR-Code generieren
            setTimeout(() => {
                this.generateQRCode('qr-preview-code', 34);
            }, 100);
        }

        // Modal erstellen
        createModal() {
            const modal = document.createElement('div');
            modal.id = 'qr-modal-overlay';
            modal.className = 'qr-modal-overlay';
            modal.innerHTML = `
                <div class="qr-modal">
                    <div class="qr-modal-header">
                        <div class="qr-modal-title">
                            📱 Spiel teilen
                        </div>
                        <div class="qr-modal-subtitle">
                            Mitspieler können diesen QR-Code scannen
                        </div>
                    </div>

                    <div class="qr-code-container">
                        <div id="qr-modal-code"></div>
                    </div>

                    <div class="qr-url-display" id="qr-url-display">
                        ${this.gameUrl}
                    </div>

                    <div class="qr-modal-actions">
                        <button class="qr-action-btn qr-btn-primary" id="qr-copy-btn">
                            📋 Link kopieren
                        </button>
                        <button class="qr-action-btn qr-btn-secondary" id="qr-share-native-btn" style="display: none;">
                            🔗 Teilen...
                        </button>
                        <button class="qr-action-btn qr-btn-close" id="qr-close-btn">
                            ✕ Schliessen
                        </button>
                    </div>
                </div>
            `;

            document.body.appendChild(modal);

            // Native Share Button nur anzeigen wenn verfügbar
            if (navigator.share) {
                document.getElementById('qr-share-native-btn').style.display = 'flex';
            }
        }

        // Toast erstellen (initial leer und versteckt)
        createToast() {
            const toast = document.createElement('div');
            toast.id = 'qr-toast';
            toast.className = 'qr-toast';
            toast.textContent = '';  // Leer - Text kommt erst bei showToast()
            document.body.appendChild(toast);
        }

        // QR Code generieren
        generateQRCode(containerId, size = CONFIG.qrSize) {
            if (!this.qrLibLoaded || !window.QRCode) {
                this.log('QR Library nicht verfügbar');
                return;
            }

            const container = document.getElementById(containerId);
            if (!container) {
                this.log('Container nicht gefunden: ' + containerId);
                return;
            }

            // Container leeren
            container.innerHTML = '';

            // QR Code erstellen
            new QRCode(container, {
                text: this.gameUrl,
                width: size,
                height: size,
                colorDark: '#3b5c6c',
                colorLight: '#ffffff',
                correctLevel: QRCode.CorrectLevel.M
            });

            this.log('QR Code generiert in: ' + containerId);
        }

        // Event Listeners
        bindEvents() {
            // Preview Click -> Modal öffnen
            const preview = document.getElementById('qr-preview');
            if (preview) {
                preview.addEventListener('click', () => this.openModal());
            }

            // Modal schliessen
            const closeBtn = document.getElementById('qr-close-btn');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => this.closeModal());
            }

            // Overlay Click -> schliessen
            const overlay = document.getElementById('qr-modal-overlay');
            if (overlay) {
                overlay.addEventListener('click', (e) => {
                    if (e.target === overlay) {
                        this.closeModal();
                    }
                });
            }

            // Link kopieren
            const copyBtn = document.getElementById('qr-copy-btn');
            if (copyBtn) {
                copyBtn.addEventListener('click', () => this.copyLink());
            }

            // Native Share
            const shareBtn = document.getElementById('qr-share-native-btn');
            if (shareBtn) {
                shareBtn.addEventListener('click', () => this.nativeShare());
            }

            // Escape Key
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && this.modalOpen) {
                    this.closeModal();
                }
            });
        }

        // Modal öffnen
        openModal() {
            const overlay = document.getElementById('qr-modal-overlay');
            if (overlay) {
                overlay.classList.add('show');
                this.modalOpen = true;

                // Grossen QR Code generieren
                setTimeout(() => {
                    this.generateQRCode('qr-modal-code', CONFIG.qrSizeLarge);
                }, 100);
            }
        }

        // Modal schliessen
        closeModal() {
            const overlay = document.getElementById('qr-modal-overlay');
            if (overlay) {
                overlay.classList.remove('show');
                this.modalOpen = false;
            }
        }

        // Link kopieren
        async copyLink() {
            try {
                await navigator.clipboard.writeText(this.gameUrl);
                this.showToast('✅ Link kopiert!');

                // Button kurz ändern
                const btn = document.getElementById('qr-copy-btn');
                if (btn) {
                    const originalText = btn.innerHTML;
                    btn.innerHTML = '✅ Kopiert!';
                    btn.classList.add('qr-copy-success');
                    setTimeout(() => {
                        btn.innerHTML = originalText;
                        btn.classList.remove('qr-copy-success');
                    }, 2000);
                }
            } catch (err) {
                // Fallback für ältere Browser
                const textArea = document.createElement('textarea');
                textArea.value = this.gameUrl;
                textArea.style.position = 'fixed';
                textArea.style.left = '-9999px';
                document.body.appendChild(textArea);
                textArea.select();
                document.execCommand('copy');
                document.body.removeChild(textArea);
                this.showToast('✅ Link kopiert!');
            }
        }

        // Native Share API
        async nativeShare() {
            if (navigator.share) {
                try {
                    await navigator.share({
                        title: '🏌️ Gopher Minigolf',
                        text: 'Tritt meinem Minigolf-Spiel bei!',
                        url: this.gameUrl
                    });
                    this.log('Shared successfully');
                } catch (err) {
                    if (err.name !== 'AbortError') {
                        console.error('Share failed:', err);
                    }
                }
            }
        }

        // Toast anzeigen - VERBESSERT mit clearTimeout
        showToast(message) {
            const toast = document.getElementById('qr-toast');
            if (toast) {
                // Alten Timeout clearen falls vorhanden
                if (this.toastTimeout) {
                    clearTimeout(this.toastTimeout);
                }
                
                // Toast anzeigen
                toast.textContent = message;
                toast.classList.add('show');
                
                // Nach 2.5 Sekunden ausblenden
                this.toastTimeout = setTimeout(() => {
                    toast.classList.remove('show');
                    this.toastTimeout = null;
                }, 2500);
            }
        }
    }

    // ==========================================
    // AUTO-INITIALISIERUNG
    // ==========================================
    
    // Warten bis DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            window.gopherQRShare = new QRShare();
        });
    } else {
        window.gopherQRShare = new QRShare();
    }

    // Debug-Zugriff
    window.GopherQRShare = QRShare;

})();
