ARG BASE_IMAGE=python:3.11-slim-bookworm
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/rkvoice HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
    XDG_CACHE_HOME=/tmp/.cache

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 libsndfile1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-container.txt /app/requirements-container.txt
# Curated installed-file closure from the tested ARM64 CPython 3.11 environment.
# It excludes host executables, editable installs, package RECORDs and bytecode.
# Each copied file and fixed distribution version has a receipt; no pip download.
COPY .image/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY .image/python-packages.json /app/python-packages.json

# All three inputs are separately verified by scripts/prepare_image.py.
# This library exists only in the image; no mount over host /usr/lib is needed.
COPY .image/runtime/librknnrt.so /usr/lib/librknnrt.so
RUN ldconfig
COPY .image/source/ /opt/rkvoice/
COPY .image/frontend/en_core_web_sm-3.8.0-py3-none-any.whl /tmp/en_core_web_sm-3.8.0-py3-none-any.whl
RUN python -m pip install --disable-pip-version-check --no-index --no-cache-dir --no-deps /tmp/en_core_web_sm-3.8.0-py3-none-any.whl \
    && python -m pip check \
    && python -c "import ctypes, numpy, spacy, onnxruntime, rknnlite; import rkvoice_stream.backends.tts.kokoro_convonly; ctypes.CDLL('/usr/lib/librknnrt.so')" \
    && test -x /usr/bin/mount && test -x /usr/bin/setpriv \
    && rm /tmp/en_core_web_sm-3.8.0-py3-none-any.whl

COPY .image/receipt.json /app/image-inputs.json
COPY speech_service/ /app/speech_service/
ARG SOURCE_REVISION
ARG BUILD_CREATED
LABEL org.opencontainers.image.title="RK3588 internal speech service" \
      org.opencontainers.image.source="https://github.com/zmhhaha/armbianbegin" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.created="${BUILD_CREATED}"
# RK3588 dma_heap devices on this node are root:root 0600. The pod runs as
# root; bootstrap drops every capability before starting the TTS process.
# The pod does not require privileged mode.
USER 0:0
EXPOSE 8092
ENTRYPOINT ["python", "-I", "-S", "/app/speech_service/container_bootstrap.py"]
CMD ["python", "-m", "speech_service", "--host", "0.0.0.0", "--port", "8092"]
