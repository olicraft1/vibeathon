FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY charlaviva/ charlaviva/
COPY web/ web/
COPY samples/ samples/
COPY pyproject.toml README.md LICENSE ./

EXPOSE 8000
# serve --demo boots with the two bundled sample stages; use `serve` in prod
CMD ["python", "-m", "charlaviva", "serve", "--host", "0.0.0.0", "--port", "8000"]
