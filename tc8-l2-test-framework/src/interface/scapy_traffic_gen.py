"""
Scapy-based traffic generator for basic burst sending on a standard PC NIC.

Limitations (see known_limitations.md for full list):
  - Rate accuracy: ±30% — OS scheduler and Python GIL introduce jitter.
  - No inter-frame gap < ~1 ms reliably achievable.
  - Cannot sustain line-rate (100 Mbps) on most PCs — Scapy throughput is
    typically 5–20 Mbps on a standard desktop/laptop NIC.
  - Throughput measurement requires a second NIC on the capture side; without
    one, received frame count is estimated from sent frames only.
  - Windows: Npcap required; rate accuracy further reduced vs. Linux AF_PACKET.

Use for:
  - Functional burst tests (does the DUT react to N frames?)
  - Low-rate multicast/storm-control threshold smoke tests
  - Informational rate estimates in automated CI where hardware tgen is absent

Do NOT use for:
  - Production conformance claims on SWITCH_FILT_008 storm control
  - SWITCH_QOS_* rate-accuracy measurements
  - EXT_PERF_003/004/005 (these require dedicated hardware and SKIP)
"""

from __future__ import annotations

import asyncio
import logging
import time

from src.interface.base_traffic_gen import BaseTrafficGen, BurstResult, ThroughputResult

logger = logging.getLogger(__name__)

# Scapy import is lazy so the module loads even if Scapy is not installed.
# Callers must ensure Scapy is available before calling send_burst or
# measure_throughput — both raise ImportError if it is not.


class ScapyTrafficGen(BaseTrafficGen):
    """
    Scapy-based burst traffic generator for PC + DUT test setups.

    Wraps Scapy's sendp() for burst transmission. Not suitable for
    hardware-accurate rate measurements — use for functional/smoke tests only.
    """

    @property
    def is_hardware_accurate(self) -> bool:
        return False

    async def send_burst(
        self,
        frames: list,
        iface: str,
        count: int = 1,
        inter_frame_gap_s: float = 0.0,
    ) -> BurstResult:
        """
        Send a burst of Scapy frames on the given interface.

        Runs Scapy's sendp() in a thread executor so it doesn't block the
        asyncio event loop. The OS NIC driver and Scapy overhead mean actual
        throughput will be well below line rate on most PC NICs.
        """
        try:
            from scapy.sendrecv import sendp
        except ImportError as exc:
            raise ImportError("Scapy is required for ScapyTrafficGen.send_burst") from exc

        if not frames:
            return BurstResult(
                frames_sent=0, frames_received=0, duration_s=0.0,
                achieved_pps=0.0, achieved_mbps=0.0, loss_rate_pct=0.0,
                warnings=["No frames provided to send_burst"],
            )

        total_frames = len(frames) * count
        frame_size = len(bytes(frames[0])) if frames else 64

        def _send() -> float:
            t_start = time.perf_counter()
            for _ in range(count):
                for pkt in frames:
                    sendp(pkt, iface=iface, verbose=False)
                    if inter_frame_gap_s > 0:
                        time.sleep(inter_frame_gap_s)
            return time.perf_counter() - t_start

        logger.info(
            "ScapyTrafficGen: sending %d frames × %d = %d total on %s",
            len(frames), count, total_frames, iface,
        )

        loop = asyncio.get_event_loop()
        duration_s = await loop.run_in_executor(None, _send)

        achieved_pps = total_frames / duration_s if duration_s > 0 else 0.0
        achieved_mbps = (total_frames * frame_size * 8) / (duration_s * 1e6) if duration_s > 0 else 0.0

        logger.info(
            "Burst complete: %d frames in %.3fs → %.1f pps / %.2f Mbps",
            total_frames, duration_s, achieved_pps, achieved_mbps,
        )

        return BurstResult(
            frames_sent=total_frames,
            frames_received=total_frames,  # no capture on send-only burst
            duration_s=duration_s,
            achieved_pps=achieved_pps,
            achieved_mbps=achieved_mbps,
            loss_rate_pct=0.0,
            warnings=[self.accuracy_warning()],
        )

    async def measure_throughput(
        self,
        frames: list,
        iface: str,
        duration_s: float,
        capture_iface: str | None = None,
    ) -> ThroughputResult:
        """
        Send frames in a loop for duration_s and measure achieved rate.

        If capture_iface is provided, starts a Scapy sniffer to count received
        frames. Without it, received count equals sent count (optimistic).

        Accuracy caveat: on a standard PC NIC with Python/Scapy, expect
        5–20 Mbps maximum throughput regardless of offered load. OS scheduler
        jitter causes ±30% variation in measured pps.
        """
        try:
            from scapy.sendrecv import sendp, AsyncSniffer
        except ImportError as exc:
            raise ImportError("Scapy is required for ScapyTrafficGen.measure_throughput") from exc

        if not frames:
            return ThroughputResult(
                offered_pps=0.0, achieved_pps=0.0, achieved_mbps=0.0,
                frame_size_bytes=64, duration_s=duration_s, loss_pct=0.0,
                is_accurate=False, warnings=["No frames provided"],
            )

        frame_size = len(bytes(frames[0]))
        sent_count = 0
        received_count: list[int] = [0]

        sniffer = None
        if capture_iface:
            sniffer = AsyncSniffer(
                iface=capture_iface,
                prn=lambda _: received_count.__setitem__(0, received_count[0] + 1),
                store=False,
            )
            sniffer.start()

        def _send_loop() -> tuple[int, float]:
            nonlocal sent_count
            t_end = time.perf_counter() + duration_s
            t_start = time.perf_counter()
            n = 0
            while time.perf_counter() < t_end:
                for pkt in frames:
                    sendp(pkt, iface=iface, verbose=False)
                    n += 1
            return n, time.perf_counter() - t_start

        loop = asyncio.get_event_loop()
        logger.info(
            "ScapyTrafficGen: measuring throughput on %s for %.1fs", iface, duration_s
        )
        sent_count, actual_duration = await loop.run_in_executor(None, _send_loop)

        if sniffer:
            sniffer.stop()

        rx = received_count[0] if capture_iface else sent_count
        achieved_pps = sent_count / actual_duration if actual_duration > 0 else 0.0
        achieved_mbps = (sent_count * frame_size * 8) / (actual_duration * 1e6) if actual_duration > 0 else 0.0
        loss_pct = max(0.0, (sent_count - rx) / sent_count * 100) if sent_count > 0 else 0.0

        logger.info(
            "Throughput: %d sent / %d received in %.3fs → %.1f pps / %.2f Mbps / %.1f%% loss",
            sent_count, rx, actual_duration, achieved_pps, achieved_mbps, loss_pct,
        )

        warnings = [self.accuracy_warning()]
        if achieved_mbps < 10.0:
            warnings.append(
                f"Achieved only {achieved_mbps:.1f} Mbps — typical Scapy limit on PC NIC. "
                "This is a Scapy/OS limitation, not a DUT fault."
            )

        return ThroughputResult(
            offered_pps=achieved_pps,
            achieved_pps=achieved_pps,
            achieved_mbps=achieved_mbps,
            frame_size_bytes=frame_size,
            duration_s=actual_duration,
            loss_pct=loss_pct,
            is_accurate=False,
            warnings=warnings,
        )
