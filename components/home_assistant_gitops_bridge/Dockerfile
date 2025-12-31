ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache \
    git \
    openssh-client \
    python3 \
    py3-pip

RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    httpx==0.27.2 \
    pydantic==2.9.2 \
    uvicorn==0.31.1 \
    watchdog==5.0.3

COPY rootfs /

EXPOSE 8099
