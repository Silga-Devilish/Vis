// 全局变量存储上传的数据
let uploadedData = null;

// 确保Chart.js已加载
document.addEventListener('DOMContentLoaded', function() {
    if (!window.Chart) {
        alert("Chart.js库加载失败，请检查网络连接");
        return;
    }

    // 初始化文件上传
    document.getElementById('upload-btn').addEventListener('click', function() {
        document.getElementById('file-input').click();
    });

    document.getElementById('file-input').addEventListener('change', handleFileUpload);
});

// 文件上传处理
async function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    document.getElementById('file-name').textContent = file.name;
    document.getElementById('upload-btn').disabled = true;
    document.getElementById('upload-btn').textContent = "分析中...";

    try {
        const fileContent = await readFileAsText(file);
        uploadedData = parseData(fileContent);

        // 显示数据预览和分析
        showDataPreview(uploadedData);
        await analyzeData(uploadedData);

        // 显示图表控制区域
        document.getElementById('chart-controls').classList.remove('hidden');

    } catch (error) {
        console.error("文件处理失败:", error);
        alert("文件处理失败: " + error.message);
    } finally {
        document.getElementById('upload-btn').disabled = false;
        document.getElementById('upload-btn').textContent = "导入数据文件";
    }
}

// 读取文件为文本
function readFileAsText(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = event => resolve(event.target.result);
        reader.onerror = error => reject(error);
        reader.readAsText(file);
    });
}

// 简单数据解析（可根据实际格式调整）
function parseData(content) {
    // 简单处理：按行分割，制表符或逗号分隔
    const lines = content.split('\n').filter(line => line.trim());
    const delimiter = content.includes('\t') ? '\t' : ',';

    return {
        raw: content,
        lines: lines,
        rows: lines.map(line => line.split(delimiter)),
        delimiter: delimiter
    };
}

// 显示数据预览
function showDataPreview(data) {
    const previewElement = document.getElementById('data-preview');
    previewElement.innerHTML = '';

    // 显示前100行数据
    const displayLines = data.lines.slice(0, 100);
    displayLines.forEach(line => {
        const div = document.createElement('div');
        div.textContent = line;
        previewElement.appendChild(div);
    });

    if (data.lines.length > 100) {
        const more = document.createElement('div');
        more.textContent = `...还有${data.lines.length - 100}行未显示`;
        previewElement.appendChild(more);
    }

    document.getElementById('data-analysis').classList.remove('hidden');
}

// 简单的Markdown转HTML解析器
function parseMarkdown(mdText) {
    // 替换标题
    mdText = mdText.replace(/^#\s(.+)$/gm, '<h3>$1</h3>');
    mdText = mdText.replace(/^##\s(.+)$/gm, '<h4>$1</h4>');

    // 修复数字列表解析
    mdText = mdText.replace(/^(\d+)\.\s(.*$)/gm, function(match, p1, p2) {
        return '<li>' + p2 + '</li>';
    });

    // 替换无序列表
    mdText = mdText.replace(/^\s*-\s(.*$)/gm, '<li>$1</li>');
    mdText = mdText.replace(/^\s*\*\s(.*$)/gm, '<li>$1</li>');

    // 包裹列表
    mdText = mdText.replace(/(<li>.*<\/li>)+/g, function(match) {
        // 检查是否是数字列表
        if (match.match(/<li>\d/)) {
            return '<ol>' + match + '</ol>';
        } else {
            return '<ul>' + match + '</ul>';
        }
    });

    // 替换加粗
    mdText = mdText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // 替换段落
    mdText = mdText.replace(/^(?!<[a-z])(.*$)/gm, function(match) {
        if (match.trim().length === 0) return '';
        return '<p>' + match + '</p>';
    });

    return mdText;
}

// 分析数据（调用API）
async function analyzeData(data) {
    const analysisElement = document.getElementById('analysis-result');
    analysisElement.innerHTML = '<p class="loading">正在分析数据...</p>';

    try {
        const prompt = `分析以下数据集并简要描述其特征:\n\n${data.raw.substring(0, 2000)}...`;
        const response = await callDeepseekAPI(prompt, false);

        let analysisText = response.choices[0]?.message?.content || "未能获取分析结果";
        // 清理分析结果中的代码块标记
        analysisText = analysisText.replace(/```/g, '');
        const htmlContent = parseMarkdown(analysisText);

        analysisElement.innerHTML = htmlContent;

    } catch (error) {
        console.error("数据分析失败:", error);
        analysisElement.innerHTML = `
            <div class="error-box">
                <p>数据分析失败: ${error.message}</p>
            </div>
        `;
    }
}

// 修改后的API调用函数
async function callDeepseekAPI(prompt, isChartRequest = true) {
    const apiKey = "sk-24ef6c01fb054870b7e571c02a7a528e"; // 替换为你的实际API密钥
    const apiUrl = "https://api.deepseek.com/v1/chat/completions";

    let content;
    if (isChartRequest) {
        content = `基于以下数据生成Chart.js图表代码(使用canvas id="chart-canvas")，要求:
        数据: ${JSON.stringify(uploadedData.rows)}
        需求: ${prompt}
        只返回纯粹的JavaScript代码，不要任何解释或注释`;
    } else {
        content = prompt;
    }

    const response = await fetch(apiUrl, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${apiKey}`
        },
        body: JSON.stringify({
            model: "deepseek-coder",
            messages: [{
                role: "user",
                content: content
            }],
            temperature: 0.3
        })
    });

    if (!response.ok) {
        throw new Error(`API请求失败: ${response.status}`);
    }

    return await response.json();
}

// 图表生成按钮点击事件
document.getElementById('generate-btn').addEventListener('click', async function() {
    const btn = this;
    const userInput = document.getElementById('user-input').value.trim();
    if (!userInput) {
        alert("请输入图表描述");
        return;
    }
    if (!uploadedData) {
        alert("请先上传数据文件");
        return;
    }

    btn.disabled = true;
    btn.textContent = "生成中...";

    try {
        // 1. 调用Deepseek API获取代码
        const response = await callDeepseekAPI(userInput);
        const generatedCode = extractChartCode(response);

        // 2. 显示生成的代码
        document.getElementById('code-output').textContent = generatedCode;

        // 3. 执行代码绘制图表
        executeChartCode(generatedCode);

    } catch (error) {
        console.error("生成图表失败:", error);
        alert("生成图表失败: " + error.message);
    } finally {
        btn.disabled = false;
        btn.textContent = "生成图表";
    }
});

function extractChartCode(apiResponse) {
    let code = apiResponse.choices[0]?.message?.content || "";
    code = code.replace(/```(javascript)?|```/g, '').trim();
    if (!code.includes("new Chart")) {
        throw new Error("API返回的代码格式不正确");
    }
    return code;
}

function executeChartCode(code) {
    const canvas = document.getElementById('chart-canvas');
    if (!canvas) throw new Error("找不到canvas元素");

    try {
        // 确保彻底销毁之前的图表
        if (window.activeChart) {
            window.activeChart.destroy();
            window.activeChart = null;
        }

        // 方法1：更可靠的正则表达式提取配置对象
        const configMatch = code.match(/new\s+Chart$[^,]+,\s*({[\s\S]*?})\s*$/);
        if (configMatch) {
            const configStr = configMatch[1];
            // 安全解析配置对象
            const config = new Function(`return ${configStr}`)();

            // 清除canvas并创建新图表
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            window.activeChart = new Chart(ctx, config);
            return;
        }

        // 方法2：直接执行代码（更安全的实现）
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // 创建安全执行环境
        const execute = new Function(`
            "use strict";
            try {
                const ctx = arguments[0];
                ${code
                    .replace(/const\s+ctx\s*=.+?;/, '')  // 移除ctx声明
                    .replace(/const\s+chart\s*=\s*new Chart/, 'window.activeChart = new Chart')  // 修改chart变量赋值
                }
                return window.activeChart;
            } catch(e) {
                console.error("执行错误:", e);
                throw e;
            }
        `);

        window.activeChart = execute(ctx);

    } catch (error) {
        console.error("图表创建失败:", error);
        throw new Error("图表创建失败: " + error.message);
    }
}
