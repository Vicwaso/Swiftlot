FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
RUN useradd --create-home app && mkdir -p /app/storage /app/staticfiles && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["waitress-serve", "--listen=0.0.0.0:8000", "--threads=8", "config.wsgi:application"]
