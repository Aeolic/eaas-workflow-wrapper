#syntax=docker/dockerfile:1

FROM python:3.8-slim-buster

USER root
WORKDIR /app

RUN mkdir /app/output
RUN mkdir /app/logs

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY wrapper.py wrapper.py

# CMD ["python3", "wrapper.py", "envID", "input1.txt", "input2.txt"]

