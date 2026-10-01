# --- Stage 1: build the Tailwind stylesheet ---------------------------------
FROM node:22-alpine AS css
WORKDIR /build
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY tailwind.config.js ./
COPY static_src ./static_src
COPY templates ./templates
COPY apps ./apps
COPY static/js ./static/js
RUN npx tailwindcss -c tailwind.config.js -i static_src/input.css -o static/css/app.css --minify

# --- Stage 2: the Django app ---------------------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=css /build/static/css/app.css static/css/app.css
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
EXPOSE 8000
# Production: run `python manage.py collectstatic --noinput` at release time, then:
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
