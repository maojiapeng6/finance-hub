FROM python:3.12-alpine

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

WORKDIR /app

COPY server.py config.json sources_catalog.json ./
COPY static ./static

EXPOSE 6789

HEALTHCHECK --interval=60s --timeout=8s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:6789/api/status', timeout=5)" || exit 1

CMD ["python", "server.py"]
