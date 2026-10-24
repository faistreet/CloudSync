import threading
from PySide6.QtCore import QObject, Signal


class TaskSignals(QObject):
    progress = Signal(dict)
    finished = Signal(dict)


def run_async_task(task_func, args=(), on_progress=None, on_finished=None):
    """
    Runs a task in a Python daemon thread and safely emits Qt signals to the GUI.
    Unlike QThread, Python daemon threads NEVER trigger 'QThread: Destroyed while thread is still running'
    core dumps when dialogs or windows are closed.
    """
    signals = TaskSignals()
    if on_progress:
        signals.progress.connect(on_progress)
    if on_finished:
        signals.finished.connect(on_finished)

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
