FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright ESTATE_DATA_DIR=/var/lib/estate
WORKDIR /app
COPY requirements-service.lock ./
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 xvfb xauth \
    && pip install --no-cache-dir -r requirements-service.lock \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 estate && useradd --uid 10001 --gid estate --create-home estate \
    && mkdir -p /var/lib/estate && chown estate:estate /var/lib/estate \
    && chmod -R a+rX /opt/playwright
COPY estate ./estate
COPY config ./config
COPY deploy/entrypoint.sh /usr/local/bin/estate-entrypoint
RUN chmod 755 /usr/local/bin/estate-entrypoint
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["estate-entrypoint"]
CMD ["api"]
