# Campaign controller image: the harness checkout, Python, kubectl, git, and (standard runner) the template case, its
# tools, node, k6 and the core/deploy checkouts at the workstation paths the template records. Built by build.sh,
# which assembles the context; nothing here reaches the network except the apt install of git.
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
COPY kubectl /usr/local/bin/kubectl
COPY harness /opt/harness
RUN ln -s /opt/harness/tools/mt-bench/kubernetes /app && git config --system --add safe.directory '*' \
 && useradd --uid 10001 --create-home controller && mkdir -p /work && chown 10001 /work
COPY ws/ /
USER 10001
WORKDIR /work
