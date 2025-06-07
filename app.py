import re
import subprocess
import logging
import pandas as pd
import json
import os
from flask import Flask, request, render_template, jsonify
from datetime import datetime
import chardet
import difflib

app = Flask(__name__)

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


def run_ollama(data_content, question):
    logger.info("开始调用大模型 deepseek-r1:8b")
    if not check_ollama_status():
        logger.error("ollama 服务不可用，跳过模型调用")
        raise Exception("ollama 服务不可用")

    # 获取 file_name 用于代码生成
    import json
    summary = json.loads(data_content)
    file_name = summary.get('file_name', 'data.csv')

    prompt = f"""基于以下数据摘要：
{data_content}

解析以下问题，生成 Python 代码（使用 pandas 和 matplotlib）以读取原始 CSV 文件（假设文件名为 {file_name}）并完成绘图任务。代码应：
- 模糊匹配地区（如 "莫斯科" 识别为 "Moscow" 或其他相近名称，使用 difflib，默认为所有地区若未明确指定）。
- 动态确定时间跨度（根据问题中的年份范围，如 "2017-2023" 或 "近年" 取所有可用年份或最近 3 年）。
- 检测所有酒精种类列（基于 alcohol_types），根据问题选择绘制总和、均值或原始数据（默认为总和柱状图或折线图）。
- 保存图表为 PNG 文件。

问题：{question}

返回格式：
- 返回 Python 代码字符串，包含完整导入和保存逻辑。
"""
    logger.info(f"发送给大模型的提示词: {prompt}")

    logger.info("通过 API 调用 deepseek-r1:8b")
    try:
        import requests
        response = requests.post(
            'http://localhost:11434/api/generate',
            json={"model": "deepseek-r1:8b", "prompt": prompt, "stream": False},
            timeout=180
        )
        response.raise_for_status()
        result = response.json().get('response', '')

        if not result:
            logger.error("大模型返回空输出")
            raise Exception("大模型返回空输出")

        result = re.sub(r'[\u2580-\u259F]|\x1B\[[0-?]*[ -/]*[@-~]', '', result).strip()
        logger.info(f"大模型返回的原始输出: {result}")

        if '```' in result:
            plot_code = result.split('```')[1].strip()
            if plot_code.startswith('python'):
                plot_code = plot_code[len('python'):].strip()
        else:
            plot_code = result.strip()

        return {'plot_code': plot_code}
    except requests.exceptions.RequestException as e:
        logger.error(f"API 调用失败: {str(e)}")
        raise Exception(f"API 调用失败: {str(e)}")
    except Exception as e:
        logger.error(f"执行大模型命令时出错: {str(e)}")
        raise


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

    logger.info(f"上传文件: {file.filename}")
    logger.info(f"输入问题: {question}")
    try:
        df, json_summary = analyze_csv(file)
        if df is None or json_summary is None:
            logger.error("CSV 分析失败")
            return jsonify({"error": "CSV 分析失败"}), 500

        logger.info(f"CSV 摘要: {json_summary}")
        logger.info("CSV 分析成功，准备传给大模型")

        file.seek(0)
        save_backup(file, json_summary)

        response = run_ollama(json_summary, question)
        logger.info("从大模型获取响应成功")
        return jsonify({
            "plot_code": response['plot_code']
        })
    except Exception as e:
        logger.error(f"处理文件上传或大模型调用时出错: {str(e)}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)

