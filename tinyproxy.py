from hashlib import md5
import time

from checks import AgentCheck
import requests
from requests.exceptions import Timeout

DEFAULT_HOST = "localhost"
DEFAULT_PORT = "8888"
DEFAULT_STATHOST = "tinyproxy.stats"
DEFAULT_TIMEOUT = 1.0  # seconds


class TinyproxyCheck(AgentCheck):
    def check(self, instance):
        self.host = instance.get("host", DEFAULT_HOST)
        self.port = int(instance.get("port", DEFAULT_PORT))
        self.stathost = instance.get("stathost", DEFAULT_STATHOST)
        self.timeout = float(instance.get('timeout', DEFAULT_TIMEOUT))

        self.url = "http://{}:{}".format(self.host, self.port)
        self.version = None
        self.aggregation_key = None

        resp = None
        start_time = time.time()
        try:
            resp = requests.get(self.url, headers={"Host": self.stathost}, timeout=self.timeout)
            end_time = time.time()
        except Timeout as e:
            msg = '{} timed out after {} seconds.'.format(self.url, self.timeout)
            return self.report_error("HTTP timeout", msg)
        except:
            msg = 'Unable to connect to {}.'.format(self.url)
            return self.report_error("HTTP timeout", msg)

        if not resp.ok:
            msg = '{} returned a status of {}'.format(self.url, resp.status_code)
            return self.report_error('Invalid HTTP response code', msg)

        try:
            data = resp.json()
        except:
            msg = '{} response was not well-formed JSON: {}'.format(self.url, resp.text)
            return self.report_error("JSON parse error", msg)

        if data.get('version'):
            self.version = data['version']

        self.report_ok()
        self.record_gauge("tinyproxy.response_time", end_time - start_time)  # reports in seconds
        self.record_gauge("tinyproxy.opens", int(data.get("opens")))
        self.record_monotonic_count("tinyproxy.reqs", int(data.get("reqs")))
        self.record_monotonic_count("tinyproxy.badconns", int(data.get("badconns")))
        self.record_monotonic_count("tinyproxy.deniedconns", int(data.get("deniedconns")))
        self.record_monotonic_count("tinyproxy.refusedconns", int(data.get("refusedconns")))

    def record_gauge(self, metric, value):
        return self.gauge(metric, value, tags=self.get_tags())

    def record_monotonic_count(self, metric, value):
        return self.monotonic_count(metric, value, tags=self.get_tags())

    def report_ok(self):
        return self.service_check("tinyproxy", AgentCheck.OK, tags=self.get_tags())

    def report_error(self, msg_title, msg_text):
        tags = self.get_tags()
        self.service_check("tinyproxy", AgentCheck.CRITICAL, tags=self.get_tags(), message=msg_title)
        if self.aggregation_key is None:
            aggregation_inputs = "/".join([self.host, str(self.port), self.stathost])
            self.aggregation_key = md5(aggregation_inputs).hexdigest()
        return self.event({
            'timestamp': int(time.time()),
            'event_type': 'tinyproxy',
            'msg_title': msg_title,
            'tags': tags,
            'msg_text': msg_text,
            'aggregation_key': self.aggregation_key
        })

    def get_tags(self):
        tags = ["url:{}".format(self.url)]
        if self.version is not None:
            tags.append("version:{}".format(self.version))
        return tags
