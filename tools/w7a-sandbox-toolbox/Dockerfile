# syntax=docker/dockerfile:1@sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32

FROM alpine:3.20@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc

ARG AIOA_SOURCE_COMMIT

LABEL org.opencontainers.image.title="AIOA W7A sandbox toolbox" \
      org.opencontainers.image.description="Credentialless non-root Python/Node coding toolbox" \
      org.opencontainers.image.revision="${AIOA_SOURCE_COMMIT}" \
      dev.aioa.sandbox.policy="DOCKER_SANDBOX_V1"

RUN apk add --no-cache \
        git=2.45.4-r0 \
        nodejs=20.15.1-r0 \
        npm=10.9.1-r0 \
        py3-pip=24.0-r2 \
        py3-pytest=8.2.2-r0 \
        python3=3.12.13-r0 \
        ripgrep=14.1.0-r0

RUN install -d -m 0755 /opt/aioa-cache/python /opt/aioa-cache/npm \
    && python3 -m pip download \
        --disable-pip-version-check \
        --no-deps \
        --only-binary=:all: \
        --dest /opt/aioa-cache/python \
        six==1.17.0 \
    && echo "4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274  /opt/aioa-cache/python/six-1.17.0-py2.py3-none-any.whl" \
        | sha256sum -c -

RUN cd /tmp \
    && npm pack --ignore-scripts --silent is-number@7.0.0 > /tmp/aioa-npm-artifact \
    && echo "7b75c1057198cf97696909a9bee176c9c5e9bcb5b03bf3ecef2f484defadd51e  /tmp/is-number-7.0.0.tgz" \
        | sha256sum -c - \
    && npm cache add \
        --cache=/opt/aioa-cache/npm \
        --ignore-scripts \
        /tmp/is-number-7.0.0.tgz \
    && rm /tmp/aioa-npm-artifact /tmp/is-number-7.0.0.tgz

COPY workspace_probe.py /usr/local/bin/aioa-workspace-probe
COPY atomic_write.py /usr/local/bin/aioa-atomic-write
COPY read_file.py /usr/local/bin/aioa-read-file
COPY runtime_probe.py /usr/local/bin/aioa-runtime-probe

RUN chmod 0555 \
        /usr/local/bin/aioa-workspace-probe \
        /usr/local/bin/aioa-atomic-write \
        /usr/local/bin/aioa-read-file \
        /usr/local/bin/aioa-runtime-probe \
    && ln -s /usr/bin/python3 /usr/local/bin/python \
    && chmod -R a-w /opt/aioa-cache \
    && install -d -o 65532 -g 65532 -m 0700 /workspace

USER 65532:65532
WORKDIR /workspace

CMD ["python3", "--version"]
