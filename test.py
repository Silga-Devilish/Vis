import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
# 读取CSV文件
plt.rcParams['font.sans-serif'] = ['SimHei']  # 或 ['Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
file_path = 'data.csv'
df = pd.read_csv(file_path)

# 过滤2017年的数据
df = df[df['Year'] == 2017]

# 提取需要的列
df = df[['Region', 'Total alcohol consumption (in liters of pure alcohol per capita)']]

# 按地区分组并求总酒精销量
regions = df.groupby('Region')['Total alcohol consumption (in liters of pure alcohol per capita)'].sum()

# 绘制柱状图
plt.figure(figsize=(10, 6))
regions.plot(kind='bar', title='2017年全年酒精销量（升纯醇/人）')
plt.show()