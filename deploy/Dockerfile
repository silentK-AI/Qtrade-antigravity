FROM python:3.9-slim

WORKDIR /app

# 设置时区为中国上海时间 (CST / Asia/Shanghai) 确保交易时间点完全精确
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt || true

COPY . .

# 启动后台守护调度进程
CMD ["python", "daemon_scheduler.py", "--source", "live"]
