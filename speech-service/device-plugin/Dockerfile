FROM scratch
ARG SOURCE_REVISION
ARG BUILD_CREATED
LABEL org.opencontainers.image.title="RK3588 generic device plugin" \
      org.opencontainers.image.source="https://github.com/squat/generic-device-plugin" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.created="${BUILD_CREATED}"
COPY generic-device-plugin /generic-device-plugin
COPY LICENSE /LICENSE
USER 0:0
ENTRYPOINT ["/generic-device-plugin"]
