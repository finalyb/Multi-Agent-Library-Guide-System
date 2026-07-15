/**
 * 对话模块
 * 管理聊天界面的渲染、消息发送、SSE 流式展示
 */

let isProcessing = false;
let currentAssistantBubble = null;

/**
 * 发送消息（主入口）
 */
async function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();

    if (!message || isProcessing) return;

    // 清空输入
    input.value = '';
    input.focus();

    // 隐藏快捷操作
    hideQuickActions();

    // 渲染用户消息
    renderUserMessage(message);

    // 渲染AI占位气泡
    const bubble = renderAssistantPlaceholder();
    currentAssistantBubble = bubble;

    // 发送请求
    isProcessing = true;

    try {
        // 使用流式请求获得打字效果
        await apiChatStream(
            message,
            getSessionId(),
            // onToken
            (token) => {
                appendTokenToBubble(bubble, token);
                scrollToBottom();
            },
            // onDone
            () => {
                finalizeAssistantBubble(bubble);
                isProcessing = false;
                scrollToBottom();
            },
            // onError
            (error) => {
                console.error('Chat error:', error);
                bubble.querySelector('.bubble-text').innerHTML =
                    '<p>抱歉，我暂时无法回答，请稍后再试 😥</p>';
                isProcessing = false;
            }
        );
    } catch (error) {
        console.error('Chat error:', error);
        bubble.querySelector('.bubble-text').innerHTML =
            '<p>抱歉，网络出问题了，请检查连接后重试。</p>';
        isProcessing = false;
    }
}

/**
 * 快捷提问
 */
function sendQuick(message) {
    document.getElementById('messageInput').value = message;
    sendMessage();
}

/**
 * 键盘事件处理
 */
function handleKeyPress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

/**
 * 渲染用户消息气泡
 */
function renderUserMessage(message) {
    const container = document.getElementById('chatContainer');
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble user';
    bubble.innerHTML = `
        <div class="bubble-content">
            <div class="bubble-text"><p>${escapeHtml(message)}</p></div>
        </div>
    `;
    container.appendChild(bubble);
    scrollToBottom();
}

/**
 * 渲染AI占位气泡（打字动画）
 */
function renderAssistantPlaceholder() {
    const container = document.getElementById('chatContainer');
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble assistant';
    bubble.innerHTML = `
        <div class="bubble-avatar"><img src="jixiaotu.png" class="bot-avatar" alt="吉小图"></div>
        <div class="bubble-content">
            <div class="bubble-text">
                <div class="typing-indicator">
                    <span></span><span></span><span></span>
                </div>
            </div>
        </div>
    `;
    container.appendChild(bubble);
    return bubble;
}

/**
 * 向气泡追加token文本
 */
function appendTokenToBubble(bubble, token) {
    const textDiv = bubble.querySelector('.bubble-text');

    // 移除打字动画占位符
    const indicator = textDiv.querySelector('.typing-indicator');
    if (indicator) indicator.remove();

    // 追加文本（保持换行）
    const formatted = token
        .replace(/\n/g, '<br>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // 使用累积方式避免innerHTML导致的光标问题
    const currentHtml = textDiv.innerHTML;
    textDiv.innerHTML = currentHtml + formatted;
}

/**
 * 完成AI气泡渲染（移除占位符、添加来源标注）
 */
function finalizeAssistantBubble(bubble) {
    // 确保没有残留的typing indicator
    const indicator = bubble.querySelector('.typing-indicator');
    if (indicator) indicator.remove();

    // 如果内容为空，显示默认消息
    const textDiv = bubble.querySelector('.bubble-text');
    if (!textDiv.innerHTML.trim() || textDiv.innerHTML.includes('typing-indicator')) {
        textDiv.innerHTML = '<p>收到你的问题了，让我想想...</p>';
    }
}

/**
 * 显示快捷操作按钮
 */
function showQuickActions() {
    const actions = document.getElementById('quickActions');
    if (actions) {
        actions.style.display = 'flex';
    }
}

/**
 * 隐藏快捷操作按钮
 */
function hideQuickActions() {
    const actions = document.getElementById('quickActions');
    if (actions) {
        actions.style.display = 'none';
    }
}

/**
 * 滚动到聊天底部
 */
function scrollToBottom() {
    const container = document.getElementById('chatContainer');
    requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight;
    });
}

/**
 * HTML转义
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
