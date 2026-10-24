import threading
from PySide6.QtCore import QObject, Signal


class TaskSignals(QObject):
    progress = Signal(dict)
    finished = Signal(dict)


_active_runners = set()


def run_async_task(task_func, args=(), on_progress=None, on_finished=None):
    """
    Runs a task in a Python daemon thread and safely emits Qt signals to the GUI.
    Maintains a strong reference to TaskSignals in _active_runners to prevent premature
    garbage collection during cross-thread signal emission.
    """
    signals = TaskSignals()
    _active_runners.add(signals)

    if on_progress:
        signals.progress.connect(on_progress)

    def on_task_finished(res):
        try:
            if on_finished:
                on_finished(res)
        finally:
            _active_runners.discard(signals)

    signals.finished.connect(on_task_finished)

    def worker():
        try:
            # Check if task_func accepts progress_callback
            import inspect
            sig = inspect.signature(task_func)
            if "progress_callback" in sig.parameters:
                res = task_func(*args, progress_callback=signals.progress.emit)
            else:
                res = task_func(*args)

            if isinstance(res, dict):
                signals.finished.emit(res)
            else:
                signals.finished.emit({"success": True, "result": res})
        except Exception as e:
            print(f"[TaskRunner] Error in background task: {e}")
            signals.finished.emit({"success": False, "error": str(e)})

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return signals
