(() => {
  const chatIcon = document.getElementById('chatbot-icon');
  const chatOverlay = document.getElementById('chat-overlay');
  const chatContainer = document.getElementById('chat-container');
  const expandBtn = document.getElementById('chat-expand');
  const closeBtn = document.getElementById('chat-close');
  const chatForm = document.getElementById('chat-form');
  const chatInput = document.getElementById('chat-input');
  const messages = document.querySelector('.messages');

  if (!chatIcon || !chatOverlay || !chatContainer || !chatForm || !chatInput || !messages) {
    return;
  }

  let isExpanded = false;
  const GREETING_TEXT = "Hi, I'm your CollectNow assistant. How may I help you today?";

  const escapeHtml = (unsafe) =>
    unsafe
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');

  const toggleChat = (open) => {
    if (open) {
      chatContainer.classList.add('open');
      chatContainer.setAttribute('aria-expanded', 'true');
      chatIcon.classList.add('active');
      if (isExpanded) {
        chatOverlay.hidden = false;
        chatOverlay.classList.add('active');
      } else {
        chatOverlay.classList.remove('active');
        chatOverlay.hidden = true;
      }
      autoResize();
      ensureGreeting();
      chatInput.focus();
    } else {
      chatContainer.classList.remove('open', 'expanded');
      chatContainer.setAttribute('aria-expanded', 'false');
      chatIcon.classList.remove('active');
      chatOverlay.classList.remove('active');
      chatOverlay.hidden = true;
      isExpanded = false;
      updateExpandState();
    }
  };

  const updateExpandState = () => {
    if (isExpanded) {
      chatContainer.classList.add('expanded');
      chatOverlay.classList.add('active');
      chatOverlay.hidden = false;
      expandBtn.setAttribute('aria-label', 'Collapse assistant');
    } else {
      chatContainer.classList.remove('expanded');
      if (!chatContainer.classList.contains('open')) {
        chatOverlay.hidden = true;
      } else {
        chatOverlay.classList.remove('active');
        chatOverlay.hidden = true;
      }
      expandBtn.setAttribute('aria-label', 'Expand assistant');
    }
  };

  const appendMessage = (role, text, { thinking = false, type = null } = {}) => {
    const container = document.createElement('div');
    container.className = 'message-container';
    if (type) {
      container.dataset.type = type;
    }

    const row = document.createElement('div');
    row.className = `message-row ${role === 'user' ? 'user-message-row' : 'bot-message-row'}`;

    if (role === 'bot') {
      const avatar = document.createElement('div');
      avatar.className = 'message-avatar bot-avatar';
      avatar.textContent = '🤖';
      row.appendChild(avatar);
    }

    const safeText = escapeHtml(text);
    const bubble = document.createElement('div');
    bubble.className = `message ${role === 'user' ? 'user-message' : 'bot-message'}`;
    bubble.innerHTML = thinking ? `<span class="chatbot-thinking">${safeText}</span>` : safeText;

    row.appendChild(bubble);
    container.appendChild(row);

    messages.appendChild(container);
    messages.scrollTop = messages.scrollHeight;
    return container;
  };

  const setThinking = () => appendMessage('bot', 'Analyzing…', { thinking: true });

  const removeElement = (el) => {
    if (el && el.remove) {
      el.remove();
    }
  };

  const autoResize = () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = `${Math.min(chatInput.scrollHeight, 160)}px`;
  };

  const ensureGreeting = () => {
    if (!messages.querySelector('[data-type="greeting"]')) {
      appendMessage('bot', GREETING_TEXT, { type: 'greeting' });
    }
  };

  chatInput.addEventListener('input', autoResize);

  chatIcon.addEventListener('click', () => {
    const isOpen = chatContainer.classList.contains('open');
    toggleChat(!isOpen);
  });

  chatOverlay.addEventListener('click', () => {
    toggleChat(false);
  });

  closeBtn.addEventListener('click', () => {
    toggleChat(false);
  });

  expandBtn.addEventListener('click', () => {
    isExpanded = !isExpanded;
    updateExpandState();
  });

  chatForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const question = chatInput.value.trim();
    if (!question) {
      return;
    }

    appendMessage('user', question);
    chatInput.value = '';
    autoResize();

    const thinkingEl = setThinking();

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });

      const payload = await response.json();
      removeElement(thinkingEl);

      if (!response.ok) {
        appendMessage('bot', payload.error || 'Something went wrong.');
        return;
      }

      const answer = payload.answer || "I'm sorry, I don't have that answer yet.";
      appendMessage('bot', answer);
    } catch (error) {
      console.error(error);
      removeElement(thinkingEl);
      appendMessage('bot', 'Network error. Please try again.');
    }
  });
})();
