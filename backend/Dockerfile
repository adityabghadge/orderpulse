# ---- dependencies (cached until pyproject.toml changes) --------------------------------------
FROM python:3.13-slim AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml ./

# CPU-only PyTorch: the default Linux build bundles gigabytes of GPU libraries we don't use.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu \
 && python -c "import tomllib; p = tomllib.load(open('pyproject.toml', 'rb'))['project']; \
print('\n'.join(p['dependencies'] + p['optional-dependencies']['demo']))" > requirements.txt \
 && pip install -r requirements.txt

# ---- application -----------------------------------------------------------------------------
FROM deps AS runtime

RUN useradd --create-home --uid 10001 orderpulse \
 && mkdir -p /app/artifacts \
 && chown orderpulse /app/artifacts

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
# Make the code readable by the app user no matter what permissions the files had on the host.
RUN chmod -R a+rX /app

USER orderpulse
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live', timeout=2)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
