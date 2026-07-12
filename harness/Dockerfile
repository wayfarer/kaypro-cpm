FROM debian:bookworm-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://github.com/MockbaTheBorg/RunCPM /tmp/RunCPM

RUN cd /tmp/RunCPM/RunCPM && make posix build


FROM debian:bookworm-slim

WORKDIR /cpm

COPY --from=builder /tmp/RunCPM/RunCPM/RunCPM ./RunCPM

COPY A/ ./A/
COPY B/ ./B/

CMD ["./RunCPM"]
