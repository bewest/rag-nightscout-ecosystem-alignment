# Client runtime for the M4 client-binary lab: node:22 (bash, curl) plus jq, which
# oref0's bin/ns-get.sh pipes its output through. The clients themselves are
# bind-mounted read-only from externals/ at run time; nothing is copied in.
FROM node:22
RUN apt-get update && apt-get install -y --no-install-recommends jq && rm -rf /var/lib/apt/lists/*
