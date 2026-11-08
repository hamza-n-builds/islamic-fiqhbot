document.addEventListener('DOMContentLoaded', () => {

    // ── Backend URL (needed early for verse fetch) ──────────────
    const BACKEND_URL = (typeof CONFIG !== 'undefined' && CONFIG.BACKEND_URL)
        ? CONFIG.BACKEND_URL.replace(/\/+$/, '')
        : 'http://localhost:5000';

    // ── Loading Screen ──────────────────────────────────────────
    const loadingScreen = document.getElementById('loading-screen');
    const verseArabic = document.querySelector('.loader-verse-arabic');
    const verseTrans = document.querySelector('.loader-verse-translation');
    const verseRef = document.querySelector('.loader-verse-ref');

    // Fetch a random verse from the backend
    (async function loadVerse() {
        if (!verseArabic) return;
        try {
            const resp = await fetch(`${BACKEND_URL}/verse`);
            if (resp.ok) {
                const v = await resp.json();
                verseArabic.textContent = v.arabic;
                verseTrans.textContent = `"${v.english}"`;
                const surahAr = v.surah_ar || '';
                verseRef.textContent = `${surahAr} ${v.chapter}:${v.ayah}`;
            }
        } catch (e) { console.warn("Could not load verse", e); }
    })();

    // ── Utility: Detect Urdu/Arabic text ────────────────────────
    function isUrduText(text) {
        if (!text) return false;
        return /[\u0600-\u06FF\u0750-\u077F]/.test(text);
    }

    const loadStart = Date.now();
    const enterBtn = document.getElementById('loader-enter-btn');
    const loaderBar = document.getElementById('loader-bar-track');

    const showEnterBtn = () => {
        const elapsed = Date.now() - loadStart;
        const delay = Math.max(0, 2800 - elapsed);
        setTimeout(() => {
            enterBtn.classList.add('show');
            loaderBar.style.opacity = '0';
            loaderBar.style.height = '0';
            loaderBar.style.margin = '0';
        }, delay);
    };

    enterBtn.addEventListener('click', () => {
        loadingScreen.classList.add('hide');
    });

    // ── DOM Elements ─────────────────────────────────────────────
    const chatContainer = document.getElementById('chat-container');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const micBtn = document.getElementById('mic-btn');
    const sttStatus = document.getElementById('stt-status');
    const sttStatusText = document.getElementById('stt-status-text');
    const sttCancelBtn = document.getElementById('stt-cancel-btn');
    const chatIntro = document.getElementById('chat-intro');
    const newChatBtn = document.getElementById('new-chat-btn');
    const historyList = document.getElementById('history-list');
    const themeToggleBtn = document.getElementById('theme-toggle-btn');
    const themeToggleText = document.getElementById('theme-toggle-text');
    const whatsappLink = document.querySelector('.whatsapp-action');
    const whatsappNumber = String((typeof CONFIG !== 'undefined' && CONFIG.WHATSAPP_NUMBER) || '').replace(/\D/g, '');
    if (whatsappLink && /^\d{8,15}$/.test(whatsappNumber)) {
        whatsappLink.href = `https://wa.me/${whatsappNumber}?text=Assalamu%20Alaikum`;
        whatsappLink.hidden = false;
    }

    // ── State ────────────────────────────────────────────────────
    let chats = [];
    const pendingChats = new Set();
    try {
        const savedChats = JSON.parse(localStorage.getItem('islamic_chatbot_chats') || '[]');
        if (Array.isArray(savedChats)) {
            chats = savedChats.filter(chat => chat && typeof chat.id === 'string'
                && typeof chat.title === 'string' && Array.isArray(chat.messages))
                .map(chat => ({ ...chat, messages: chat.messages.filter(msg => msg
                    && (msg.sender === 'user' || msg.sender === 'bot')
                    && typeof msg.text === 'string') }));
        }
    } catch (error) {
        console.warn('Saved chat history could not be read:', error);
    }
    let currentChatId = localStorage.getItem('islamic_chatbot_current_id') || null;
    let isRecording = false;
    let recognition = null;
    let currentAudio = null; // track server TTS audio so we can stop it

    // ── Theme Management ──────────────────────────────────────────
    let currentTheme = localStorage.getItem('islamic_chatbot_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', currentTheme);

    function updateThemeUI() {
        if (!themeToggleBtn || !themeToggleText) return;
        const action = currentTheme === 'light' ? 'dark' : 'light';
        themeToggleText.textContent = action === 'dark' ? 'Dark Mode' : 'Light Mode';
        themeToggleBtn.title = `Switch to ${action} mode`;
        themeToggleBtn.setAttribute('aria-label', themeToggleBtn.title);
    }
    updateThemeUI();

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => {
            currentTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', currentTheme);
            localStorage.setItem('islamic_chatbot_theme', currentTheme);
            updateThemeUI();
        });
    }

    // Escape source text before injecting into HTML.
    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    // ── Auto-scroll button ──────────────────────────────────────
    const scrollBtn = document.getElementById('scroll-bottom-btn');
    const chatContainerEl = document.getElementById('chat-container');

    chatContainerEl.addEventListener('scroll', () => {
        const threshold = 300;
        const atBottom = chatContainerEl.scrollHeight - chatContainerEl.scrollTop - chatContainerEl.clientHeight < threshold;
        scrollBtn.classList.toggle('visible', !atBottom);
    });

    scrollBtn.addEventListener('click', () => {
        chatContainerEl.scrollTo({ top: chatContainerEl.scrollHeight, behavior: 'smooth' });
    });

    // ── Hijri Date ──────────────────────────────────────────────
    function updateHijriDate() {
        const el = document.getElementById('hijri-date-text');
        if (!el) return;
        const now = new Date();
        // Simple estimation: Hijri year ≈ 2025 - 622 = 1403 (approx)
        // Use Intl API where available
        try {
            const formatter = new Intl.DateTimeFormat('en-u-ca-islamic', {
                day: 'numeric', month: 'long', year: 'numeric'
            });
            el.textContent = formatter.format(now);
        } catch {
            // Fallback: rough calculation
            const day = now.getDate();
            const month = now.getMonth() + 1;
            const year = now.getFullYear();
            const hijriYear = Math.floor((year - 622) * 0.97);
            el.textContent = `${day}/${month}/${hijriYear} AH`;
        }
    }
    updateHijriDate();

    // ── Initialization ───────────────────────────────────────────
    if (chats.length === 0) {
        createNewChat();
    } else {
        if (!currentChatId || !chats.find(c => c.id === currentChatId)) {
            currentChatId = chats[0].id;
        }
        loadChat(currentChatId);
    }
    renderHistory();


    // ════════════════════════════════════════════════════════════
    // SPEECH-TO-TEXT (STT) — Web Speech API (free, no API key)
    // Works in Chrome, Edge, Safari. Firefox needs a flag enabled.
    // ════════════════════════════════════════════════════════════

    function initSTT() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

        if (!SpeechRecognition) {
            micBtn.title = 'Voice input not supported in this browser. Use Chrome or Edge.';
            micBtn.style.opacity = '0.4';
            micBtn.style.cursor = 'not-allowed';
            return null;
        }

        const rec = new SpeechRecognition();
        rec.continuous = false;   // stop after one sentence
        rec.interimResults = true;    // show partial results while speaking
        rec.lang = 'en-US'; // default: English
        // To support Urdu: rec.lang = 'ur-PK';
        // To support Arabic: rec.lang = 'ar-SA';
        // Could auto-detect based on madhab, but English is safest default

        rec.onstart = () => {
            isRecording = true;
            micBtn.classList.add('recording');
            sttStatus.style.display = 'flex';
            sttStatusText.textContent = 'Listening... speak now';
        };

        rec.onresult = (event) => {
            let interim = '';
            let final = '';
            for (let i = event.resultIndex; i < event.results.length; i++) {
                if (event.results[i].isFinal) {
                    final += event.results[i][0].transcript;
                } else {
                    interim += event.results[i][0].transcript;
                }
            }
            // Show interim in input while speaking
            userInput.value = final || interim;
            resizeComposer();
            if (final) {
                sttStatusText.textContent = 'Got it! Processing...';
            }
        };

        rec.onend = () => {
            isRecording = false;
            micBtn.classList.remove('recording');
            sttStatus.style.display = 'none';
            // Auto-send if we captured something
            if (userInput.value.trim()) {
                setTimeout(() => sendMessage(), 300);
            }
        };

        rec.onerror = (event) => {
            isRecording = false;
            micBtn.classList.remove('recording');
            sttStatus.style.display = 'none';
            if (event.error === 'not-allowed') {
                alert('Microphone access denied. Please allow microphone access in your browser settings.');
            } else if (event.error !== 'aborted') {
                console.warn('STT error:', event.error);
            }
        };

        return rec;
    }

    recognition = initSTT();

    micBtn.addEventListener('click', () => {
        if (!recognition) return;
        if (isRecording) {
            recognition.stop();
        } else {
            userInput.value = '';
            resizeComposer();
            recognition.start();
        }
    });

    sttCancelBtn.addEventListener('click', () => {
        if (recognition && isRecording) {
            recognition.abort();
        }
    });


    // ════════════════════════════════════════════════════════════
    // TEXT-TO-SPEECH (TTS) — Web Speech Synthesis (free, built-in)
    // ════════════════════════════════════════════════════════════

    // Speak text using the backend /speak endpoint (native edge-tts voices for
    // English/Urdu/Arabic). This works on ANY machine — no OS voice install
    // needed — unlike the browser's speechSynthesis.
    async function speakText(text, onended) {
        stopSpeech();

        // Strip HTML/citations/markdown so they aren't read aloud.
        const cleanText = (text || '')
            .replace(/<[^>]*>/g, '')
            .replace(/\[.*?\]/g, '')
            .replace(/\*\*(.*?)\*\*/g, '$1')
            .trim();
        if (!cleanText) return;

        const lang = detectSpeechLang(cleanText);   // 'ur' | 'ar' | 'en'

        try {
            const resp = await fetch(`${BACKEND_URL}/speak`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: cleanText, lang: lang })
            });
            if (!resp.ok) throw new Error('speak failed: ' + resp.status);

            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const audio = new Audio(url);
            currentAudio = audio;
            audio.onended = () => {
                URL.revokeObjectURL(url);
                if (currentAudio === audio) currentAudio = null;
                if (typeof onended === 'function') onended();
            };
            audio.onerror = () => {
                URL.revokeObjectURL(url);
                if (currentAudio === audio) currentAudio = null;
                if (typeof onended === 'function') onended();
            };
            await audio.play();
        } catch (e) {
            console.error(e);
            if (typeof onended === 'function') onended();  // reset the button icon
        }
    }

    // Decide the spoken language from the text.
    // Urdu-specific letters -> Urdu; other Arabic-block -> Arabic; else English
    // (covers English AND Roman-Urdu, which is Latin script).
    function detectSpeechLang(text) {
        const t = text || '';
        if (/[\u067E\u0686\u0698\u06A9\u06AF\u06BA\u06BE\u06C1\u06CC\u06D2\u0679\u0688\u0691]/.test(t)) {
            return 'ur';
        }
        if (/[\u0600-\u06FF]/.test(t)) {
            return 'ar';
        }
        return 'en';
    }

    function stopSpeech() {
        if (currentAudio) {
            try { currentAudio.pause(); } catch (e) { }
            currentAudio = null;
        }
        // Also stop any legacy browser speech, just in case.
        if (window.speechSynthesis) {
            window.speechSynthesis.cancel();
        }
    }


    // ════════════════════════════════════════════════════════════
    // CHAT HISTORY MANAGEMENT
    // ════════════════════════════════════════════════════════════

    function createNewChat() {
        const newChat = {
            id: Date.now().toString(),
            title: 'New Chat',
            messages: [],
            madhab: 'General',
            timestamp: Date.now()
        };
        chats.unshift(newChat);
        saveChats();
        loadChat(newChat.id);
    }

    function saveChats() {
        try {
            localStorage.setItem('islamic_chatbot_chats', JSON.stringify(chats));
        } catch (error) {
            console.error('Chat history could not be saved:', error);
            if (!saveChats.warningShown) {
                saveChats.warningShown = true;
                alert('Chat history could not be saved on this device. Your current conversation is still visible, but it may be lost when you close the page.');
            }
        }
        renderHistory();
    }

    function loadChat(id) {
        currentChatId = id;
        localStorage.setItem('islamic_chatbot_current_id', currentChatId);

        const chat = chats.find(c => c.id === id);
        if (!chat) return;

        chatContainer.innerHTML = '';
        chatContainer.appendChild(chatIntro);
        chatIntro.hidden = chat.messages.length > 0;
        sendBtn.disabled = pendingChats.has(id);

        chat.messages.forEach(msg => {
            appendMessageUI(msg.sender, msg.text, false, msg.meta);
        });

        renderHistory();
        requestAnimationFrame(() => {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        });
    }

    function deleteChat(id, e) {
        e.stopPropagation();
        if (confirm('Are you sure you want to delete this chat?')) {
            chats = chats.filter(c => c.id !== id);
            saveChats();
            if (chats.length === 0) {
                createNewChat();
            } else if (currentChatId === id) {
                loadChat(chats[0].id);
            } else {
                renderHistory();
            }
        }
    }

    function renameChat(id, e) {
        e.stopPropagation();
        const chat = chats.find(c => c.id === id);
        if (chat) {
            const newTitle = prompt('Enter new chat title:', chat.title);
            if (newTitle) {
                chat.title = newTitle;
                saveChats();
            }
        }
    }

    function renderHistory() {
        historyList.innerHTML = '';
        chats.forEach(chat => {
            const item = document.createElement('div');
            item.classList.add('history-item');
            if (chat.id === currentChatId) item.classList.add('active');

            const isUrduTitle = isUrduText(chat.title);
            item.innerHTML = `

                <span class="title ${isUrduTitle ? 'font-urdu-ui' : ''}" ${isUrduTitle ? 'lang="ur"' : ''}>${escapeHtml(chat.title)}</span>
                <div class="history-actions">
                    <button class="action-btn edit-btn"><i class="fas fa-edit"></i></button>
                    <button class="action-btn delete-btn"><i class="fas fa-trash"></i></button>
                </div>
            `;

            item.addEventListener('click', () => loadChat(chat.id));
            item.querySelector('.edit-btn').addEventListener('click', (e) => renameChat(chat.id, e));
            item.querySelector('.delete-btn').addEventListener('click', (e) => deleteChat(chat.id, e));

            historyList.appendChild(item);
        });
    }

    newChatBtn.addEventListener('click', createNewChat);


    // ════════════════════════════════════════════════════════════
    // SEND MESSAGE & API CALL
    // ════════════════════════════════════════════════════════════

    async function sendMessage() {
        const text = userInput.value.trim();
        if (!text) return;

        // Stop any ongoing speech when user sends a new message
        stopSpeech();

        const chat = chats.find(c => c.id === currentChatId);
        if (!chat || pendingChats.has(chat.id)) return;
        pendingChats.add(chat.id);
        sendBtn.disabled = true;
        chatIntro.hidden = true;

        // The most recent bot answer — sent along so a follow-up like
        // "explain in urdu" can re-express it instead of starting a new topic.
        const lastBot = [...chat.messages].reverse().find(m => m.sender === 'bot');
        const prevAnswer = lastBot ? lastBot.text : '';
        const prevReceipt = lastBot?.meta?.answer_receipt || '';

        chat.messages.push({ sender: 'user', text: text });

        // Move this chat to the top of the recent list
        chats = chats.filter(c => c.id !== chat.id);
        chats.unshift(chat);

        saveChats();
        appendMessageUI('user', text, true);
        userInput.value = '';
        resizeComposer();

        // Honest pending state; the UI does not invent provider/retrieval stages.
        const loadingDiv = document.createElement('div');
        loadingDiv.classList.add('message', 'bot-message', 'loading-msg');
        loadingDiv.innerHTML = `<div class="message-content" role="status" aria-live="polite"><span class="pending-orbit" aria-hidden="true"></span><span>Preparing your answer<span class="typing-dots" aria-hidden="true"><span></span><span></span><span></span></span></span></div>`;
        chatContainer.insertBefore(loadingDiv, chatIntro);
        requestAnimationFrame(() => {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        });

        try {
            // New questions compare all schools, including in older selected-school chats.
            const result = await askBackend(text, 'General', prevAnswer, prevReceipt);
            loadingDiv.remove();
            if (!chats.some(c => c.id === chat.id)) return; // Deleted while awaiting the response.

            if (!result || result.ok === false) {
                const errMsg = (result && result.error) ? result.error : 'something went wrong.';
                if (currentChatId === chat.id) appendMessageUI('bot', 'Sorry, ' + errMsg, false);
                return;
            }

            const answer = result.answer || '';
            const meta = {
                mode: result.mode,
                response_schema: result.response_schema,
                answer_sections: result.answer_sections,
                citation_validation: result.citation_validation,
                scholarly_review: result.scholarly_review,
                sources: result.sources,
                answer_receipt: result.answer_receipt,
                out_of_scope: result.out_of_scope
            };

            chat.messages.push({ sender: 'bot', text: answer, meta: meta });
            saveChats();
            if (currentChatId === chat.id) appendMessageUI('bot', answer, true, meta);

            // Auto-rename chat from first question
            if (chat.title === 'New Chat' && chat.messages.length <= 3) {
                chat.title = text.substring(0, 25) + (text.length > 25 ? '...' : '');
                saveChats();
            }

        } catch (error) {
            loadingDiv.remove();
            const message = error instanceof TypeError
                ? 'Sorry, I could not reach FIQHBOT. Open start_fiqhbot.cmd from the FIQHBOT folder, ' +
                  'then use the page it opens.'
                : error.status === 503
                    ? 'Sorry, FIQHBOT could not connect to Gemini. Check your internet connection and try again.'
                : error.status
                    ? `Sorry, the server returned an error (${error.status}). Please try again.`
                    : 'Sorry, something went wrong while reading the server response. Please try again.';
            if (currentChatId === chat.id) appendMessageUI('bot', message, false);
            console.error(error);
        } finally {
            pendingChats.delete(chat.id);
            sendBtn.disabled = pendingChats.has(currentChatId);
        }
    }


    // ════════════════════════════════════════════════════════════
    // RENDER MESSAGES (with TTS speak button on bot messages)
    // ════════════════════════════════════════════════════════════

    function buildSourcesAccordion(sources) {
        const container = document.createElement('div');
        container.classList.add('sources-accordion');
        sourceEntries(sources).forEach(entry => {
            const record = entry.record;
            let row;
            if (entry.kind === 'fiqh') {
                row = document.createElement('div');
                row.className = 'src-static-line';
                row.tabIndex = -1;
                row.innerHTML = `<strong>Topic:</strong> ${escapeHtml(record.topic_name || record.topic_id)}`;
            } else {
                row = buildClickableLine(entry.label, entry.kind, record);
            }
            row.setAttribute('data-source-key', entry.key);
            container.appendChild(row);
        });

        return container;
    }

    function buildClickableLine(label, type, data) {
        const wrapper = document.createElement('details');
        wrapper.className = 'src-clickable-row';

        const header = document.createElement('summary');
        header.className = 'src-row-header';

        const text = document.createElement('span');
        text.className = 'src-row-text';
        text.textContent = label;

        const chevron = document.createElement('i');
        chevron.className = 'fas fa-chevron-down src-row-chevron';

        header.appendChild(text);
        header.appendChild(chevron);

        const panel = document.createElement('div');
        panel.className = 'src-row-panel';

        wrapper.addEventListener('toggle', () => {
            if (wrapper.open && !panel.hasChildNodes()) {
                panel.appendChild(buildTrilingualContent(data, type));
            }
        });

        wrapper.appendChild(header);
        wrapper.appendChild(panel);
        return wrapper;
    }


    function buildTrilingualContent(item, type) {
        const div = document.createElement('div');
        div.className = 'source-content';

        if (type === 'quran') {
            if (item.arabic) {
                const block = document.createElement('div');
                block.className = 'src-lang-block';
                block.dir = 'rtl';
                block.innerHTML = `<span class="src-lang-label">ARABIC</span><p class="src-lang-text src-lang-arabic">${escapeHtml(item.arabic)}</p>`;
                div.appendChild(block);
            }
            if (item.english) {
                const block = document.createElement('div');
                block.className = 'src-lang-block';
                block.dir = 'ltr';
                block.innerHTML = `<span class="src-lang-label">ENGLISH</span><p class="src-lang-text src-lang-english">${escapeHtml(item.english)}</p>`;
                div.appendChild(block);
            }
            if (item.urdu) {
                const block = document.createElement('div');
                block.className = 'src-lang-block';
                block.dir = 'rtl';
                block.innerHTML = `<span class="src-lang-label">URDU</span><p class="src-lang-text src-lang-urdu">${escapeHtml(item.urdu)}</p>`;
                div.appendChild(block);
            }
        } else if (type === 'hadith') {
            if (item.text_ar && item.text_ar.trim()) {
                const block = document.createElement('div');
                block.className = 'src-lang-block';
                block.dir = 'rtl';
                block.innerHTML = `<span class="src-lang-label">ARABIC</span><p class="src-lang-text src-lang-arabic">${escapeHtml(item.text_ar)}</p>`;
                div.appendChild(block);
            }
            if (item.text_en && item.text_en.trim()) {
                const block = document.createElement('div');
                block.className = 'src-lang-block';
                block.dir = 'ltr';
                block.innerHTML = `<span class="src-lang-label">ENGLISH</span><p class="src-lang-text src-lang-english">${escapeHtml(item.text_en)}</p>`;
                div.appendChild(block);
            }
        }

        return div;
    }

    function buildMetaBadges(meta) {
        // Old saved percentages/flags are intentionally ignored. A reference
        // membership check cannot certify answer accuracy or scholarly approval.
        if (!meta || !['fiqh', 'general', 'reexpress', 'fiqh_comparison'].includes(meta.mode) || meta.out_of_scope) return '';
        const validation = meta.citation_validation || {};
        if (validation.status !== 'passed' || validation.scope !== 'provided_reference_membership') return '';
        let html = '<div class="msg-meta"><span class="evidence-badge">References matched</span>';
        const review = meta.scholarly_review || {};
        if (review.status === 'not_completed' && review.scope === 'answer_and_ruling_support') {
            html += '<span class="evidence-badge">Scholarly review not completed</span>';
        }
        html += '<small class="evidence-note">Matching supplied references does not verify the answer\'s accuracy.</small></div>';
        return html;
    }

    function sourceEntries(sources) {
        const entries = [];
        if (!sources || typeof sources !== 'object') return entries;
        for (const kind of ['fiqh', 'quran', 'hadith']) {
            if (!Array.isArray(sources[kind])) continue;
            sources[kind].forEach((record, index) => {
                if (!record || typeof record !== 'object') return;
                let tag, label;
                if (kind === 'fiqh' && typeof record.topic_name === 'string' && record.topic_name.trim()) {
                    tag = `[${record.topic_name}]`; label = 'Fiqh note';
                } else if (kind === 'quran' && typeof record.ref === 'string' && record.ref.trim()) {
                    tag = `[Quran ${record.ref}]`; label = `Qur’an ${record.ref}`;
                } else if (kind === 'hadith' && typeof record.ref === 'string' && record.ref.trim()) {
                    if (![record.text_ar, record.text_en].some(value => typeof value === 'string' && value.trim())) return;
                    tag = `[${record.ref.replace(/&#39;|&apos;/g, "'")}]`; label = record.ref.replace(/&#39;|&apos;/g, "'");
                } else return;
                entries.push({ kind, key: `${kind}-${index}`, tag, label, record });
            });
        }
        return entries;
    }

    function formatAnswerInline(text, sources, school, depth = 0) {
        const records = sourceEntries(sources);
        const normalize = value => value.toLowerCase().replace(/\s+/g, ' ').trim();
        const tokens = /\[[^\[\]\n]{1,256}\]|\*\*[^*\n]+\*\*|`[^`\n]+`/g;
        let html = '', cursor = 0;
        for (const match of String(text).matchAll(tokens)) {
            html += escapeHtml(text.slice(cursor, match.index));
            const token = match[0];
            if (token.startsWith('**') && depth < 3) {
                html += '<strong>' + formatAnswerInline(token.slice(2, -2), sources, school, depth + 1) + '</strong>';
            } else if (token.startsWith('`')) {
                html += '<code>' + escapeHtml(token.slice(1, -1)) + '</code>';
            } else {
                const entry = records.find(record => normalize(record.tag) === normalize(token));
                if (entry && ['hanafi', 'shafi', 'maliki'].includes(school)) {
                    html += `<button type="button" class="inline-citation" dir="ltr" data-citation-school="${school}" data-citation-key="${entry.key}" aria-haspopup="dialog" aria-label="${escapeHtml('View ' + entry.label + ' source for ' + school)}" title="${escapeHtml(token.slice(1, -1))}">${escapeHtml(entry.label)}<span aria-hidden="true">↗</span></button>`;
                } else html += escapeHtml(token);
            }
            cursor = match.index + token.length;
        }
        return html + escapeHtml(text.slice(cursor));
    }

    function formatAnswerContent(text, sources, school) {
        // A deliberately small Markdown subset. Never evaluate model HTML or links.
        const lines = String(text).replace(/\r\n/g, '\n').split('\n');
        const attrs = value => `${isUrduText(value) ? ' class="font-urdu"' : ''} dir="auto"`;
        const inline = value => formatAnswerInline(value, sources, school);
        let html = '', i = 0;
        while (i < lines.length) {
            if (!lines[i].trim()) { i++; continue; }
            const heading = lines[i].match(/^#{1,6}\s+(.+)$/);
            if (heading) { html += `<h4${attrs(heading[1])}>${inline(heading[1])}</h4>`; i++; continue; }
            const bullet = lines[i].match(/^\s*[-*]\s+(.+)$/);
            const numbered = lines[i].match(/^\s*(\d{1,4})[.)]\s+(.+)$/);
            if (bullet || numbered) {
                const ordered = Boolean(numbered);
                const pattern = ordered ? /^\s*(\d{1,4})[.)]\s+(.+)$/ : /^\s*[-*]\s+(.+)$/;
                html += ordered ? `<ol start="${Number(numbered[1])}">` : '<ul>';
                while (i < lines.length) {
                    const item = lines[i].match(pattern);
                    if (!item) break;
                    const content = item[ordered ? 2 : 1];
                    html += `<li${attrs(content)}>${inline(content)}</li>`; i++;
                }
                html += ordered ? '</ol>' : '</ul>';
                continue;
            }
            const paragraph = [];
            while (i < lines.length && lines[i].trim()) {
                if (paragraph.length && /^(?:#{1,6}\s|\s*[-*]\s|\s*\d{1,4}[.)]\s)/.test(lines[i])) break;
                paragraph.push(lines[i++]);
            }
            const value = paragraph.join('\n');
            html += `<p${attrs(value)}>${inline(value).replace(/\n/g, '<br>')}</p>`;
        }
        return html;
    }

    function bindResponseSources(root) {
        const dialog = root.querySelector('.response-source-dialog');
        if (!dialog) return;
        const close = root.querySelector('.source-close-btn');
        const viewport = root.closest?.('.chat-container');
        let opener = null;
        let previousScroll = null;
        const restoreFocus = () => {
            if (opener?.isConnected) opener.focus({ preventScroll: true });
            if (viewport && Number.isFinite(previousScroll)) viewport.scrollTop = previousScroll;
        };
        const closeSources = () => {
            if (typeof dialog.close === 'function') dialog.close();
            else { dialog.removeAttribute('open'); restoreFocus(); }
        };
        root.querySelectorAll('[data-open-sources], .inline-citation').forEach(button => {
            button.addEventListener('click', event => {
                opener = event.currentTarget;
                if (!dialog.open) {
                    previousScroll = viewport?.scrollTop;
                    if (typeof dialog.showModal === 'function') dialog.showModal();
                    else { dialog.classList.add('dialog-inline-fallback'); dialog.setAttribute('open', ''); }
                }
                const school = opener.dataset.citationSchool;
                const key = opener.dataset.citationKey;
                if (!/^(hanafi|shafi|maliki)$/.test(school || '') || !/^(fiqh|quran|hadith)-\d+$/.test(key || '')) return;
                const group = dialog.querySelector(`[data-source-group="${school}"]`);
                const record = group?.querySelector(`[data-source-key="${key}"]`);
                if (!record) return;
                if (record.tagName === 'DETAILS') record.open = true;
                requestAnimationFrame(() => {
                    const target = record.querySelector('summary') || record;
                    target.focus({ preventScroll: true });
                    record.scrollIntoView({ block: 'nearest', behavior: 'auto' });
                });
            });
        });
        close.addEventListener('click', closeSources);
        dialog.addEventListener('close', restoreFocus);
        dialog.addEventListener('keydown', event => {
            if (event.key === 'Escape' && typeof dialog.showModal !== 'function') closeSources();
        });
        dialog.addEventListener('click', event => {
            if (event.target !== dialog) return;
            const rect = dialog.getBoundingClientRect();
            if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeSources();
        });
    }

    function buildSchoolSections(sections) {
        const schools = [['hanafi', 'Hanafi'], ['shafi', 'Shafi‘i'], ['maliki', 'Maliki']];
        const statuses = { available: 'Answer', unavailable: 'Not available', withheld: 'Withheld' };
        if (!Array.isArray(sections) || sections.length !== schools.length || sections.some((s, i) =>
            !s || s.school !== schools[i][0] || !Object.hasOwn(statuses, s.status) || typeof s.answer !== 'string')) return '';
        return '<section class="school-responses" aria-label="School responses">' + sections.map((section, i) => {
            const available = section.status === 'available';
            const body = formatAnswerContent(section.answer, available ? section.sources : {}, section.school);
            return `<div class="school-answer" data-state="${section.status}">
                <div class="school-answer-heading"><h3 class="school-answer-title">${schools[i][1]}</h3>
                    ${available ? '' : `<span class="school-answer-state">${statuses[section.status]}</span>`}</div>
                <div class="school-answer-body">${body}</div></div>`;
        }).join('') + '</section>';
    }

    function buildSchoolSources(sections) {
        if (!buildSchoolSections(sections)) return '';
        const titles = { hanafi: 'Hanafi', shafi: 'Shafi‘i', maliki: 'Maliki' };
        return sections.filter(section => section.status === 'available' && ['fiqh', 'quran', 'hadith']
            .some(kind => Array.isArray(section.sources?.[kind]) && section.sources[kind].some(item => item && typeof item === 'object')))
            .map(section => `<section class="school-source-group" data-source-group="${section.school}" aria-label="${titles[section.school]} references">
                <h4>${titles[section.school]}</h4><div data-school-sources="${section.school}"></div></section>`).join('');
    }

    function responseActionContent(icon, label) {
        // Small, consistent outline icons; the label remains visible on mobile.
        const paths = {
            listen: '<path d="m11 5-6 4H2v6h3l6 4V5Z"/><path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>',
            copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V4a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v11a1 1 0 0 0 1 1h4"/>',
            sources: '<path d="M12 6c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1Z"/><path d="M12 6v15"/>',
            chevron: '<path d="m6 9 6 6 6-6"/>',
            stop: '<rect x="5" y="5" width="14" height="14" rx="2"/>',
            loading: '<path d="M20 12a8 8 0 1 1-8-8"/>',
            check: '<path d="m5 12 4 4L19 6"/>',
            error: '<path d="m6 6 12 12M6 18 18 6"/>',
            close: '<path d="m6 6 12 12M6 18 18 6"/>',
            spark: '<path d="m12 3 2.7 6.3L21 12l-6.3 2.7L12 21l-2.7-6.3L3 12l6.3-2.7L12 3Z"/>',
        };
        return `<svg class="response-icon${icon === 'loading' ? ' response-icon-loading' : ''}" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${paths[icon] || paths.sources}</svg>${label ? `<span>${escapeHtml(label)}</span>` : ''}`;
    }

    function appendMessageUI(sender, text, animate, meta) {
        const distanceFromBottom = chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight;
        const followReply = !Number.isFinite(distanceFromBottom) || distanceFromBottom < 160 || sender === 'user';
        const msgDiv = document.createElement('div');
        msgDiv.classList.add('message', sender === 'user' ? 'user-message' : 'bot-message');
        if (animate && sender === 'bot') msgDiv.classList.add('response-enter');

        const contentDiv = document.createElement('div');
        contentDiv.classList.add('message-content');

        let formattedText = escapeHtml(text).replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        // Make any URL clickable (opens in a new tab). Covers the IslamQA
        // referral link shown on low-confidence answers.
        formattedText = formattedText.replace(
            /(https?:\/\/[^\s<]+)/g,
            '<a href="$1" target="_blank" rel="noopener">$1</a>'
        );
        formattedText = formattedText.replace(/\n/g, '<br>');

        // Show the Sources button only for real answers that actually carry
        // citations. Referral / greeting / capability / low-confidence replies
        // ("ask a scholar", IslamQA link, etc.) have no sources, so hide it.
        const noSourceModes = ['greeting', 'capability', 'low_confidence'];
        const s = (meta && meta.sources) || {};
        const realSourceCount =
            (Array.isArray(s.fiqh) ? s.fiqh.filter(Boolean).length : 0) +
            (Array.isArray(s.quran) ? s.quran.filter(Boolean).length : 0) +
            (Array.isArray(s.hadith) ? s.hadith.filter(Boolean).length : 0);
        const schoolHtml = sender === 'bot' && meta?.response_schema === 'school_comparison_v1'
            ? buildSchoolSections(meta.answer_sections) : '';
        if (schoolHtml) msgDiv.classList.add('comparison-message');
        if (!schoolHtml && isUrduText(text)) {
            contentDiv.classList.add('font-urdu');
            contentDiv.setAttribute('lang', 'ur');
        }
        const hasSources = !schoolHtml && sender === 'bot'
            && !noSourceModes.includes(meta && meta.mode)
            && realSourceCount > 0;
        const metaBadges = buildMetaBadges(meta);
        const speakButton = sender === 'bot'
            ? `<button type="button" class="speak-btn" title="Read aloud" aria-label="Read answer aloud" aria-pressed="false">${responseActionContent('listen', 'Listen')}</button>`
            : '';
        const copyButton = sender === 'bot'
            ? `<button type="button" class="copy-btn" title="Copy answer" aria-label="Copy answer">${responseActionContent('copy', 'Copy')}</button>`
            : '';
        const sourcesButton = hasSources
            ? `<button class="sources-btn" title="View sources"><i class="fas fa-book-open"></i> Sources</button>`
            : '';

        const schoolSources = schoolHtml ? buildSchoolSources(meta.answer_sections) : '';
        const responseHeader = `<header class="response-header"><span class="response-avatar" aria-hidden="true">${responseActionContent('spark', '')}</span><strong>Fiqhbot</strong></header>`;
        contentDiv.innerHTML = schoolHtml
            ? `${responseHeader}
                ${schoolHtml}<div class="response-actions" role="group" aria-label="Answer actions">${copyButton}${speakButton}
                ${schoolSources ? `<button type="button" class="response-sources-btn" data-open-sources aria-haspopup="dialog" title="View answer sources">${responseActionContent('sources', 'Sources')}</button>` : ''}
                <span class="response-action-status" role="status" aria-live="polite"></span></div>${metaBadges}
                ${schoolSources ? `<dialog class="response-source-dialog" aria-label="Answer sources">
                    <div class="source-inspector-header"><div><p class="source-inspector-eyebrow">Provided references</p><h2>Sources</h2></div><button type="button" class="source-close-btn" aria-label="Close sources" title="Close sources">${responseActionContent('close', '')}</button></div>
                    <div class="response-sources-body"><p class="school-reference-note">References mapped to this topic; school-specific support has not been independently reviewed.</p>${schoolSources}</div></dialog>` : ''}`
            : sender === 'bot'
                ? `${responseHeader}<div class="response-prose"><p>${formattedText}</p></div><div class="response-actions" role="group" aria-label="Answer actions">${copyButton}${speakButton}${sourcesButton}<span class="response-action-status" role="status" aria-live="polite"></span></div>${metaBadges}`
                : `<p>${formattedText}</p>`;
        if (schoolHtml) {
            meta.answer_sections.forEach(section => {
                if (section.status !== 'available') return;
                const holder = contentDiv.querySelector(`[data-school-sources="${section.school}"]`);
                if (holder) holder.appendChild(buildSourcesAccordion(section.sources || {}));
            });
            bindResponseSources(contentDiv);
        }

        if (hasSources) {
            const sourcesDiv = document.createElement('div');
            sourcesDiv.classList.add('sources-dropdown');
            sourcesDiv.style.display = 'none';
            contentDiv.appendChild(sourcesDiv);

            const srcBtn = contentDiv.querySelector('.sources-btn');
            let accordionBuilt = false;
            srcBtn.addEventListener('click', () => {
                const isOpen = sourcesDiv.style.display !== 'none';
                sourcesDiv.style.display = isOpen ? 'none' : 'block';
                srcBtn.classList.toggle('active', !isOpen);
                if (!isOpen && !accordionBuilt) {
                    const accordion = buildSourcesAccordion(meta.sources);
                    sourcesDiv.appendChild(accordion);
                    accordionBuilt = true;
                }
            });
        }

        if (sender === 'bot') {
            const speakBtn = contentDiv.querySelector('.speak-btn');
            let isSpeaking = false;

            const resetIcon = () => {
                speakBtn.innerHTML = responseActionContent('listen', 'Listen');
                speakBtn.setAttribute('aria-label', 'Read answer aloud');
                speakBtn.setAttribute('aria-pressed', 'false');
                speakBtn.title = 'Read answer aloud';
                isSpeaking = false;
            };

            speakBtn.addEventListener('click', () => {
                if (isSpeaking) {
                    stopSpeech();
                    resetIcon();
                } else {
                    stopSpeech();
                    speakBtn.innerHTML = responseActionContent('loading', 'Loading');
                    speakBtn.setAttribute('aria-label', 'Stop reading');
                    speakBtn.setAttribute('aria-pressed', 'true');
                    speakBtn.title = 'Stop reading';
                    isSpeaking = true;
                    speakText(text, resetIcon).then(() => {
                        if (isSpeaking) speakBtn.innerHTML = responseActionContent('stop', 'Stop');
                    });
                }
            });

            const copyBtn = contentDiv.querySelector('.copy-btn');
            const copyStatus = contentDiv.querySelector('.response-action-status');
            copyBtn.addEventListener('click', async () => {
                try {
                    await navigator.clipboard.writeText(text);
                    copyBtn.classList.add('copied');
                    copyBtn.innerHTML = responseActionContent('check', 'Copied');
                    copyBtn.setAttribute('aria-label', 'Answer copied');
                    if (copyStatus) copyStatus.textContent = 'Answer copied';
                    setTimeout(() => {
                        copyBtn.classList.remove('copied');
                        copyBtn.innerHTML = responseActionContent('copy', 'Copy');
                        copyBtn.setAttribute('aria-label', 'Copy answer');
                        if (copyStatus) copyStatus.textContent = '';
                    }, 2000);
                } catch {
                    copyBtn.innerHTML = responseActionContent('error', 'Failed');
                    if (copyStatus) copyStatus.textContent = 'Copy failed. Please select and copy the text.';
                    setTimeout(() => {
                        copyBtn.innerHTML = responseActionContent('copy', 'Copy');
                        if (copyStatus) copyStatus.textContent = '';
                    }, 1500);
                }
            });
        }

        msgDiv.appendChild(contentDiv);

        if (chatIntro.parentNode === chatContainer) {
            chatContainer.insertBefore(msgDiv, chatIntro);
        } else {
            chatContainer.appendChild(msgDiv);
        }

        requestAnimationFrame(() => {
            if (animate && sender === 'bot' && followReply && typeof msgDiv.scrollIntoView === 'function') {
                msgDiv.scrollIntoView({ block: 'start', behavior: 'auto' });
            } else if (followReply || !animate) chatContainer.scrollTop = chatContainer.scrollHeight;
        });
    }


    // ════════════════════════════════════════════════════════════
    // BACKEND CALL  (RAG pipeline + grounded Gemini, via Flask /ask)
    // ════════════════════════════════════════════════════════════

    async function askBackend(question, madhab, prevAnswer, prevReceipt) {
        const response = await fetch(`${BACKEND_URL}/ask`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: question,
                madhab: madhab || 'General',
                prev_answer: prevAnswer || '',
                prev_answer_receipt: prevReceipt || ''
            })
        });
        if (!response.ok) {
            let detail = response.status;
            try { const j = await response.json(); detail = j.error || detail; } catch (e) { }
            const error = new Error('Backend error: ' + detail);
            error.status = response.status;
            throw error;
        }
        return await response.json();
    }



    // ── Event Listeners ──────────────────────────────────────────
    function resizeComposer() {
        if (!userInput.style) return;
        userInput.style.height = 'auto';
        if (userInput.value) userInput.style.height = userInput.scrollHeight + 'px';
    }

    function handleComposerKeydown(event) {
        if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) return;
        if (window.matchMedia('(pointer: coarse)').matches) return;
        event.preventDefault();
        sendMessage();
    }

    sendBtn.addEventListener('click', sendMessage);
    userInput.addEventListener('keydown', handleComposerKeydown);
    userInput.addEventListener('input', () => {
        resizeComposer();
        if (isUrduText(userInput.value)) {
            userInput.classList.add('font-urdu-ui');
            userInput.setAttribute('lang', 'ur');
        } else {
            userInput.classList.remove('font-urdu-ui');
            userInput.removeAttribute('lang');
        }
    });

    // ── Show enter button after minimum 2.8s ────────────────────
    showEnterBtn();
});
