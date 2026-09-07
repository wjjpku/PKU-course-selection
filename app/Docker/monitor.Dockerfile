FROM python:3.10-slim

LABEL maintainer="you.siki@outlook.com"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY requirements.txt ./
RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r requirements.txt

COPY . ./

VOLUME ["/config"]

# The dashboard intentionally binds to loopback; use it locally instead of
# exposing credentials and session status through a published container port.
CMD ["python", "main.py", "--enable-election", "--with-monitor", "--config=/config/config.ini"]
