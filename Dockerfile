FROM python:3.14-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libc6-dev zlib1g-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    apt-get purge -y gcc libc6-dev && \
    apt-get autoremove -y && \
    rm -rf /root/.cache/pip

RUN adduser --disabled-password --no-create-home --uid 1001 appuser

COPY . .

USER 1001

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import ssl,urllib.request; ctx=ssl.create_default_context(cafile='/certs/tls.crt'); ctx.check_hostname=False; urllib.request.urlopen('https://127.0.0.1:8000/health', context=ctx, timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--ssl-certfile", "/certs/tls.crt", "--ssl-keyfile", "/certs/tls.key"]
