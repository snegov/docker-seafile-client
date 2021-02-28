FROM python:3-slim

RUN apt-get update && apt-get install gnupg curl -y && rm -rf /var/lib/apt/lists/*
RUN curl https://linux-clients.seafile.com/seafile.asc | apt-key add - && \
    echo 'deb [arch=amd64] https://linux-clients.seafile.com/seafile-deb/buster/ stable main' > /etc/apt/sources.list.d/seafile.list && \
    apt-get update -y && \
    apt-get install -y seafile-cli procps grep && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /seafile-client
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY seafile_client ./seafile_client/
COPY start.py ./start.py

RUN chmod +x /seafile-client/start.py && \
    useradd -U -d /seafile-client -s /bin/bash seafile && \
    usermod -G users seafile && \
    chown seafile:seafile -R /seafile-client && \
    su - seafile -c "seaf-cli init -d /seafile-client"

VOLUME /seafile-client/seafile-data

CMD ["./start.py"]
