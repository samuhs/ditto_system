"""Process and machine memory figures (inside Docker: the VM's)."""
import ctypes
import os
import sys

import psutil


class _RusageInfoV0(ctypes.Structure):
    """struct rusage_info_v0 from <sys/resource.h> (macOS)."""

    _fields_ = [("ri_uuid", ctypes.c_uint8 * 16)] + [
        (name, ctypes.c_uint64)
        for name in (
            "ri_user_time", "ri_system_time", "ri_pkg_idle_wkups", "ri_interrupt_wkups",
            "ri_pageins", "ri_wired_size", "ri_resident_size", "ri_phys_footprint",
            "ri_proc_start_abstime", "ri_proc_exit_abstime",
        )
    ]


def _darwin_phys_footprint(pid: int) -> int | None:
    """What Activity Monitor calls "Memory": includes compressed, swapped and Metal pages."""
    try:
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib")
        info = _RusageInfoV0()
        if libproc.proc_pid_rusage(pid, 0, ctypes.byref(info)) != 0:  # 0 = RUSAGE_INFO_V0
            return None
        return int(info.ri_phys_footprint)
    except OSError:
        return None


def process_memory_bytes() -> int:
    """Memory this API process uses.

    On macOS, RSS leaves out compressed and swapped-out pages, so under memory
    pressure it can show a few MB for a process holding GBs; the physical
    footprint does not. Elsewhere RSS is the usual measure.
    """
    if sys.platform == "darwin":
        footprint = _darwin_phys_footprint(os.getpid())
        if footprint is not None:
            return footprint
    return psutil.Process().memory_info().rss


def total_memory_bytes() -> int:
    """Physical memory of the machine (or of the Docker VM)."""
    return psutil.virtual_memory().total


def available_memory_bytes() -> int:
    """Memory the OS can hand out without swapping."""
    return psutil.virtual_memory().available
