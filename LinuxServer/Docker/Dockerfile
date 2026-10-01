FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DH_PYTHON=/opt/venv/bin/python3 \
    DH_SERVER_USER=dhgame \
    DH_LINUX_ROOT=/server

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libstdc++6 libgcc-s1 libcurl4 passwd util-linux \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin dhgame

WORKDIR /server
COPY requirements-linux.txt .
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/python3 -m pip install --no-cache-dir -r requirements-linux.txt

COPY app/ /opt/toolkit/app/
COPY config/ /opt/toolkit/config/
COPY DreadHungerServer.sh /opt/toolkit/
COPY LICENSE /opt/toolkit/
ENTRYPOINT ["/opt/venv/bin/python3", "/opt/toolkit/app/docker_entrypoint.py"]
