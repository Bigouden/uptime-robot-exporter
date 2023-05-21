# Uptime Robot Exporter

## Quick Start

```bash
DOCKER_BUILDKIT=1 docker build -t uptime-robot-exporter .
docker run -dit --name uptime-robot-exporter --env UPTIME_ROBOT_API_KEY=xxx
```

## Metrics

```bash
# HELP uptime_robot_status Uptime Robot Status
# TYPE uptime_robot_status gauge
uptime_robot_status{create_datetime="1684600296",friendly_name="Google",id="xxx",interval="300",job="uptime-robot-exporter",status="2",timeout="30",type="1",url="https://www.google.fr"} 2.0
```
