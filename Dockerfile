FROM python:3.12 AS requirements_stage

WORKDIR /wheel

RUN python -m pip install --user uv

COPY ./pyproject.toml \
  ./uv.lock \
  /wheel/

RUN python -m uv export --format requirements.txt --output-file requirements.txt --no-hashes

RUN python -m pip wheel --wheel-dir=/wheel --no-cache-dir --requirement ./requirements.txt

RUN python -m uv tool run --no-cache --from nb-cli nb generate -f /tmp/bot.py


FROM node:22-bookworm-slim AS node_runtime


FROM python:3.12-slim-bookworm

WORKDIR /app

ENV TZ=Asia/Shanghai \
    PYTHONPATH=/app \
    APP_MODULE=_main:app \
    MAX_WORKERS=1 \
    DEBIAN_FRONTEND=noninteractive \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY ./docker/gunicorn_conf.py ./docker/start.sh /
RUN chmod +x /start.sh

COPY --from=requirements_stage /tmp/bot.py /app
COPY ./docker/_main.py /app
COPY --from=requirements_stage /wheel /wheel
COPY --from=node_runtime /usr/local/ /usr/local/

# Offline install from prebuilt wheels, then gunicorn (not in project deps) + Chromium
RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg \
  && pip install --no-cache-dir --no-index --find-links=/wheel -r /wheel/requirements.txt \
  && pip install --no-cache-dir gunicorn \
  && node -e "process.exit(Number(process.versions.node.split('.')[0]) < 22)" \
  && python -c "import yt_dlp_ejs" \
  && rm -rf /wheel \
  && playwright install --with-deps chromium \
  && rm -rf /var/lib/apt/lists/*

COPY . /app/

CMD ["/start.sh"]
