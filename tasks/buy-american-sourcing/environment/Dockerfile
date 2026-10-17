FROM python:3.13-slim-bookworm@sha256:a1165e272e578941b84abc79e4ab38a0305cd12803a5c4247979ac7655f4d641

RUN pip install --no-cache-dir \
    numpy==2.5.3 \
    pandas==3.0.6 \
    python-dateutil==2.9.0.post0 \
    six==1.17.0 \
    scipy==1.18.1 \
    ortools==9.15.6755 \
    absl-py==2.5.0 \
    protobuf==6.33.6 \
    immutabledict==4.3.1 \
    typing_extensions==4.16.0

WORKDIR /app
COPY data /app/data
RUN mkdir -p /app/output
