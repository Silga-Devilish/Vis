
import pandas as pd
import json

def analyze_csv(file_path):
    """
    分析 CSV 文件，提取数据结构并生成 LLM 可理解的 JSON 摘要。
    参数：
        file_path (str): CSV 文件路径
    返回：
        tuple: (DataFrame, str) - 原始数据和 JSON 格式的摘要
    """
    # 1. 读取 CSV 文件
    try:
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        print(f"错误：找不到文件 '{file_path}'")
        return None, None
    except Exception as e:
        print(f"错误：无法读取 CSV 文件 '{file_path}'，原因：{e}")
        return None, None

    # 2. 分析列类型
    columns = []
    for col in df.columns:
        col_type = 'unknown'
        unique_values = None

        # 判断列类型
        if pd.api.types.is_numeric_dtype(df[col]):
            col_type = 'numeric'
        elif pd.api.types.is_datetime64_any_dtype(df[col]) or pd.to_datetime(df[col], errors='coerce').notna().sum() > len(df) / 2:
            col_type = 'date'
        else:
            col_type = 'category'
            # 获取类别列的前 5 个唯一值
            unique_values = list(df[col].dropna().unique())[:5]

        columns.append({
            'name': col,
            'type': col_type,
            'unique_values': unique_values
        })

    # 3. 生成分组信息
    summary = {'columns': columns, 'rows': len(df)}
    if any(col['type'] == 'date' for col in columns):
        date_col = next(col['name'] for col in columns if col['type'] == 'date')
        # 按日期分组统计行数
        grouped = df.groupby(date_col).size().to_dict()
        summary['grouped'] = {str(k): v for k, v in grouped.items()}
    elif any(col['type'] == 'category' for col in columns):
        cat_col = next(col['name'] for col in columns if col['type'] == 'category')
        # 按类别分组统计行数
        summary['grouped'] = df.groupby(cat_col).size().to_dict()

    # 4. 转换为 JSON 摘要
    json_summary = json.dumps(summary, ensure_ascii=False, indent=2)

    return df, json_summary

def main():
    """
    主函数，测试 CSV 分析功能并导出结果。
    """
    # 指定 CSV 文件路径
    csv_file = "C:/Users/nizhijie/Desktop/可视化/可视化大作业/csv文件的结构提取/Consumption of alcoholic beverages in Russia 2017-2023.csv"  # 替换为实际路径
    df, json_summary = analyze_csv(csv_file)

    if df is not None and json_summary is not None:
        print("CSV 数据结构摘要：")
        print(json_summary)
        print("\n原始数据预览：")
        print(df.head())

        # 导出结果到 TXT 文件
        try:
            with open('csv_structure_summary.txt', 'w', encoding='utf-8') as f:
                f.write("CSV 数据结构摘要：\n")
                f.write(json_summary)
                f.write("\n\n原始数据预览：\n")
                f.write(df.head().to_string())
            print("分析结果已导出到 'csv_structure_summary.txt'")
        except Exception as e:
            print(f"错误：无法导出到 TXT 文件，原因：{e}")

if __name__ == "__main__":
    main()

