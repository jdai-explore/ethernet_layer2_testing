"""
Smart test case sampling.

Reduces the combinatorial explosion of test cases (200K-500K+)
by selecting representative samples: edge cases, boundary values,
and statistically representative midpoints.
"""

from __future__ import annotations

import logging
import random
from typing import Sequence

logger = logging.getLogger(__name__)


class VIDSampler:
    """
    Samples VLAN IDs intelligently from the 0-4095 range.

    Strategies:
    - edge:         Only boundary values (0, 1, 4094, 4095)
    - representative: Edges + evenly-spaced midpoints
    - random:       Random sample of N values
    - all:          Full range (0-4095)
    """

    EDGE_VIDS = [0, 1, 4094, 4095]
    COMMON_VIDS = [0, 1, 10, 100, 500, 1000, 2000, 3000, 4000, 4094, 4095]

    @classmethod
    def sample(
        cls,
        strategy: str = "representative",
        count: int = 10,
        vid_range: tuple[int, int] = (0, 4095),
        seed: int | None = None,
    ) -> list[int]:
        """
        Sample VIDs using the given strategy.

        Args:
            strategy: Sampling strategy name.
            count: Number of samples for 'representative' and 'random'.
            vid_range: Inclusive (start, end) range.
            seed: Random seed for reproducibility.
        """
        start, end = vid_range

        if strategy == "all":
            return list(range(start, end + 1))

        if strategy == "edge":
            return [v for v in cls.EDGE_VIDS if start <= v <= end]

        if strategy == "random":
            rng = random.Random(seed)
            pool = list(range(start, end + 1))
            edges = [v for v in cls.EDGE_VIDS if start <= v <= end]
            sample = list(set(edges))
            remaining = count - len(sample)
            if remaining > 0:
                non_edge = [v for v in pool if v not in sample]
                sample.extend(rng.sample(non_edge, min(remaining, len(non_edge))))
            return sorted(sample)

        # representative (default)
        edges = [v for v in cls.EDGE_VIDS if start <= v <= end]
        total_range = end - start
        if total_range <= count:
            return list(range(start, end + 1))

        step = total_range // (count - len(edges))
        midpoints = list(range(start, end + 1, max(1, step)))
        combined = sorted(set(edges + midpoints))
        return combined[:count] if len(combined) > count else combined


class PortPairSampler:
    """
    Samples ingress/egress port pairs.

    Strategies:
    - first_pair:       Only first available pair
    - diagonal:         Each port as ingress once, different egress
    - all_pairs:        All permutations (N × N-1)
    - all_combinations: All unique combinations (N choose 2)
    """

    @classmethod
    def sample(
        cls,
        port_ids: Sequence[int],
        strategy: str = "all_pairs",
    ) -> list[tuple[int, int]]:
        ports = list(port_ids)
        if len(ports) < 2:
            if len(ports) == 1:
                return [(ports[0], ports[0])]
            return []

        if strategy == "first_pair":
            return [(ports[0], ports[1])]

        if strategy == "diagonal":
            pairs = []
            for i, ingress in enumerate(ports):
                egress = ports[(i + 1) % len(ports)]
                pairs.append((ingress, egress))
            return pairs

        if strategy == "all_combinations":
            return [
                (ports[i], ports[j])
                for i in range(len(ports))
                for j in range(i + 1, len(ports))
            ]

        # all_pairs (default): all permutations
        return [
            (i, e) for i in ports for e in ports if i != e
        ]


class TestSampler:
    """
    Combines VID and port sampling to estimate total test case counts.
    """

    @staticmethod
    def estimate_case_count(
        spec_count: int,
        port_count: int,
        vid_strategy: str = "representative",
        vid_count: int = 10,
        frame_types: int = 3,
        tpid_count: int = 3,
        port_strategy: str = "all_pairs",
    ) -> int:
        """Estimate total test case count for a configuration."""
        port_pairs = len(PortPairSampler.sample(list(range(port_count)), port_strategy))
        vids = len(VIDSampler.sample(vid_strategy, vid_count))

        total = spec_count * port_pairs * vids * frame_types * tpid_count
        logger.info(
            "Estimated cases: %d specs × %d port-pairs × %d VIDs × %d frames × %d TPIDs = %d",
            spec_count, port_pairs, vids, frame_types, tpid_count, total,
        )
        return total
