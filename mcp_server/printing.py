"""Send PDFs to a local printer through CUPS.

``lp`` is the CUPS client. The destination printer comes from PACKING_PRINTER or
the tool argument; when neither is set CUPS prints on its default queue.
"""
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .client import PackingError

_JOB_RE = re.compile(r"request id is (\S+)")
MAX_COPIES = 99


def validate_print_request(copies: int) -> str:
    """Check local prerequisites before any carrier booking and return lp's path."""
    if not isinstance(copies, int) or isinstance(copies, bool) or not 1 <= copies <= MAX_COPIES:
        raise PackingError(f"copies must be a whole number between 1 and {MAX_COPIES}")
    executable = shutil.which("lp")
    if executable is None:
        raise PackingError(
            "The CUPS `lp` command was not found. Install the CUPS client "
            "(Debian/Ubuntu: cups-client), make sure a printer is configured, and retry."
        )
    return executable


@dataclass(frozen=True)
class PrintJob:
    job_id: str | None
    printer: str
    output: str


def print_pdf(
    path: Path,
    *,
    printer: str | None = None,
    copies: int = 1,
    title: str | None = None,
) -> PrintJob:
    """Print an existing PDF file with ``lp`` and return the queued job."""
    executable = validate_print_request(copies)

    path = Path(path)
    if not path.is_file():
        raise PackingError(f"Nothing to print: {path} does not exist.")
    try:
        with path.open("rb") as handle:
            magic = handle.read(5)
    except OSError as exc:
        raise PackingError(f"Cannot read {path}: {exc}") from None
    if magic != b"%PDF-":
        raise PackingError(f"Refusing to print {path}: it is not a PDF file.")

    command = [executable]
    if printer:
        command += ["-d", printer]
    if copies != 1:
        command += ["-n", str(copies)]
    if title:
        command += ["-t", title[:80]]
    command.append(str(path))

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise PackingError(f"`lp` could not be started: {exc}") from None

    output = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode != 0:
        detail = stderr or output or f"exit code {result.returncode}"
        raise PackingError(
            f"Printing failed: {detail}. Check that the printer exists "
            "(`lpstat -p`) and that PACKING_PRINTER names a configured queue."
        )

    match = _JOB_RE.search(output)
    job_id = match.group(1) if match else None
    # "request id is Office-42" — the queue name is everything before "-<number>".
    reported_printer = printer or (job_id.rsplit("-", 1)[0] if job_id and "-" in job_id else "default")
    return PrintJob(job_id=job_id, printer=reported_printer, output=output)
