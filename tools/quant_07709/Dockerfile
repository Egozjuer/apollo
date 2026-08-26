FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HOST=0.0.0.0 \
    PORT=8770

WORKDIR /app

# Keep the original package path: tools.quant_07709
COPY . /app/tools/quant_07709/
RUN printf '' > /app/tools/__init__.py

EXPOSE 8770

HEALTHCHECK --interval=30s --timeout=8s --start-period=15s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8770/api/health', timeout=5)"

CMD ["python3", "-m", "tools.quant_07709.app", "--host", "0.0.0.0", "--port", "8770"]
