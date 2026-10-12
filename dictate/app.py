"""Dictate: hold Right Shift to record, release to transcribe, clean up and paste into the focused textbox."""
import logging
import os
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

import numpy as np
from PySide6.QtCore import QLockFile, QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .hotkey import RightShift
from .inserter import paste
from .overlay import EdgeGlow
from .recorder import MicError, Recorder
from .transcriber import DATA_DIR, MAX_SECONDS, MIN_SECONDS, SAMPLE_RATE, Transcriber, too_short
from .voicebar import VoiceBar
from .window import MainWindow

log = logging.getLogger("dictate")
TRAY_COLORS = {"idle": "#7c6ce0", "listening": "#22d3c5", "error": "#fb464c"}


def make_icon(color: str) -> QIcon:
    """A microphone on a colored disc."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(2, 2, 60, 60)
    p.setBrush(Qt.white)
    p.drawRoundedRect(QRectF(24, 12, 16, 26), 8, 8)
    p.setPen(QPen(Qt.white, 4, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(17, 20, 30, 26), 180 * 16, 180 * 16)
    p.drawLine(32, 46, 32, 52)
    p.end()
    return QIcon(pix)


class App(QObject):
    # Worker threads report back through these; Qt delivers them on the main thread.
    _model_loaded = Signal(str)  # "" when ready, else the error
    _mic_failed = Signal(str)
    _finished = Signal(str, str)  # kind ("text" | "empty" | "error"), payload

    def __init__(self, qapp: QApplication):
        super().__init__()
        self.qapp = qapp
        self.recorder = Recorder()
        self.transcriber = Transcriber()
        self.audio = ThreadPoolExecutor(1, thread_name_prefix="audio")  # mic open/close, in order
        self.work = ThreadPoolExecutor(1, thread_name_prefix="transcribe")  # transcriptions, in order
        self.glow = EdgeGlow(lambda: min(1.0, self.recorder.level * 8))
        self.bar = VoiceBar(lambda: min(1.0, self.recorder.level * 8))
        self.icons = {name: make_icon(color) for name, color in TRAY_COLORS.items()}
        self.window = MainWindow(self.icons["idle"])

        self.tray = QSystemTrayIcon(self.icons["idle"])
        self.tray.setToolTip("Dictate: hold Right Shift to dictate")
        menu = QMenu()
        menu.addAction("Open", self._open)
        menu.addAction("Quit", self._quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: reason == QSystemTrayIcon.Trigger and self._open())

        self.hotkey = RightShift()
        self.hotkey.pressed.connect(self._on_press)
        self.hotkey.released.connect(self._on_release)
        self._cap = QTimer(interval=250)
        self._cap.timeout.connect(self._check_cap)

        self._model_loaded.connect(self._on_model_loaded)
        self._mic_failed.connect(self._on_mic_failed)
        self._finished.connect(self._on_finished)

        self._load_error = ""
        self._holding = False
        self._pressed_at = 0.0
        self._pending = 0

    def start(self, hidden: bool) -> None:
        self.tray.show()
        if not hidden:
            self._open()
        self.hotkey.start()
        threading.Thread(target=self._load_model, daemon=True).start()

    # Model --------------------------------------------------------------

    def _load_model(self) -> None:
        started = time.perf_counter()
        try:
            self.transcriber.load()
            log.info("transcriber ready in %.1f s", time.perf_counter() - started)
            self._model_loaded.emit("")
        except Exception as err:
            log.exception("model load failed")
            self._model_loaded.emit(f"Could not start transcription: {err}")

    def _on_model_loaded(self, error: str) -> None:
        self._load_error = error
        if error:
            self._fail(error)
        else:
            self._set_state("ready")

    # Recording ----------------------------------------------------------

    def _on_press(self) -> None:
        if self._holding:
            return
        if not self.transcriber.ready:
            self._fail(self._load_error or "Still connecting to Groq")
            return
        self._holding = True
        self._pressed_at = time.monotonic()
        self.glow.listen()
        self.bar.listen()
        self._set_state("listening")
        self.audio.submit(self._open_mic)
        self._cap.start()

    def _open_mic(self) -> None:
        try:
            self.recorder.start()
        except MicError as err:
            self._mic_failed.emit(str(err))

    def _on_mic_failed(self, message: str) -> None:
        self._holding = False
        self._cap.stop()
        self._fail(message)

    def _check_cap(self) -> None:
        if time.monotonic() - self._pressed_at >= MAX_SECONDS:
            self._on_release()

    def _on_release(self) -> None:
        if not self._holding:
            return
        self._holding = False
        self._cap.stop()
        stopped = self.audio.submit(self.recorder.stop)
        if time.monotonic() - self._pressed_at < MIN_SECONDS:  # a normal Shift press, not dictation
            self.glow.discard()
            self.bar.dismiss()
            self._set_state("ready")
            return
        self._pending += 1
        self.glow.transcribing()
        self.bar.transcribing()
        self._set_state("transcribing")
        self.work.submit(self._transcribe, stopped)

    # Transcription ------------------------------------------------------

    def _transcribe(self, stopped: Future) -> None:
        try:
            pcm = stopped.result()
            if too_short(pcm):
                self._finished.emit("empty", "")
                return
            if not np.any(pcm):
                self._finished.emit(
                    "error",
                    "The microphone sent no signal. Check Windows Settings → Privacy & security → Microphone.",
                )
                return
            started = time.perf_counter()
            text = self.transcriber.transcribe(pcm)
            log.info(
                "transcribed %.1f s of audio in %d ms (%d chars)",
                pcm.size / SAMPLE_RATE,
                (time.perf_counter() - started) * 1000,
                len(text),
            )
            if text:
                started = time.perf_counter()
                text = self.transcriber.correct(text)
                log.info("cleaned up in %d ms (%d chars)", (time.perf_counter() - started) * 1000, len(text))
            self._finished.emit("text" if text else "empty", text)
        except Exception as err:
            log.exception("transcription failed")
            self._finished.emit("error", f"Transcription failed: {err}")

    def _on_finished(self, kind: str, payload: str) -> None:
        self._pending -= 1
        if kind == "error":
            self._fail(payload)
            return
        if kind == "text":
            paste(payload + " ")  # trailing space so back-to-back dictations don't run together
            self.window.add_transcript(payload)
        if self._holding:  # a new recording owns the glow now
            return
        if self._pending:
            self.glow.transcribing()
            return
        self.bar.dismiss()
        self.glow.done() if kind == "text" else self.glow.discard()
        self._set_state("ready")

    # UI -----------------------------------------------------------------

    def _set_state(self, state: str) -> None:
        self.window.set_status(state)
        self.tray.setIcon(self.icons["listening" if state == "listening" else "idle"])

    def _fail(self, message: str) -> None:
        log.warning("error: %s", message)
        self.glow.error()
        self.bar.dismiss()
        self.window.set_status("error", message)
        self.tray.setIcon(self.icons["error"])
        self.tray.showMessage("Dictate", message, QSystemTrayIcon.Warning, 4000)

    def _open(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _quit(self) -> None:
        self.hotkey.stop()
        self.tray.hide()
        self.qapp.quit()


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    logging.basicConfig(
        filename=os.path.join(DATA_DIR, "dictate.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    lock = QLockFile(os.path.join(DATA_DIR, "dictate.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, "Dictate", "Dictate is already running. Look for it in the system tray.")
        return
    app = App(qapp)
    app.start(hidden="--hidden" in sys.argv)  # --hidden: start in the tray only (used at login)
    qapp.exec()
    lock.unlock()
