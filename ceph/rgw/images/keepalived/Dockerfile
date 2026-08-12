FROM alpine:3.20

RUN apk add --no-cache bash ca-certificates curl keepalived \
    && mkdir -p /etc/keepalived /var/lib /var/run/keepalived

COPY init.sh /init.sh
RUN chmod 0755 /init.sh

CMD ["/init.sh"]
