import collections
import logging
import time

LOG_BUF: collections.deque[str] = collections.deque(maxlen=2000)


class BufHandler(logging.Handler):
    def emit(self, record):
        LOG_BUF.append(f"{time.strftime('%H:%M:%S')} {record.getMessage()}")


_log = logging.getLogger("nova")
_log.setLevel(logging.INFO)
_log.addHandler(BufHandler())
_log.addHandler(logging.StreamHandler())


def log_info(msg):
    _log.info(msg)
