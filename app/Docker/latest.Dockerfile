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

# A live election remains explicit even inside the purpose-built image.
CMD ["python", "main.py", "--enable-election", "--config=/config/config.ini"]
