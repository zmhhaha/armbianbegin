# docker build -t arm-cluster-master:5000/portal:latest .
# docker push arm-cluster-master:5000/portal:latest
FROM arm-cluster-master:5000/base:latest
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 && \
    rm -rf /var/lib/apt/lists/*
EXPOSE 8080
CMD ["python3", "-m", "http.server", "8080", "--directory", "/www"]
