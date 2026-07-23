FROM docker.io/searxng/searxng:latest

COPY settings.yml /etc/searxng/settings.yml
COPY entrypoint.sh /usr/local/bin/locreach-searxng-entrypoint.sh

USER root
RUN chmod +x /usr/local/bin/locreach-searxng-entrypoint.sh

# settings.yml defaults to localhost; cloud must listen on all interfaces.
ENV SEARXNG_BIND_ADDRESS=0.0.0.0
ENV SEARXNG_LIMITER=false

USER searxng
ENTRYPOINT ["/usr/local/bin/locreach-searxng-entrypoint.sh"]
