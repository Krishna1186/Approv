"""Instrument the existing v6 interpreter and bridge, without replacing their reading."""
from __future__ import annotations

import time

from approv.harness.intent import RequestInterpreter, as_extractor
from approv.ops.telemetry import CURRENT


class DependencyFailure(RuntimeError):
    pass


class Extractor:
    def __init__(self, config, base, metrics, *, interpreter_factory=RequestInterpreter):
        self.config, self.base, self.metrics = config, base, metrics
        self.interpreter_factory = interpreter_factory

    def __call__(self, text, schema):
        operation = CURRENT.get()
        if operation:
            operation.stage = "extractor"
        started = time.perf_counter()
        metadata, status = {}, "system_failure"
        try:
            key = self.config.credential.read(self.base).decode("utf-8")
            interpreter = self.interpreter_factory(self.config.endpoint, self.config.model,
                                                   key, version=self.config.prompt_version)
            def observed(case, category):
                nonlocal metadata
                result, metadata = interpreter(case, category)
                if metadata.get("status") != "parsed":
                    raise DependencyFailure("extractor returned an invalid interpretation")
                return result, metadata
            result = as_extractor(observed)(text, schema)
            status = "parsed"
            return result
        except Exception:
            # Provider exceptions can contain echoed credentials and request text.
            raise DependencyFailure("extractor unavailable") from None
        finally:
            self.metrics.extraction(metadata, self.config.prices,
                                    time.perf_counter() - started, status)
