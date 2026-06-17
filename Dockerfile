FROM python:3.12-slim

WORKDIR /app

# 先装依赖，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再拷贝项目代码
COPY . .

# 监听端口：Render 运行时注入 $PORT；HF Spaces 用 7860
ENV PORT=7860
EXPOSE 7860

# shell 形式以便展开 ${PORT}
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-7860}
