# API Note de tête, lancée par le compose.yaml de l'application.
# Python 3.12 comme la CI (.github/workflows/pipeline.yml).
FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# Dépendances d'abord : la couche reste en cache tant que requirements.txt ne bouge pas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# L'API ne lit que le GOLD et le MART, déjà calculés et versionnés par pipeline.py
COPY src/ src/
COPY data/03_gold/ data/03_gold/
COPY data/04_mart/ data/04_mart/

USER nobody
EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"]

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
