FROM debian:bookworm-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Upstream has no release tags, so we pin by commit SHA. Keep in sync with
# RUNCPM_REF in harness/build_runcpm.sh.
ARG RUNCPM_REF=1c19a8baa073ecf746d6501cc28239d139b809d7

# A shallow clone can't check out an arbitrary SHA; fetch the pinned commit directly.
RUN git init /tmp/RunCPM \
  && git -C /tmp/RunCPM remote add origin https://github.com/MockbaTheBorg/RunCPM \
  && git -C /tmp/RunCPM fetch --depth 1 origin "$RUNCPM_REF" \
  && git -C /tmp/RunCPM checkout FETCH_HEAD

# Local patches (serial/modem bridge). The build context is a machine dir, so
# the Makefile passes harness/patches as a named context:
#   docker build --build-context patches=harness/patches ...
# --check first so drift against a bumped RUNCPM_REF fails the build. Keep in
# sync with the same step in harness/build_runcpm.sh.
COPY --from=patches . /tmp/patches/
RUN for p in /tmp/patches/*.patch; do \
      git -C /tmp/RunCPM apply --check "$p" && git -C /tmp/RunCPM apply "$p"; \
    done

RUN cd /tmp/RunCPM/RunCPM && make posix build


FROM debian:bookworm-slim

WORKDIR /cpm

COPY --from=builder /tmp/RunCPM/RunCPM/RunCPM ./RunCPM

# Copy the whole machine directory (the build context): drive letters may be
# plain directories or symlinks into real stores, and COPY of a symlink does
# not dereference it — copying everything keeps relative links resolvable.
# The machine's .dockerignore keeps non-drive files out.
COPY . ./

CMD ["./RunCPM"]
