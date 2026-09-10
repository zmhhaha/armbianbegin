ARG ES_VERSION=8.15.3
FROM docker.elastic.co/elasticsearch/elasticsearch:${ES_VERSION}
ARG ES_VERSION
ARG IK_SHA256
RUN test -n "$IK_SHA256" && \
    curl -fSL --retry 3 "https://release.infinilabs.com/analysis-ik/stable/elasticsearch-analysis-ik-${ES_VERSION}.zip" -o /tmp/ik.zip && \
    echo "$IK_SHA256  /tmp/ik.zip" | sha256sum -c - && \
    bin/elasticsearch-plugin install --batch file:///tmp/ik.zip && rm /tmp/ik.zip
COPY --chown=elasticsearch:root analysis/ /usr/share/elasticsearch/config/analysis-ik/
