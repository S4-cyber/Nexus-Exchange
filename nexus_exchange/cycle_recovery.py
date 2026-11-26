"""Bounded Scout terminalization; no retries or execution authority."""
import sqlite3


class CycleMaintenanceRequired(RuntimeError):
    """Recovery could not be verified; require a new owner startup review."""


_MESSAGE = 'Scout cycle storage requires maintenance. Automatic engagement paused.'
_STORAGE_ERRORS = (ValueError, OSError, sqlite3.Error)


class CycleRecovery:
    def __init__(self, settle, record, stopped):
        self._settle = settle
        self._record = record
        self._stopped = stopped
        self._settlement_attempted = False
        self._journal_fault = False
        self._state = None

    def settle(self, failed=False):
        self._settlement_attempted = True
        try:
            self._settle(failed)
        except _STORAGE_ERRORS:
            raise CycleMaintenanceRequired(_MESSAGE) from None

    def record(self, state):
        try:
            self._record(state)
        except _STORAGE_ERRORS:
            self._journal_fault = True
            raise CycleMaintenanceRequired(_MESSAGE) from None
        self._state = state

    def fail(self, error):
        """Try each independent recovery path once; never fabricate a task state."""
        maintenance = isinstance(error, CycleMaintenanceRequired)
        halted = self._stopped() is not False
        if not self._settlement_attempted:
            try:
                self.settle(failed=not halted)
            except CycleMaintenanceRequired:
                maintenance = True
        if not self._journal_fault and self._state in ('queued', 'running'):
            state = ('cancelled' if halted else
                     'interrupted' if self._state == 'queued' else 'failed')
            try:
                self.record(state)
            except CycleMaintenanceRequired:
                maintenance = True
        if maintenance:
            raise CycleMaintenanceRequired(_MESSAGE) from None
