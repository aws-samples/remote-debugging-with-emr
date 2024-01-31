# It's important this be the same platform and architecture as your EMR environment
FROM --platform=linux/amd64 amazonlinux:2 AS base

RUN yum install -y python3 tar gzip

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN python3 -m pip install --upgrade pip

ENV PATH="$PATH:/root/.local/bin"

RUN python3 -m pip install venv-pack==0.2.0 pydevd-pycharm~=233.13763.11
RUN mkdir /output && venv-pack -o /output/pyspark_deps.tar.gz

# Export stage - used to copy packaged venv to local filesystem
# docker build --output dist .
FROM scratch AS export-python
COPY --from=base /output/pyspark_deps.tar.gz /