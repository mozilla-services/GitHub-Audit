FROM python:3.7

RUN mkdir -p /app
WORKDIR /app

RUN pip install poetry

COPY . /app/

RUN poetry install

CMD ./produce-report.sh
