"""Process and machine memory figures (inside Docker: the VM's)."""
import psutil


def process_rss_bytes() -> int:
    """Resident memory of this API process."""
    return psutil.Process().memory_info().rss


def total_memory_bytes() -> int:
    """Physical memory of the machine (or of the Docker VM)."""
    return psutil.virtual_memory().total


def available_memory_bytes() -> int:
    """Memory the OS can hand out without swapping."""
    return psutil.virtual_memory().available
