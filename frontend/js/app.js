/**
 * 应用主模块
 * 初始化、会话管理、全局状态
 */

// 会话ID（整个页面生命周期内保持不变）
let SESSION_ID = null;

/**
 * 获取或创建会话ID
 */
function getSessionId() {
    if (!SESSION_ID) {
        SESSION_ID = localStorage.getItem('library_guide_session') || generateSessionId();
    }
    return SESSION_ID;
}

/**
 * 生成新的会话ID
 */
function generateSessionId() {
    const id = 'sess_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
    localStorage.setItem('library_guide_session', id);
    return id;
}

/**
 * 重置会话（开始新对话）
 */
function resetSession() {
    SESSION_ID = generateSessionId();
    localStorage.setItem('library_guide_session', SESSION_ID);

    // 清空聊天记录
    const container = document.getElementById('chatContainer');
    container.innerHTML = '';

    // 重新显示欢迎消息
    renderWelcomeMessage();
    showQuickActions();
}

/**
 * 渲染欢迎消息
 */
function renderWelcomeMessage() {
    const container = document.getElementById('chatContainer');
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble assistant';
    bubble.innerHTML = `
        <div class="bubble-avatar">🤖</div>
        <div class="bubble-content">
            <div class="bubble-text">
                <p>你好！我是图书馆AI导览助手<strong>吉小图</strong> 👋</p>
                <p>我可以帮你：</p>
                <ul>
                    <li>📖 查询借阅规则和图书馆制度</li>
                    <li>📍 找到任何图书/区域的位置</li>
                    <li>🗺️ 规划从A到B的导航路径</li>
                    <li>📸 <strong>拍照识别书架位置</strong>（点击下方相机按钮）</li>
                </ul>
                <p>有什么可以帮你的？</p>
            </div>
        </div>
    `;
    container.appendChild(bubble);
}

/**
 * 页面初始化
 */
document.addEventListener('DOMContentLoaded', () => {
    // 初始化会话
    getSessionId();

    // 聚焦输入框
    document.getElementById('messageInput').focus();

    // 显示快捷操作
    showQuickActions();

    // 健康检查
    apiHealth()
        .then(data => {
            console.log('Server status:', data);
            updateStatusDot(true);
        })
        .catch(() => {
            console.warn('Server not reachable');
            updateStatusDot(false);
        });

    // 每隔30秒健康检查
    setInterval(() => {
        apiHealth()
            .then(() => updateStatusDot(true))
            .catch(() => updateStatusDot(false));
    }, 30000);

    // 关闭弹窗的点击事件
    const mapModal = document.getElementById('mapModal');
    if (mapModal) {
        mapModal.addEventListener('click', (e) => {
            if (e.target === e.currentTarget) closeMap();
        });
    }

    console.log('📚 图书馆AI导览助手 - 前端已就绪');
    console.log('Session:', SESSION_ID);
});

/**
 * 更新在线状态指示灯
 */
function updateStatusDot(online) {
    const dot = document.querySelector('.status-dot');
    const text = document.querySelector('.status-text');
    if (online) {
        dot.className = 'status-dot online';
        text.textContent = '在线';
    } else {
        dot.className = 'status-dot';
        text.textContent = '离线';
    }
}

/**
 * 点击地图弹窗背景关闭
 */
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeCamera();
        closeMap();
    }
});
