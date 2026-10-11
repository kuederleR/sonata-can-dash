"""Listen-only SocketCAN reader. Never transmits frames to the vehicle bus."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from can_reader.decode import FrameDecoder
from can_reader.state import SharedState

log = logging.getLogger(__name__)


class CanReader:
    """Background thread that recv()s from SocketCAN and updates SharedState.

    CRITICAL: this class never calls bus.send(). Listen-only only.
    """

    def __init__(
        self,
        state: SharedState,
        channel: str = "can0",
        interface: str = "socketcan",
        bitrate: int = 500_000,
        decoder: FrameDecoder | None = None,
    ) -> None:
        self.state = state
        self.channel = channel
        self.interface = interface
        self.bitrate = bitrate
        self.decoder = decoder or FrameDecoder(state)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._frame_times: list[float] = []

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="can-reader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        try:
            import can  # noqa: WPS433 — optional at import time for simulate-only hosts
        except ImportError:
            log.error("python-can is not installed")
            self.state.set_health(connected=False, interface=f"{self.interface}:{self.channel}")
            return

        self.state.set_health(
            connected=False,
            interface=f"{self.interface}:{self.channel}",
        )
        bus = None
        try:
            # receive_own_messages=False; we never send anyway.
            bus = can.Bus(
                channel=self.channel,
                interface=self.interface,
                bitrate=self.bitrate,
                receive_own_messages=False,
            )
            log.info(
                "Listening on %s:%s @ %d (recv-only, never transmit)",
                self.interface,
                self.channel,
                self.bitrate,
            )
            self.state.set_health(connected=True)

            while not self._stop.is_set():
                msg = bus.recv(timeout=0.5)
                if msg is None:
                    self._update_fps()
                    continue
                data = bytes(msg.data)
                self.decoder.handle_frame(msg.arbitration_id, data)
                self._frame_times.append(time.monotonic())
                self._update_fps()
        except Exception as exc:  # noqa: BLE001 — keep reader alive / report health
            log.exception("CAN reader error: %s", exc)
            self.state.set_health(connected=False)
        finally:
            if bus is not None:
                try:
                    bus.shutdown()
                except Exception:  # noqa: BLE001
                    pass

    def _update_fps(self) -> None:
        now = time.monotonic()
        cutoff = now - 1.0
        self._frame_times = [t for t in self._frame_times if t >= cutoff]
        self.state.set_health(frames_per_sec=float(len(self._frame_times)))


class FrameSourceReader:
    """Generic reader that pulls (can_id, data) from a callable — used by simulator."""

    def __init__(
        self,
        state: SharedState,
        source: Callable[[], tuple[int, bytes] | None],
        interface_label: str = "simulator",
        poll_hz: float = 200.0,
        decoder: FrameDecoder | None = None,
    ) -> None:
        self.state = state
        self.source = source
        self.interface_label = interface_label
        self.poll_interval = 1.0 / poll_hz
        self.decoder = decoder or FrameDecoder(state)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._frame_times: list[float] = []

    def start(self) -> None:
        self._stop.clear()
        self.state.set_health(connected=True, interface=self.interface_label)
        self._thread = threading.Thread(
            target=self._run, name="frame-source", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            item = self.source()
            if item is not None:
                can_id, data = item
                self.decoder.handle_frame(can_id, data)
                self._frame_times.append(time.monotonic())
                now = time.monotonic()
                cutoff = now - 1.0
                self._frame_times = [t for t in self._frame_times if t >= cutoff]
                self.state.set_health(frames_per_sec=float(len(self._frame_times)))
            time.sleep(self.poll_interval)
