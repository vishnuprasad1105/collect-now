document.addEventListener('DOMContentLoaded', function() {
  const chatbotIcon = document.getElementById('chatbotIcon');
  const chatContainer = document.getElementById('chatContainer');
  const closeChatButton = document.getElementById('closeChat');
  const toggleExpandBtn = document.getElementById('toggleExpandBtn');
  const chatOverlay = document.getElementById('chatOverlay');
  const chatForm = document.getElementById('chat-form') || document.querySelector('.chat-input');
  const messageInput = document.getElementById('messageInput') || document.getElementById('chat-input');
  const messagesContainer = document.getElementById('messages');
  const sendButton = document.getElementById('sendButton');

  let isExpanded = false;

  // --- Core UI Listeners ---
  if (chatbotIcon) {
      chatbotIcon.addEventListener('click', () => {
          chatContainer.classList.toggle('open');
          chatbotIcon.classList.toggle('active');
      });
  }

  if (closeChatButton) {
      closeChatButton.addEventListener('click', () => {
          chatContainer.classList.remove('open');
          chatbotIcon.classList.remove('active');
          if (isExpanded) {
              collapseChat();
          }
      });
  }
  
  if (toggleExpandBtn) {
      toggleExpandBtn.addEventListener('click', () => {
          if (isExpanded) {
              collapseChat();
          } else {
              expandChat();
          }
      });
  }

  if (chatOverlay) {
      chatOverlay.addEventListener('click', () => {
          if (isExpanded) {
              collapseChat();
          }
      });
  }

  // --- Chat Functionality ---
  if (chatForm) {
      chatForm.addEventListener('submit', function(e) {
          e.preventDefault();
          sendMessage();
      });
  }
  
  if(sendButton) {
      sendButton.addEventListener('click', function(e){
          e.preventDefault();
          sendMessage();
      });
  }

  if (messageInput) {
      messageInput.addEventListener('keydown', function(e) {
          if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              sendMessage();
          }
      });
  }

  async function sendMessage() {
      const question = messageInput.value.trim();
      if (question === '') return;

      addMessage(question, 'user');
      messageInput.value = '';
      messageInput.style.height = 'auto';
      showThinkingAnimation();

      try {
          const response = await fetch('/api/chat', {
              method: 'POST',
              headers: {
                  'Content-Type': 'application/json',
              },
              body: JSON.stringify({ question }),
          });

          if (!response.ok) {
              throw new Error('Network response was not ok');
          }

          const data = await response.json();
          removeThinkingAnimation();
          addMessage(data.answer, 'bot');
      } catch (error) {
          removeThinkingAnimation();
          addMessage('Sorry, I am having trouble connecting. Please try again later.', 'bot');
      }
  }

  function addMessage(text, sender) {
      const messageRow = document.createElement('div');
      messageRow.classList.add('message-row', `${sender}-message-row`);

      const message = document.createElement('div');
      message.classList.add('message', `${sender}-message`);
      message.textContent = text;

      messageRow.appendChild(message);
      messagesContainer.appendChild(messageRow);
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  function showThinkingAnimation() {
      const thinkingRow = document.createElement('div');
      thinkingRow.classList.add('message-row', 'bot-message-row', 'thinking');
      
      const thinkingMessage = document.createElement('div');
      thinkingMessage.classList.add('message', 'bot-message');
      thinkingMessage.innerHTML = '<span>.</span><span>.</span><span>.</span>';
      
      thinkingRow.appendChild(thinkingMessage);
      messagesContainer.appendChild(thinkingRow);
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  function removeThinkingAnimation() {
      const thinkingRow = messagesContainer.querySelector('.thinking');
      if (thinkingRow) {
          thinkingRow.remove();
      }
  }

  // --- Helper Functions ---
  function expandChat() {
      isExpanded = true;
      chatContainer.classList.add('expanded');
      chatOverlay.classList.add('active');
  }

  function collapseChat() {
      isExpanded = false;
      chatContainer.classList.remove('expanded');
      chatOverlay.classList.remove('active');
  }
});