# BASE IMAGE: Use the latest Python 3.14 on a 'slim' Debian-based image.
# 'slim' is chosen to minimize the final image size while maintaining compatibility
# with the C-extensions required by our database drivers (like asyncpg).
FROM python:3.14-slim

# BUILD SYSTEM DEPENDENCIES: Install tools required to compile Python packages.
# gcc and libc-dev are necessary for binary extensions.
# --no-install-recommends keeps the image lean by avoiding unnecessary packages.
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libc6-dev zlib1g-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# DEPENDENCY MANAGEMENT: Copy requirements.txt first to take advantage of Docker's layer caching.
# This prevents re-installing all packages if only the application source code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    # LAYER OPTIMIZATION: Remove compilers and temporary files after building dependencies.
    # This significantly reduces the final image size and minimizes the security attack surface.
    apt-get purge -y gcc libc6-dev && \
    apt-get autoremove -y && \
    rm -rf /root/.cache/pip

# CONTAINER SECURITY: Create a dedicated non-root user (appuser).
# UID 1001 is used to avoid conflicts with common host users.
# Running as non-root is a critical security best practice to prevent container breakout.
RUN adduser --disabled-password --no-create-home --uid 1001 appuser

# PROJECT FILES: Copy the entire application source code into the container.
COPY . .

# PRIVILEGE DROP: Switch from root to the non-privileged user for runtime.
USER 1001

# INTERNAL HEALTHCHECK: Verifies that the FastAPI application is alive and responding.
# Since 'slim' images lack 'curl', we use a built-in Python script for the check.
# Logic: It creates a custom SSL context to handle our internal TLS certificates (cafile='/certs/tls.crt')
# and performs a secure HTTPS request to the local health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import ssl,urllib.request; ctx=ssl.create_default_context(cafile='/certs/tls.crt'); ctx.check_hostname=False; urllib.request.urlopen('https://127.0.0.1:8000/health', context=ctx, timeout=3)" || exit 1

# RUNTIME ENTRYPOINT: Launches the application using the Uvicorn ASGI server.
# --ssl-certfile and --ssl-keyfile: Enables mandatory encryption for all API traffic (TLS).
# --host 0.0.0.0: Binds the server to all network interfaces inside the container.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--ssl-certfile", "/certs/tls.crt", "--ssl-keyfile", "/certs/tls.key"]
