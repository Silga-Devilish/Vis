import re
import shutil
import subprocess
import logging
import tempfile
import traceback

import pandas as pd
import json
import os
from flask import Flask, request, render_template, jsonify, send_file
from datetime import datetime
import chardet
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import difflib

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False  # 禁用美化输出
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 允许50MB大文件

app.config['TEMP_IMG_DIR'] = os.path.join(os.getcwd(), 'temp_images')
app.config['ARCHIVE_IMG_DIR'] = os.path.join(os.getcwd(), 'archive_images')

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
        # 初始化目录
        init_dirs()
        clear_temp_images()

        # 1. 分析CSV文件
        df, json_summary = analyze_csv(file)
        if df is None:
            raise ValueError("CSV文件分析失败")

        # 2. 调用DeepSeek API获取绘图代码
        response = run_deepseek(json_summary, question)
        plot_code = response['plot_code']
        logger.info(f"获取到的绘图代码:\n{plot_code}")

        # 3. 执行绘图代码
        generated_images = execute_plot_code(plot_code, df, file.filename)

        # 4. 归档所有图片并准备响应
        image_urls = []
        for img_path in generated_images:
            # 将图片移动到正式临时目录
            filename = os.path.basename(img_path)
            dest_path = os.path.join(app.config['TEMP_IMG_DIR'], filename)
            shutil.move(img_path, dest_path)

            # 归档图片
            archive_path = archive_image(dest_path)
            logger.info(f"图片已归档: {archive_path}")

            image_urls.append({
                "name": filename,
                "url": f"/get_image?path={filename}"
            })

        # 5. 返回结果
        return jsonify({
            "plot_code": plot_code,
            "images": image_urls,
            "model": "deepseek"
        })

    except Exception as e:
        logger.error(f"处理失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@app.route('/list_images')
def list_images():
    """返回当前目录下的图片文件列表"""
    image_extensions = ('.png', '.jpg', '.jpeg', '.gif')
    image_files = []

    for filename in os.listdir(os.getcwd()):
        if filename.lower().endswith(image_extensions):
            file_path = os.path.join(os.getcwd(), filename)
            image_files.append({
                'name': filename,
                'size': os.path.getsize(file_path),
                'lastModified': int(os.path.getmtime(file_path))
            })

    return jsonify(image_files)


@app.route('/<filename>')
def serve_image(filename):
    """提供图片文件"""
    if not filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
        return jsonify({"error": "Invalid file type"}), 400

    file_path = os.path.join(os.getcwd(), filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    return send_file(file_path)


@app.route('/get_image')
def get_image():
    """提供生成的图片文件"""
    try:
        file_name = request.args.get('path')
        if not file_name or not re.match(r'^[\w-]+\.(png|jpg|jpeg)$', file_name, re.IGNORECASE):
            return jsonify({"error": "非法文件名"}), 400

        file_path = os.path.join(app.config['TEMP_IMG_DIR'], file_name)
        if not os.path.exists(file_path):
            # 尝试从归档目录查找
            date_str = datetime.now().strftime('%Y-%m-%d')
            archive_dir = os.path.join(app.config['ARCHIVE_IMG_DIR'], date_str)
            archive_path = os.path.join(archive_dir, file_name)

            if os.path.exists(archive_path):
                file_path = archive_path
            else:
                return jsonify({"error": "图片不存在"}), 404

        # 添加缓存控制头
        response = send_file(file_path)
        response.headers['Cache-Control'] = 'no-store, max-age=0'
        return response

    except Exception as e:
        logger.error(f"获取图片失败: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/list_archive')
def list_archive():
    """获取归档图片列表"""
    archive_data = []
    try:
        for root, dirs, files in os.walk(app.config['ARCHIVE_IMG_DIR']):
            if files:
                date = os.path.basename(root)
                archive_data.append({
                    "date": date,
                    "files": [{
                        "name": f,
                        "path": f"/get_image?path={f}&from_archive=true&date={date}",
                        "size": os.path.getsize(os.path.join(root, f))
                    } for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                })
        return jsonify(sorted(archive_data, key=lambda x: x['date'], reverse=True))
    except Exception as e:
        logger.error(f"获取归档列表失败: {str(e)}")
        return jsonify({"error": str(e)}), 500


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


def execute_plot_code(plot_code, df, original_filename):
    """执行绘图代码并返回所有生成的图片路径
    参数：
        plot_code: 生成的Python代码
        df: 要分析的数据框
        original_filename: 用户上传的原始文件名
    返回：
        list: 生成的图片路径列表
    """
    import matplotlib
    matplotlib.use('Agg')
    plt.close('all')

    # 创建临时工作目录
    temp_dir = tempfile.mkdtemp(dir=app.config['TEMP_IMG_DIR'])
    original_dir = os.getcwd()

    try:
        # 切换到临时目录
        os.chdir(temp_dir)
        logger.info(f"将在临时目录执行代码: {temp_dir}")

        # 将数据保存到临时目录供生成的代码使用
        temp_csv_path = os.path.join(temp_dir, original_filename)
        df.to_csv(temp_csv_path, index=False)

        # 修改生成的代码，使用正确的文件名
        plot_code = plot_code.replace("pd.read_csv('vgsales.csv')",
                                      f"pd.read_csv('{original_filename}')")

        # 准备执行环境
        exec_globals = {
            'pd': pd,
            'plt': plt,
            '__file__': os.path.join(temp_dir, 'generated_script.py')
        }

        # 执行生成的代码
        exec(plot_code, exec_globals)

        # 收集所有生成的PNG文件
        generated_images = []
        for f in os.listdir(temp_dir):
            if f.lower().endswith('.png'):
                img_path = os.path.join(temp_dir, f)
                generated_images.append(img_path)
                logger.info(f"检测到生成的图片: {img_path}")

        if not generated_images:
            raise FileNotFoundError("代码执行后未生成任何图片文件")

        return generated_images

    except Exception as e:
        logger.error(f"执行绘图代码时出错: {str(e)}")
        raise
    finally:
        # 恢复原始工作目录
        os.chdir(original_dir)
        plt.close('all')


def init_dirs():
    """初始化图片目录"""
    os.makedirs(app.config['TEMP_IMG_DIR'], exist_ok=True)
    os.makedirs(app.config['ARCHIVE_IMG_DIR'], exist_ok=True)


def clear_temp_images():
    """清空临时图片目录"""
    for filename in os.listdir(app.config['TEMP_IMG_DIR']):
        file_path = os.path.join(app.config['TEMP_IMG_DIR'], filename)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            logger.error(f"删除临时文件失败 {file_path}: {e}")


def archive_image(src_path):
    """归档图片到带日期的目录"""
    try:
        if not os.path.exists(src_path):
            raise FileNotFoundError(f"源图片不存在: {src_path}")

        date_str = datetime.now().strftime('%Y-%m-%d')
        filename = os.path.basename(src_path)
        archive_dir = os.path.join(app.config['ARCHIVE_IMG_DIR'], date_str)

        # 创建归档目录（按日期）
        os.makedirs(archive_dir, exist_ok=True)

        # 直接使用原文件名（不再添加时间戳）
        archive_path = os.path.join(archive_dir, filename)

        # 复制文件到归档目录
        shutil.copy2(src_path, archive_path)
        logger.info(f"图片归档成功: {src_path} -> {archive_path}")

        return archive_path

    except Exception as e:
        logger.error(f"图片归档失败: {str(e)}")
        raise


if __name__ == '__main__':
    app.run(debug=True)
