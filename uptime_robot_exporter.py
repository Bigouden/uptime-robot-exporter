#!/usr/bin/env python3
# coding: utf-8
# pyright: reportMissingImports=false

"""Uptime Robot Exporter"""

import logging
import os
import sys
import threading
import time
import warnings
from datetime import datetime
from typing import Callable
from wsgiref.simple_server import make_server

import pytz
import requests
from prometheus_client import PLATFORM_COLLECTOR, PROCESS_COLLECTOR
from prometheus_client.core import REGISTRY, CollectorRegistry, Metric
from prometheus_client.exposition import _bake_output, _SilentHandler, parse_qs

# Ignore Ansible Warning
warnings.filterwarnings("ignore")

UPTIME_ROBOT_EXPORTER_NAME = os.environ.get(
    "UPTIME_ROBOT_EXPORTER_NAME", "uptime-robot-exporter"
)
UPTIME_ROBOT_EXPORTER_LOGLEVEL = os.environ.get(
    "UPTIME_ROBOT_EXPORTER_LOGLEVEL", "INFO"
).upper()
UPTIME_ROBOT_EXPORTER_TZ = os.environ.get("TZ", "Europe/Paris")
UPTIME_ROBOT_API_KEY = os.environ.get("UPTIME_ROBOT_API_KEY")

MANDATORY_ENV_VARS = ["UPTIME_ROBOT_API_KEY"]


def make_wsgi_app(
    registry: CollectorRegistry = REGISTRY, disable_compression: bool = False
) -> Callable:
    """Create a WSGI app which serves the metrics from a registry."""

    def prometheus_app(environ, start_response):
        # Prepare parameters
        accept_header = environ.get("HTTP_ACCEPT")
        accept_encoding_header = environ.get("HTTP_ACCEPT_ENCODING")
        params = parse_qs(environ.get("QUERY_STRING", ""))
        headers = [
            ("Server", ""),
            ("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0"),
            ("Pragma", "no-cache"),
            ("Expires", "0"),
            ("X-Content-Type-Options", "nosniff"),
        ]
        if environ["PATH_INFO"] == "/":
            status = "301 Moved Permanently"
            headers.append(("Location", "/metrics"))
            output = b""
        elif environ["PATH_INFO"] == "/favicon.ico":
            status = "200 OK"
            output = b""
        elif environ["PATH_INFO"] == "/metrics":
            status, tmp_headers, output = _bake_output(
                registry,
                accept_header,
                accept_encoding_header,
                params,
                disable_compression,
            )
            headers += tmp_headers
        else:
            status = "404 Not Found"
            output = b""
        start_response(status, headers)
        return [output]

    return prometheus_app


def start_wsgi_server(
    port: int,
    addr: str = "0.0.0.0",  # nosec B104
    registry: CollectorRegistry = REGISTRY,
) -> None:
    """Starts a WSGI server for prometheus metrics as a daemon thread."""
    app = make_wsgi_app(registry)
    httpd = make_server(addr, port, app, handler_class=_SilentHandler)
    thread = threading.Thread(target=httpd.serve_forever)
    thread.daemon = True
    thread.start()


start_http_server = start_wsgi_server


# Logging Configuration
try:
    pytz.timezone(UPTIME_ROBOT_EXPORTER_TZ)
    logging.Formatter.converter = lambda *args: datetime.now(
        tz=pytz.timezone(UPTIME_ROBOT_EXPORTER_TZ)
    ).timetuple()
    logging.basicConfig(
        stream=sys.stdout,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%d/%m/%Y %H:%M:%S",
        level=UPTIME_ROBOT_EXPORTER_LOGLEVEL,
    )
except pytz.exceptions.UnknownTimeZoneError:
    logging.Formatter.converter = lambda *args: datetime.now(
        tz=pytz.timezone("Europe/Paris")
    ).timetuple()
    logging.basicConfig(
        stream=sys.stdout,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%d/%m/%Y %H:%M:%S",
        level="INFO",
    )
    logging.error("TZ invalid : %s !", UPTIME_ROBOT_EXPORTER_TZ)
    os._exit(1)
except ValueError:
    logging.basicConfig(
        stream=sys.stdout,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%d/%m/%Y %H:%M:%S",
        level="INFO",
    )
    logging.error("UPTIME_ROBOT_EXPORTER_LOGLEVEL invalid !")
    os._exit(1)

# Check Mandatory Environment Variable
for var in MANDATORY_ENV_VARS:
    if var not in os.environ:
        logging.critical("%s environment variable must be set !", var)
        os._exit(1)

# Check UPTIME_ROBOT_EXPORTER_PORT
try:
    UPTIME_ROBOT_EXPORTER_PORT = int(
        os.environ.get("UPTIME_ROBOT_EXPORTER_PORT", "8123")
    )
except ValueError:
    logging.error("UPTIME_ROBOT_EXPORTER_PORT must be int !")
    os._exit(1)

METRICS = [
    {
        "name": "status",
        "description": "Uptime Robot Status",
        "type": "gauge",
    },
    {
        "name": "response_times",
        "description": "Uptime Robot Response Time",
        "type": "gauge",
    },
]

# REGISTRY Configuration
REGISTRY.unregister(PROCESS_COLLECTOR)
REGISTRY.unregister(PLATFORM_COLLECTOR)
REGISTRY.unregister(REGISTRY._names_to_collectors["python_gc_objects_collected_total"])


class UptimeRobotCollector:
    """UptimeRobot Collector Class"""

    def __init__(self):
        pass

    @staticmethod
    def _get_monitors():
        url = "https://api.uptimerobot.com/v2/getMonitors"
        payload = (
            f"api_key={UPTIME_ROBOT_API_KEY}"
            f"&format=json"
            f"&response_times=1"
            f"&response_times_limit=1"
            f"&response_times_average=0"
        )
        headers = {
            "content-type": "application/x-www-form-urlencoded",
            "cache-control": "no-cache",
        }
        res = requests.request("POST", url, data=payload, headers=headers)
        if res.status_code != 200:
            logging.error("Invalid HTTP Status Code : %s", res.status_code)
            os._exit(1)
        if res.json()["stat"] == "ok":
            return res.json()
        if res.json()["stat"] == "fail":
            logging.error("Uptime Robot Error : %s", res.json()["error"]["message"])
            os._exit(1)
        else:
            logging.error("Uptime Robot Unknown Error")
            os._exit(1)

    def get_metrics(self):
        """Retrieve Prometheus Metrics"""
        metrics = []
        for monitor in self._get_monitors()["monitors"]:
            metric_labels = {
                k: str(v)
                for k, v in monitor.items()
                if v
                and v is not None
                and k not in [metric["name"] for metric in METRICS]
                and k != "average_response_time"
            }

            for key, value in monitor.items():
                if key in [metric["name"] for metric in METRICS]:
                    metric_name = f"uptime_robot_{key}"
                    metric_description = [
                        metric["description"]
                        for metric in METRICS
                        if key == metric["name"]
                    ][0]
                    metric_type = [
                        metric["type"] for metric in METRICS if key == metric["name"]
                    ][0]
                    if key == "response_times":
                        metric_name = "uptime_robot_response_time"
                        metric_value = value[0]["value"]
                    else:
                        metric_value = value

                    metrics.append(
                        {
                            "name": metric_name,
                            "description": metric_description,
                            "type": metric_type,
                            "labels": metric_labels,
                            "value": metric_value,
                        }
                    )
        logging.info("Metrics : %s", metrics)
        return metrics

    def collect(self):
        """Collect Prometheus Metrics"""
        metrics = self.get_metrics()
        for metric in metrics:
            labels = {"job": UPTIME_ROBOT_EXPORTER_NAME}
            labels |= metric["labels"]
            prometheus_metric = Metric(
                metric["name"], metric["description"], metric["type"]
            )
            prometheus_metric.add_sample(
                metric["name"], value=metric["value"], labels=labels
            )
            yield prometheus_metric


def main():
    """Main Function"""
    logging.info(
        "Starting Uptime Robot Exporter on port %s.", UPTIME_ROBOT_EXPORTER_PORT
    )
    logging.debug("UPTIME_ROBOT_EXPORTER_PORT: %s.", UPTIME_ROBOT_EXPORTER_PORT)
    logging.debug("UPTIME_ROBOT_EXPORTER_NAME: %s.", UPTIME_ROBOT_EXPORTER_NAME)
    UptimeRobotCollector()
    # Start Prometheus HTTP Server
    start_http_server(UPTIME_ROBOT_EXPORTER_PORT)
    # Init AnsibleCollector
    REGISTRY.register(UptimeRobotCollector())
    # Infinite Loop
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
