/**
 * API 通信模块
 * 封装与后端的 Fetch 请求，处理 SSE 流式响应
 */

const API_BASE = window.location.origin;

/**
 * 非流式对话请求
 */
async function apiChat(message, sessionId = null) {
    const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message: message,
            session_id: sessionId || getSessionId(),
        }),
    });

    if (!response.ok) {
        const err = await response.json();
        throw new Error(err.error || '请求失败');
    }

    return await response.json();
}

/**
 * 流式对话请求 (SSE)
 * 返回 ReadableStream，逐字读取AI回复
 */
async function apiChatStream(message, sessionId, onToken, onDone, onError) {
    const response = await fetch(`${API_BASE}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message: message,
            session_id: sessionId || getSessionId(),
        }),
    });

    if (!response.ok) {
        const err = await response.json();
        onError(new Error(err.error || '流式请求失败'));
        return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';  // 最后不完整的一行留在buffer

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);
                    if (data === '[DONE]') {
                        onDone();
                        return;
                    }
                    if (data.startsWith('[ERROR:')) {
                        onError(new Error(data));
                        return;
                    }
                    onToken(data);
                }
            }
        }
    } catch (err) {
        onError(err);
    }
}

/**
 * 图片上传请求
 */
async function apiUploadImage(file, sessionId) {
    const formData = new FormData();
    formData.append('image', file);
    formData.append('session_id', sessionId || getSessionId());

    const response = await fetch(`${API_BASE}/upload/image`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const err = await response.json();
        throw new Error(err.error || '图片上传失败');
    }

    return await response.json();
}

/**
 * 健康检查
 */
async function apiHealth() {
    const response = await fetch(`${API_BASE}/health`);
    return await response.json();
}

/**
 * 重建知识库（管理接口）
 */
async function apiRebuildKB() {
    const response = await fetch(`${API_BASE}/admin/rebuild-kb`, {
        method: 'POST',
    });
    return await response.json();
}
