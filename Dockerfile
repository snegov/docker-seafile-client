FROM python:3-slim

RUN apt-get update && apt-get install gnupg -y && rm -rf /var/lib/apt/lists/*
RUN apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys 8756C4F765C9AC3CB6B85D62379CE192D401AB61 && \
    echo deb http://deb.seadrive.org buster main | tee /etc/apt/sources.list.d/seafile.list && \
    apt-get update -y && \
    apt-get install -y seafile-cli procps curl grep && \
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

CMD ["./start.py"]
