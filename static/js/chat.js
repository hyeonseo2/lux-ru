/* LUX-RU — AI Chat with SSE */

let isStreaming = false;

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function sendSuggestion(btn) {
  const text = btn.textContent.trim();
  document.getElementById('chat-input').value = text;
  sendChat();
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const message = input.value.trim();
  if (!message || isStreaming) return;

  input.value = '';
  isStreaming = true;
  document.getElementById('chat-send-btn').disabled = true;

  const messagesEl = document.getElementById('chat-messages');

  // Add user message
  const userMsg = document.createElement('div');
  userMsg.className = 'chat-msg user';
  userMsg.textContent = message;
  messagesEl.appendChild(userMsg);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  // Create assistant message container
  const assistantMsg = document.createElement('div');
  assistantMsg.className = 'chat-msg assistant';
  assistantMsg.innerHTML = '<span class="spinner"></span>';
  messagesEl.appendChild(assistantMsg);

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: SESSION_ID,
        message: message,
      }),
    });

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let fullText = '';
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const jsonStr = line.slice(6).trim();
        if (!jsonStr) continue;

        try {
          const event = JSON.parse(jsonStr);

          if (event.type === 'progress') {
            // Show progress step
            const progressEl = document.createElement('div');
            progressEl.className = 'chat-msg progress';
            progressEl.innerHTML = `<span class="spinner" style="width:14px;height:14px;border-width:2px;margin-right:8px;"></span> ${event.message}`;
            messagesEl.insertBefore(progressEl, assistantMsg);
            messagesEl.scrollTop = messagesEl.scrollHeight;

            // Fade out progress after a moment
            setTimeout(() => {
              progressEl.style.opacity = '0.4';
              progressEl.style.transform = 'scale(0.95)';
              progressEl.style.transition = 'all 0.3s ease';
            }, 1500);
          }

          if (event.type === 'content') {
            fullText += event.text;
            assistantMsg.innerHTML = formatMarkdown(fullText);
            messagesEl.scrollTop = messagesEl.scrollHeight;
          }

          if (event.type === 'done') {
            // Remove progress messages
            messagesEl.querySelectorAll('.chat-msg.progress').forEach(el => el.remove());
          }
        } catch (e) {
          // Skip malformed JSON
        }
      }
    }

    if (!fullText) {
      assistantMsg.innerHTML = '응답을 받지 못했습니다. 다시 시도해주세요.';
    }

  } catch (err) {
    assistantMsg.innerHTML = `⚠️ 오류가 발생했습니다: ${err.message}`;
  } finally {
    isStreaming = false;
    document.getElementById('chat-send-btn').disabled = false;
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
}

function formatMarkdown(text) {
  const safe = escapeHtml(text);

  // Simple markdown-like formatting
  return safe
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code style="background:rgba(99,102,241,0.15);padding:2px 6px;border-radius:4px;font-family:var(--font-mono);font-size:0.85em;">$1</code>')
    .replace(/\n---\n/g, '<hr style="border:none;border-top:1px solid var(--border-subtle);margin:0.75rem 0;">')
    .replace(/^### (.*)/gm, '<h4 style="margin:0.5rem 0;font-size:1rem;">$1</h4>')
    .replace(/^## (.*)/gm, '<h3 style="margin:0.75rem 0;font-size:1.1rem;">$1</h3>')
    .replace(/^- (.*)/gm, '<div style="padding-left:1rem;position:relative;margin:2px 0;">• $1</div>')
    .replace(/^(\d+)\. (.*)/gm, '<div style="padding-left:1rem;margin:2px 0;">$1. $2</div>')
    .replace(/ℹ️(.*)/g, '<div style="color:var(--text-muted);font-size:0.85rem;margin-top:0.5rem;padding:8px 12px;background:rgba(99,102,241,0.06);border-radius:8px;border:1px solid var(--border-accent);">ℹ️$1</div>')
    .replace(/\n\n/g, '<br><br>')
    .replace(/\n/g, '<br>');
}
