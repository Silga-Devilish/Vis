import re
import subprocess
import logging
import traceback

import pandas as pd
import json
import os
from flask import Flask, request, render_template, jsonify
from datetime import datetime
import chardet
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import difflib

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False  # 禁用美化输出
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 允许50MB大文件

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def analyze_csv(file_stream):
    """
    分析 CSV 文件流，生成精简的 JSON 数据摘要，包含列信息和预览。
    参数：
        file_stream: 上传的 CSV 文件流
    返回：
        tuple: (DataFrame, str) - 原始数据和 JSON 格式的摘要
    """
    try:
        raw_data = file_stream.read()
        result = chardet.detect(raw_data)
        encoding = result['encoding']
        logger.info(f"检测到文件编码: {encoding}")

        try:
            content = raw_data.decode(encoding)
        except (UnicodeDecodeError, TypeError):
            logger.warning(f"使用 {encoding} 解码失败，尝试使用 utf-8")
            content = raw_data.decode('utf-8', errors='replace')

        from io import StringIO
        df = pd.read_csv(StringIO(content))
        file_name = file_stream.filename

        # 检测列类型和酒精种类
        columns = {col: 'numeric' if pd.api.types.is_numeric_dtype(df[col]) else 'other' for col in df.columns}
        alcohol_types = [col for col in df.columns if
                         'alcohol' in col.lower() or 'vodka' in col.lower() or 'wine' in col.lower() or 'beer' in col.lower()]
        preview_rows = df.head(3).to_dict(orient='records')
        for row in preview_rows:
            for key, value in row.items():
                if pd.isna(value):
                    row[key] = None
                elif isinstance(value, (pd.Timestamp, datetime)):
                    row[key] = str(value)
                elif isinstance(value, (int, float)):
                    row[key] = float(value) if isinstance(value, float) else int(value)

        summary = {
            'file_name': file_name,
            'columns': columns,
            'alcohol_types': alcohol_types,
            'regions': list(df['Region'].unique()) if 'Region' in df.columns else [],
            'years': sorted(df['Year'].unique().astype(str).tolist()) if 'Year' in df.columns else [],
            'data_preview': preview_rows
        }

        json_summary = json.dumps(summary, ensure_ascii=False, indent=2)
        return df, json_summary
    except Exception as e:
        logger.error(f"分析 CSV 文件时出错: {str(e)}")
        file_stream.seek(0)
        save_backup(file_stream, json.dumps({"error": str(e)}, ensure_ascii=False, indent=2))
        return None, None


def save_backup(file_stream, json_summary):
    """
    保存上传的 CSV 文件和 JSON 摘要到备份文件夹。
    参数：
        file_stream: 上传的 CSV 文件流
        json_summary: 生成的 JSON 摘要
    返回：
        None
    """
    try:
        backup_dir = os.path.join(os.getcwd(), 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_filename = os.path.splitext(file_stream.filename)[0]
        csv_backup_path = os.path.join(backup_dir, f"{base_filename}_{timestamp}.csv")
        file_stream.seek(0)
        with open(csv_backup_path, 'wb') as f:
            f.write(file_stream.read())
        logger.info(f"已保存 CSV 文件备份: {csv_backup_path}")
        json_backup_path = os.path.join(backup_dir, f"{base_filename}_{timestamp}_summary.json")
        with open(json_backup_path, 'w', encoding='utf-8') as f:
            f.write(json_summary)
        logger.info(f"已保存 JSON 摘要备份: {json_backup_path}")
    except Exception as e:
        logger.error(f"保存备份时出错: {str(e)}")


def check_ollama_status():
    """检查 ollama 服务是否可用"""
    logger.info("检查 ollama 服务状态")
    try:
        result = subprocess.run(['ollama', '--version'], capture_output=True, text=True, timeout=10)
        logger.info(f"ollama 版本: {result.stdout.strip()}")
        return True
    except subprocess.TimeoutExpired:
        logger.error("检查 ollama 状态超时")
        return False
    except Exception as e:
        logger.error(f"检查 ollama 状态失败: {str(e)}")
        return False


def run_deepseek(data_content, question):
    logger.info("开始调用DeepSeek API")

    # 获取file_name用于代码生成
    import json
    summary = json.loads(data_content)
    file_name = summary.get('file_name', 'data.csv')

    prompt = f"""基于以下数据摘要：
{data_content}

请生成Python代码（使用pandas和matplotlib）读取CSV文件（假设文件名为{file_name}）并完成绘图任务。要求：
1. 模糊匹配地区（如"莫斯科"识别为"Moscow"或其他相近名称）
2. 动态确定时间跨度（根据问题中的年份范围）
3. 检测所有酒精种类列（基于alcohol_types）
4. 保存图表为PNG文件

问题：{question}

请只返回Python代码，包含完整导入和保存逻辑，不需要任何解释。
代码块必须用```python包裹。
"""

    try:
        import requests
        headers = {
            "Authorization": "Bearer sk-b6b7f0fb779f47449fb2a72642974a9b",  # 替换为实际API密钥
            "Content-Type": "application/json"
        }
        payload = {
            "model": "deepseek-chat",  # 或其他可用模型
            "messages": [
                {"role": "system", "content": "你是一个专业的数据分析师，擅长生成Python可视化代码"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3  # 降低随机性
        }

        response = requests.post(
            'https://api.deepseek.com/v1/chat/completions',  # 确认实际API端点
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()

        result = response.json()['choices'][0]['message']['content']
        logger.info(f"DeepSeek API返回内容: {result}")

        # 提取代码块
        if '```python' in result:
            plot_code = result.split('```python')[1].split('```')[0].strip()
        elif '```' in result:
            plot_code = result.split('```')[1].split('```')[0].strip()
            if plot_code.startswith('python'):
                plot_code = plot_code[6:].strip()
        else:
            plot_code = result.strip()

        return {'plot_code': plot_code}

    except Exception as e:
        logger.error(f"DeepSeek API调用失败: {str(e)}")
        raise Exception(f"DeepSeek API调用失败: {str(e)}")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    logger.info("接收到文件上传请求")
    if 'file' not in request.files or 'question' not in request.form:
        logger.error("未找到上传文件或问题文本")
        return jsonify({"error": "未找到上传文件或问题文本"}), 400

    file = request.files['file']
    question = request.form['question']
    if file.filename == '' or not question:
        logger.error("上传文件名或问题文本为空")
        return jsonify({"error": "上传文件名或问题文本为空"}), 400

    try:
        df, json_summary = analyze_csv(file)
        response = run_deepseek(json_summary, question)
        img_buffer = execute_plot_code(response['plot_code'], df)

        # 获取base64编码
        img_buffer = execute_plot_code(response['plot_code'], df)

        # Base64编码并确保字符串安全
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')

        # 调试输出
        logger.info(f"Base64数据长度: {len(img_base64)}")
        logger.info(f"前100字符: {img_base64[:100]}")
        logger.info(f"最后100字符: {img_base64[-100:]}")

        # 构建响应数据（使用json.dumps确保格式正确）
        response_data = {
            "image_base64": img_base64,
            "plot_code": response['plot_code'],
            "model": "deepseek"
        }

        # 手动生成JSON字符串（确保特殊字符被转义）
        import json
        json_str = json.dumps(response_data, ensure_ascii=False)

        # 验证JSON是否有效
        try:
            json.loads(json_str)  # 测试反序列化
        except json.JSONDecodeError as e:
            logger.error(f"生成的JSON无效: {str(e)}")
            raise ValueError("生成的数据包含无效字符")

        # 返回响应（使用Response对象更可靠）
        from flask import Response
        return Response(
            response=json_str,
            status=200,
            mimetype='application/json',
            headers={
                'Content-Length': str(len(json_str)),
                'Cache-Control': 'no-store',
                'X-Content-Type-Options': 'nosniff'
            }
        )

    except Exception as e:
        logger.error(f"处理失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
def sanitize_base64(base64_str):
    """清理Base64字符串中的潜在问题字符"""
    import re
    # 移除所有非Base64标准字符
    return re.sub(r'[^a-zA-Z0-9+/=]', '', base64_str)

def validate_and_fix_code(plot_code):
    """验证并修复生成的代码"""
    try:
        # 尝试编译代码检查语法
        compile(plot_code, '<string>', 'exec')
        return plot_code
    except SyntaxError as e:
        logger.warning(f"检测到语法错误: {str(e)}")
        # 自动修复常见错误
        if "was never closed" in str(e):
            fixed_code = plot_code.replace(
                "df['Region'].unique()",
                "df['Region'].unique())"
            )
            try:
                compile(fixed_code, '<string>', 'exec')
                logger.info("已自动修复括号不匹配问题")
                return fixed_code
            except SyntaxError:
                pass
        # 如果无法自动修复，返回原始代码让错误暴露
        return plot_code


def execute_plot_code(plot_code, df):
    import matplotlib
    matplotlib.use('Agg', force=True)
    import matplotlib.pyplot as plt
    from io import BytesIO
    import numpy as np

    plt.close('all')

    try:
        # 创建独立命名空间
        local_vars = {
            'pd': pd,
            'plt': plt,
            'df': df,
            'np': np,
            '__builtins__': __builtins__
        }

        # 执行原始代码（不再移除savefig）
        exec(plot_code, local_vars)

        # 获取当前图形
        fig = plt.gcf()
        if not fig.axes:
            # 紧急恢复：绘制默认图形
            ax = fig.add_subplot(111)
            df.iloc[:, 0].value_counts().head(5).plot(kind='bar', ax=ax)
            ax.set_title('自动生成的备用图表')

        # 保存到缓冲区
        img_buffer = BytesIO()
        fig.savefig(img_buffer, format='png', bbox_inches='tight', dpi=100)
        img_buffer.seek(0)

        # 调试输出
        print(f"图形尺寸: {fig.get_size_inches()}")
        print(f"坐标轴数量: {len(fig.axes)}")
        return img_buffer

    except Exception as e:
        plt.close('all')
        raise RuntimeError(f"绘图失败: {str(e)}") from e
    finally:
        plt.close('all')


if __name__ == '__main__':
    app.run(debug=True)

