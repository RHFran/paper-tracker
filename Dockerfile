FROM python:3.12-slim

# zoneinfo uses the OS IANA database; SMTP/HTTPS require trusted CA roots.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 digest \
    && useradd --uid 10001 --gid digest --no-create-home --home-dir /data digest \
    && mkdir -p /app /data \
    && chown digest:digest /data

WORKDIR /app
COPY literature_digest/ /app/literature_digest/
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
VOLUME ["/data"]
ENTRYPOINT ["python", "-m", "literature_digest"]
CMD ["--help"]
