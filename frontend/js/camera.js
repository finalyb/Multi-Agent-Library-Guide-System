/**
 * 图片上传模块
 * 支持从相册/文件选择照片，上传到后端进行AI识别
 */

// 页面加载后绑定事件
document.addEventListener("DOMContentLoaded", function () {
    const fileInput = document.getElementById("imageFileInput");
    if (fileInput) {
        fileInput.addEventListener("change", function (event) {
            console.log("File selected:", event.target.files[0]?.name);
            handleFileUpload(event);
        });
        console.log("File upload listener bound");
    } else {
        console.error("imageFileInput not found!");
    }
});

/**
 * 处理文件上传
 */
function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) {
        console.log("No file selected");
        return;
    }

    console.log("Processing:", file.name, file.type, file.size);

    // 验证文件类型
    if (!file.type.startsWith("image/")) {
        alert("请选择图片文件（JPG/PNG/WebP）");
        return;
    }

    // 验证文件大小（10MB）
    if (file.size > 10 * 1024 * 1024) {
        alert("图片过大，请选择10MB以内的文件");
        return;
    }

    // 上传并处理
    processImage(file);

    // 重置input，允许重复选择同一文件
    event.target.value = "";
}

/**
 * 处理图片：上传 → 识别 → 展示结果
 */
async function processImage(imageBlob) {
    console.log("processImage started, blob:", imageBlob.type, imageBlob.size);

    const overlay = document.getElementById("loadingOverlay");
    const loadingText = document.getElementById("loadingText");

    // 显示加载
    overlay.classList.add("active");
    loadingText.textContent = "正在识别中...";

    // 渲染用户图片消息
    renderImageMessage(imageBlob);

    // 渲染AI占位
    const bubble = renderAssistantPlaceholder();
    currentAssistantBubble = bubble;

    try {
        loadingText.textContent = "AI正在分析图片...";
        console.log("Calling apiUploadImage...");
        const result = await apiUploadImage(imageBlob, getSessionId());
        console.log("Upload result:", result);

        // 关闭加载
        overlay.classList.remove("active");

        // 渲染结果
        const textDiv = bubble.querySelector(".bubble-text");
        const indicator = textDiv.querySelector(".typing-indicator");
        if (indicator) indicator.remove();

        textDiv.innerHTML = formatResponse(result.response);

        // 如果有路径信息，显示路径卡片
        if (result.path_info && result.path_info.directions) {
            appendPathCard(bubble, result.path_info);
        }

        // 如果有识别位置，保存到会话
        if (result.target_location) {
            console.log("识别位置:", result.target_location);
        }

    } catch (error) {
        console.error("Image processing error:", error);
        overlay.classList.remove("active");

        const textDiv = bubble.querySelector(".bubble-text");
        const indicator = textDiv.querySelector(".typing-indicator");
        if (indicator) indicator.remove();
        textDiv.innerHTML = "<p>抱歉，图片识别失败。请换一张照片重试，或直接描述位置。</p>";
    }
}

/**
 * 渲染用户发送的图片
 */
function renderImageMessage(imageBlob) {
    const container = document.getElementById("chatContainer");
    const imageUrl = URL.createObjectURL(imageBlob);

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble user";
    bubble.innerHTML = `
        <div class="bubble-content">
            <div class="bubble-text" style="padding: 6px; background: transparent;">
                <img src="${imageUrl}" alt="上传的图片"
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
        .replace(/\n/g, "<br>")
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

/**
 * 追加路径卡片
 */
function appendPathCard(bubble, pathInfo) {
    const content = bubble.querySelector(".bubble-content");
    const card = document.createElement("div");
    card.className = "path-card";

    let stepsHtml = "";
    if (pathInfo.directions && pathInfo.directions.length > 0) {
        stepsHtml = pathInfo.directions
            .map(s => `<div class="path-step">${escapeHtml(s)}</div>`)
            .join("");
    }

    card.innerHTML = `
        <div class="path-title">🗺️ 导航路径</div>
        ${stepsHtml}
    `;
    content.appendChild(card);
}

/**
 * HTML转义
 */
function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}
