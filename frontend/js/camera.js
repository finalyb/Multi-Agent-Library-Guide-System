/**
 * 相机模块
 * 管理拍照、相册选择、图片上传和识别结果处理
 */

let cameraStream = null;

/**
 * 打开相机
 */
async function openCamera() {
    const modal = document.getElementById('cameraModal');
    const video = document.getElementById('cameraPreview');

    modal.classList.add('active');

    try {
        // 优先使用后置摄像头（environment）
        cameraStream = await navigator.mediaDevices.getUserMedia({
            video: {
                facingMode: 'environment',
                width: { ideal: 1280 },
                height: { ideal: 720 },
            },
            audio: false,
        });
        video.srcObject = cameraStream;
    } catch (err) {
        console.error('Camera access denied:', err);
        // 降级：只显示文件上传选项
        video.style.display = 'none';
        document.getElementById('btnCapture').style.display = 'none';
        alert('无法访问相机，请使用相册上传图片。\n\n请在浏览器设置中允许相机权限，或使用"从相册选择"按钮。');
    }
}

/**
 * 关闭相机
 */
function closeCamera() {
    const modal = document.getElementById('cameraModal');
    modal.classList.remove('active');

    // 停止摄像头
    if (cameraStream) {
        cameraStream.getTracks().forEach(track => track.stop());
        cameraStream = null;
    }

    // 恢复视频元素
    const video = document.getElementById('cameraPreview');
    video.style.display = '';
    document.getElementById('btnCapture').style.display = '';
}

/**
 * 拍照
 */
function capturePhoto() {
    const video = document.getElementById('cameraPreview');
    const canvas = document.getElementById('cameraCanvas');

    if (!cameraStream) {
        alert('相机未就绪，请使用"从相册选择"');
        return;
    }

    // 设置canvas尺寸
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    // 绘制当前帧
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0);

    // 转换为Blob
    canvas.toBlob(async (blob) => {
        // 关闭相机
        closeCamera();

        // 上传并处理
        await processImage(blob);
    }, 'image/jpeg', 0.85);
}

/**
 * 从相册选择文件
 */
function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    // 关闭相机
    closeCamera();

    // 验证文件类型
    if (!file.type.startsWith('image/')) {
        alert('请选择图片文件（JPG/PNG/WebP）');
        return;
    }

    // 验证文件大小
    if (file.size > 10 * 1024 * 1024) {
        alert('图片过大，请选择10MB以内的文件');
        return;
    }

    // 上传并处理
    processImage(file);

    // 重置input
    event.target.value = '';
}

/**
 * 处理图片：上传 → 识别 → 展示结果
 */
async function processImage(imageBlob) {
    const overlay = document.getElementById('loadingOverlay');
    const loadingText = document.getElementById('loadingText');

    // 显示加载
    overlay.classList.add('active');
    loadingText.textContent = '正在识别中...';

    // 渲染用户图片消息
    renderImageMessage(imageBlob);

    // 渲染AI占位
    const bubble = renderAssistantPlaceholder();
    currentAssistantBubble = bubble;

    try {
        // 上传并获取结果
        loadingText.textContent = 'AI正在分析图片...';
        const result = await apiUploadImage(imageBlob, getSessionId());

        // 关闭加载
        overlay.classList.remove('active');

        // 渲染结果
        const textDiv = bubble.querySelector('.bubble-text');
        const indicator = textDiv.querySelector('.typing-indicator');
        if (indicator) indicator.remove();

        textDiv.innerHTML = formatResponse(result.response);

        // 如果有路径信息，显示路径卡片
        if (result.path_info && result.path_info.directions) {
            appendPathCard(bubble, result.path_info);
        }

    } catch (error) {
        console.error('Image processing error:', error);
        overlay.classList.remove('active');

        const textDiv = bubble.querySelector('.bubble-text');
        const indicator = textDiv.querySelector('.typing-indicator');
        if (indicator) indicator.remove();
        textDiv.innerHTML = '<p>抱歉，图片识别失败。请换个角度再拍一次，或直接描述你的位置。</p>';
    }
}

/**
 * 渲染用户发送的图片
 */
function renderImageMessage(imageBlob) {
    const container = document.getElementById('chatContainer');
    const imageUrl = URL.createObjectURL(imageBlob);

    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble user';
    bubble.innerHTML = `
        <div class="bubble-content">
            <div class="bubble-text" style="padding: 6px; background: transparent;">
                <img src="${imageUrl}" alt="用户拍摄的图片"
                     style="max-width: 200px; border-radius: 12px; display: block;">
            </div>
        </div>
    `;
    container.appendChild(bubble);
    scrollToBottom();

    // 清理URL
    setTimeout(() => URL.revokeObjectURL(imageUrl), 5000);
}

/**
 * 格式化回复文本
 */
function formatResponse(text) {
    return text
        .replace(/\n/g, '<br>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/📖|📍|🗺️|🕐|💺|🎯/g, '');
}

/**
 * 追加路径卡片
 */
function appendPathCard(bubble, pathInfo) {
    const content = bubble.querySelector('.bubble-content');
    const card = document.createElement('div');
    card.className = 'path-card';

    let stepsHtml = '';
    if (pathInfo.directions && pathInfo.directions.length > 0) {
        stepsHtml = pathInfo.directions
            .map(s => `<div class="path-step">${escapeHtml(s)}</div>`)
            .join('');
    }

    card.innerHTML = `
        <div class="path-title">🗺️ 导航路径</div>
        ${stepsHtml}
        <button onclick="openMapModal('${escapeHtml(JSON.stringify(pathInfo))}')"
                style="margin-top:8px; padding:6px 14px; border-radius:16px;
                       border:1px solid var(--primary); background:white;
                       color:var(--primary); cursor:pointer; font-size:13px;">
            查看详细路线
        </button>
    `;

    content.appendChild(card);
}

/**
 * 打开地图弹窗
 */
function openMapModal(pathInfoStr) {
    let pathInfo;
    try {
        pathInfo = JSON.parse(pathInfoStr);
    } catch {
        return;
    }

    const modal = document.getElementById('mapModal');
    const content = document.getElementById('mapContent');

    const stepsHtml = (pathInfo.directions || [])
        .map((step, i) => `
            <li class="map-step">
                <span class="step-num">${i + 1}</span>
                <span class="step-text">${escapeHtml(step)}</span>
            </li>
        `).join('');

    content.innerHTML = `
        <div class="map-location">
            <h3>📍 ${escapeHtml(pathInfo.to_location || '目的地')}</h3>
            <p>从 ${escapeHtml(pathInfo.from_location || '当前位置')} 出发 · 共 ${pathInfo.steps || 0} 步</p>
        </div>
        <ul class="map-steps">${stepsHtml}</ul>
    `;

    modal.classList.add('active');
}

/**
 * 关闭地图弹窗
 */
function closeMap() {
    document.getElementById('mapModal').classList.remove('active');
}
