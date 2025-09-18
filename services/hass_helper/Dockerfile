FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY services/hass_helper/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements.txt

COPY services /app/services

EXPOSE 8000

CMD ["uvicorn", "services.hass_helper.app:app", "--host", "0.0.0.0", "--port", "8000"]
