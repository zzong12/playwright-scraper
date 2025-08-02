FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /app

# 设置清华源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 复制应用代码
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 安装Playwright和浏览器
# RUN python -m playwright install
# RUN python -m playwright install-deps

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]