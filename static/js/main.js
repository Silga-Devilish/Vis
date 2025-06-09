// 图片错误处理
function handleImageError(imgElement) {
    const wrapper = imgElement.parentElement;
    wrapper.innerHTML = '<div class="error">图表加载失败</div>';
    console.error('图片加载失败:', imgElement.src);
}

// 显示历史记录
async function showHistory() {
    const container = document.getElementById('historyContainer');
    const showBtn = document.getElementById('showHistoryBtn');
    const hideBtn = document.getElementById('hideHistoryBtn');
    
    container.innerHTML = '<div class="loading">加载历史记录...</div>';
    container.style.display = 'block';
    showBtn.style.display = 'none';
    hideBtn.style.display = 'inline-block';
    
    try {
        const response = await fetch('/list_archive');
        if (!response.ok) throw new Error('获取历史记录失败');
        
        const historyData = await response.json();
        
        if (historyData.length === 0) {
            container.innerHTML = '<div class="info">暂无历史记录</div>';
            return;
        }
        
        let html = '';
        historyData.forEach(day => {
            html += `<div class="day-group">
                <h4>📅 ${day.date}</h4>
                <div class="day-images">`;
            
            day.files.forEach(file => {
                html += `<div class="history-image">
                    <img src="${file.path}" 
                         alt="${file.name}" 
                         loading="lazy"
                         onerror="this.style.display='none'">
                    <div>${file.name} (${Math.round(file.size/1024)}KB)</div>
                </div>`;
            });
            
            html += `</div></div>`;
        });
        
        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = `<div class="error">加载失败: ${error.message}</div>`;
    }
}

// 隐藏历史记录
function hideHistory() {
    const container = document.getElementById('historyContainer');
    const showBtn = document.getElementById('showHistoryBtn');
    const hideBtn = document.getElementById('hideHistoryBtn');
    
    container.style.display = 'none';
    showBtn.style.display = 'inline-block';
    hideBtn.style.display = 'none';
}

// 表单提交处理
document.getElementById('uploadForm').addEventListener('submit', async function(event) {
    event.preventDefault();

    const answerDiv = document.getElementById('answer');
    answerDiv.innerHTML = '<div class="loading">🔄 正在分析数据并生成可视化结果，请稍候...</div>';

    try {
        const formData = new FormData(this);
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errorText = await response.text();
            try {
                const errorJson = JSON.parse(errorText);
                throw new Error(errorJson.error || errorText);
            } catch {
                throw new Error(errorText);
            }
        }

        const result = await response.json();
        answerDiv.innerHTML = '';

        // 显示成功消息
        const successMsg = document.createElement('div');
        successMsg.className = 'success-message';
        successMsg.textContent = '✅ 分析完成！以下是结果:';
        answerDiv.appendChild(successMsg);

        // 显示代码
        if (result.plot_code) {
            const codeSection = document.createElement('div');
            codeSection.className = 'code-section';
            codeSection.innerHTML = `
                <h3>💻 生成代码</h3>
                <div class="code-container">
                    <button class="copy-btn" data-clipboard-target="#generated-code">
                        复制代码
                    </button>
                    <pre><code id="generated-code" class="language-python">${result.plot_code}</code></pre>
                </div>
            `;
            answerDiv.appendChild(codeSection);

            hljs.highlightAll();
            new ClipboardJS('.copy-btn');
        }

        // 显示所有生成的图片
        if (result.images && result.images.length > 0) {
            const chartsContainer = document.createElement('div');
            chartsContainer.className = 'multi-chart-container';
            
            result.images.forEach((img, index) => {
                const chartCard = document.createElement('div');
                chartCard.className = 'chart-card';
                const imgUrl = `${img.url}&t=${Date.now()}`;
                chartCard.innerHTML = `
                    <div class="chart-title">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
                            <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
                            <line x1="12" y1="22.08" x2="12" y2="12"></line>
                        </svg>
                        图表 ${index + 1}: ${img.name.replace('.png', '')}
                    </div>
                    <div class="img-wrapper">
                        <img src="${imgUrl}" 
                             alt="${img.name}"
                             loading="lazy"
                             onerror="handleImageError(this)">
                    </div>
                `;
                chartsContainer.appendChild(chartCard);
            });
            
            answerDiv.appendChild(chartsContainer);
        } else {
            answerDiv.innerHTML += '<div class="info">未生成任何图表</div>';
        }

    } catch (error) {
        answerDiv.innerHTML = `
            <div class="error">
                <h3>❌ 处理失败</h3>
                <p>${error.message}</p>
                <button onclick="location.reload()" style="margin-top:10px;">重新尝试</button>
            </div>
        `;
        console.error('处理失败:', error);
        document.getElementById('debugInfo').textContent = error.stack || error.message;
        document.getElementById('debugPanel').style.display = 'block';
    }
});

// 历史记录按钮事件
document.getElementById('showHistoryBtn').addEventListener('click', showHistory);
document.getElementById('hideHistoryBtn').addEventListener('click', hideHistory);
