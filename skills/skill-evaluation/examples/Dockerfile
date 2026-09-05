FROM node:26.5.0-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN npm install --global @github/copilot@1.0.83

ENV CI=true
WORKDIR /workspace/repo
