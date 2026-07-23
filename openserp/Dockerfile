FROM docker.io/karust/openserp:latest

# Render provides $PORT; local default is 7000.
ENTRYPOINT ["sh", "-c", "exec openserp serve -a 0.0.0.0 -p ${PORT:-7000}"]
