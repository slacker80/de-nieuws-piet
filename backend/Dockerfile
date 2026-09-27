# Nieuws Piet backend — FastAPI + SQLite (taken 2.3/2.4).
#
# Afhankelijkheden: backend/requirements.txt (gepind, ongewijzigd).
# Data: /app/data is het mountpunt van de named volume `nieuws_piet_sqlite_data`;
#       de database staat op /app/data/news.db.
# Startopdracht: uvicorn op `app.main:app` — de FastAPI-applicatie zelf volgt in
#       sectie 4; deze scaffolding levert de build- en run-opzet van taak 2.3.

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Mountpunt voor de SQLite named volume (taak 2.4); de volume zelf overschrijft dit.
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
