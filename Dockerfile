FROM alpine:3.18
LABEL maintainer="Thomas GUIRRIEC <thomas@guirriec.fr>"
ENV UPTIME_ROBOT_EXPORTER_PORT=8123
ENV UPTIME_ROBOT_EXPORTER_LOGLEVEL='INFO'
ENV UPTIME_ROBOT_EXPORTER_NAME='uptime-robot-exporter'
ENV SCRIPT="uptime_robot_exporter.py"
ENV USERNAME="exporter"
ENV UID="1000"
ENV GID="1000"
COPY apk_packages /
COPY pip_packages /
ENV VIRTUAL_ENV="/uptime-robot-exporter"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
RUN xargs -a /apk_packages apk add --no-cache --update \
    && python3 -m venv ${VIRTUAL_ENV} \
    && pip install --no-cache-dir --no-dependencies --no-binary :all: -r pip_packages \
    && pip uninstall -y setuptools pip \
    && useradd -l -u ${UID} -U -s /bin/sh ${USERNAME} \
    && rm -rf \
        /root/.cache \
        /tmp/* \
        /var/cache/*
COPY --chown=${USERNAME}:${USERNAME} --chmod=500 ${SCRIPT} ${VIRTUAL_ENV}
COPY --chown=${USERNAME}:${USERNAME} --chmod=500 entrypoint.sh /
USER ${USERNAME}
WORKDIR ${VIRTUAL_ENV}
EXPOSE ${UPTIME_ROBOT_EXPORTER_PORT}
HEALTHCHECK CMD nc -vz localhost ${UPTIME_ROBOT_EXPORTER_PORT} || exit 1 # nosemgrep
ENTRYPOINT ["/entrypoint.sh"]
