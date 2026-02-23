"""
Scapy-based DUT controller — real hardware interaction.

Implements the DUTController protocol using psutil for link state
verification and optional DUT reset via shell command.  MAC table /
statistics clearing are best-effort stubs because network switches
cannot be managed over raw Ethernet.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Any

import psutil

from src.models.test_case import DUTProfile

logger = logging.getLogger(__name__)

_TAG = "[ScapyDUT]"


class ScapyDUTController:
    """
    Concrete DUT controller for live hardware testing.

    Uses psutil to verify physical link state and (optionally) a
    shell command to power-cycle the DUT between tests.
    """

    def __init__(self, dut_profile: DUTProfile) -> None:
        self._profile = dut_profile
        # Build a mapping from port_id → OS interface name
        self._port_iface: dict[int, str] = {
            p.port_id: p.interface_name for p in dut_profile.ports
        }

    # ── DUTController protocol ────────────────────────────────────────

    async def clear_mac_table(self) -> bool:
        """
        Request MAC table clear.

        Physical switches cannot be cleared over raw Ethernet, so we
        log the request and return True.  The session manager will
        fall back to aging if needed.
        """
        logger.info("%s MAC table clear requested — no direct management channel", _TAG)
        return True

    async def clear_statistics(self) -> bool:
        """Clear statistics — no direct management channel available."""
        logger.info("%s Statistics clear requested — no direct management channel", _TAG)
        return True

    async def verify_link_state(self, port_id: int) -> bool:
        """Check real link state via psutil."""
        iface_name = self._port_iface.get(port_id)
        if iface_name is None:
            logger.warning("%s Port %d has no mapped interface", _TAG, port_id)
            return False

        try:
            stats = psutil.net_if_stats()
            if iface_name in stats:
                is_up = stats[iface_name].isup
                speed = stats[iface_name].speed
                logger.info(
                    "%s Link state on port %d (%s): %s (%d Mbps)",
                    _TAG, port_id, iface_name,
                    "UP" if is_up else "DOWN", speed,
                )
                return is_up
            else:
                logger.warning(
                    "%s Interface '%s' (port %d) not found on this host",
                    _TAG, iface_name, port_id,
                )
                return False
        except Exception as exc:
            logger.error("%s Link state check failed for port %d: %s", _TAG, port_id, exc)
            return False

    async def get_mac_table_entries(self) -> int:
        """Cannot query switch MAC table over raw Ethernet."""
        return 0

    async def reset_dut(self) -> bool:
        """Reset the DUT using the configured reset command, if any."""
        cmd = self._profile.reset_command
        if not cmd:
            logger.warning("%s DUT reset requested but no reset_command configured", _TAG)
            return False

        logger.info("%s Executing DUT reset: %s", _TAG, cmd)
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            if proc.returncode == 0:
                logger.info("%s DUT reset succeeded", _TAG)
                return True
            else:
                logger.error(
                    "%s DUT reset failed (rc=%d): %s",
                    _TAG, proc.returncode, stderr.decode(errors="replace"),
                )
                return False
        except asyncio.TimeoutError:
            logger.error("%s DUT reset timed out after 30s", _TAG)
            return False
        except Exception as exc:
            logger.error("%s DUT reset error: %s", _TAG, exc)
            return False
