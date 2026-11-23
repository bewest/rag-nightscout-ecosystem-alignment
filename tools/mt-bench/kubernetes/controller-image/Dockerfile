# Campaign controller image: the harness checkout, Python, kubectl, git, and (standard runner) the template case, its
# tools, node, k6 and the core/deploy checkouts at the workstation paths the template records. Built by build.sh,
# which assembles the context; nothing here reaches the network except the apt install of git.
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
COPY kubectl /usr/local/bin/kubectl
RUN useradd --uid 10001 --create-home controller
# The template's inputs are private (0600/0700) on the workstation; the controller (uid 10001) must own them.
COPY --chown=10001:10001 harness /opt/harness
RUN ln -s /opt/harness/tools/mt-bench/kubernetes /app && git config --system --add safe.directory '*' \
 && mkdir -p /work && chown 10001 /work
COPY --chown=10001:10001 ws/ /
USER 10001
WORKDIR /work
