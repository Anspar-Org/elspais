ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    pandoc \
    texlive-xetex \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
