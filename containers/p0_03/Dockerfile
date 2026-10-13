ARG BASE=python@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134
FROM ${BASE}
COPY --chown=65532:65532 server.py /opt/fixture/server.py
USER 65532:65532
WORKDIR /tmp
ENTRYPOINT ["python", "-I", "-B", "/opt/fixture/server.py"]
