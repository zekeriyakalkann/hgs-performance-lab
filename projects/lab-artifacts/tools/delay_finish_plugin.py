"""Repro helper (not part of the repo): delays SyntheticServer._finish to widen the response-vs-record race window."""
import time

from hgs2_lab import synthetic_server

_real = synthetic_server.SyntheticServer._finish


def _delayed(self, event, **fields):
    time.sleep(0.2)
    return _real(self, event, **fields)


synthetic_server.SyntheticServer._finish = _delayed
