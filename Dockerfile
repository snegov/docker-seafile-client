FROM debian:bookworm-slim

# Install seafile client
RUN apt-get update && \
    apt-get install gnupg curl python3.11-venv -y && \
    rm -rf /var/lib/apt/lists/*
RUN curl https://linux-clients.seafile.com/seafile.asc | apt-key add - && \
    echo 'deb [arch=amd64] https://linux-clients.seafile.com/seafile-deb/bookworm/ stable main' \
    > /etc/apt/sources.list.d/seafile.list && \
    apt-get update -y && \
    apt-get install -y seafile-cli && \
    rm -rf /var/lib/apt/lists/*

# Use virtual environment
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv --system-site-packages $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install app requirements
WORKDIR /dsc
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY dsc ./dsc/
COPY start.py ./start.py

# Create seafile user and init seafile client
RUN chmod +x /dsc/start.py && \
    useradd -U -d /dsc -s /bin/bash seafile && \
    usermod -G users seafile && \
    mkdir -p /dsc/seafile-data && \
    chown seafile:seafile -R /dsc

VOLUME /dsc/seafile-data
CMD ["./start.py"]
