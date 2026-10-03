"""Model artifact scanner for unsafe deserialization (pickle RCE), built on picklescan.

Nothing is ever unpickled: picklescan walks the opcode stream and reports every imported global
(e.g. a __reduce__ returning os.system), classified as innocuous / suspicious / dangerous.

Hardening on top of picklescan:
- Polyglots: any file that parses as a pickle from byte 0 is scanned as a pickle, whatever else it claims
  to be (GGUF/safetensors magic, or a zip appended to a pickle: picklescan detects zips by the trailing
  directory, torch.load by the leading magic).
- Decompression budget: archive members are capped by total declared uncompressed size and count before
  anything is extracted (zip bombs).
- Fail closed: unparseable pickles, unreadable archive members and parser crashes are "unknown", never "safe".
"""

import hashlib
import io
import json
import os
import pickletools
import struct
import zipfile

from picklescan.scanner import SafetyLevel, scan_bytes as picklescan_bytes, scan_pickle_bytes

PICKLE_SUFFIXES = (".pkl", ".pickle", ".pt", ".pth", ".bin", ".ckpt", ".joblib", ".npy", ".npz", ".zip",
                   ".7z", ".safetensors", ".gguf")
PICKLE_MEMBER_SUFFIXES = {".pkl", ".pickle", ".joblib", ".dat", ".data"}  # what picklescan scans inside zips
SEVERITY = {SafetyLevel.Innocuous: "safe", SafetyLevel.Suspicious: "suspicious", SafetyLevel.Dangerous: "dangerous"}
VERDICT_ORDER = ["dangerous", "suspicious", "unknown", "safe"]
DEFAULT_MAX_UNPACKED = 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10_000
SEVENZ_MAGIC = b"7z\xbc\xaf\x27\x1c"
NUMPY_MAGIC = b"\x93NUMPY"


class ScanLimitError(Exception):
    pass


def _report(name: str, data: bytes, fmt: str, verdict: str, imports=(), note: str | None = None) -> dict:
    return {"name": name, "format": fmt, "verdict": verdict, "imports": list(imports), "note": note,
            "sha256": hashlib.sha256(data).hexdigest()}


def _parses_as_pickle(data: bytes) -> bool:
    try:
        for _ in pickletools.genops(io.BytesIO(data)):  # first pickle only; legacy torch appends raw tensor bytes
            pass
        return True
    except Exception:
        return False


def _is_safetensors(data: bytes) -> bool:
    try:
        (header_len,) = struct.unpack("<Q", data[:8])
        return header_len < len(data) and isinstance(json.loads(data[8 : 8 + header_len]), dict)
    except Exception:
        return False


def _is_gguf(data: bytes) -> bool:
    if len(data) < 24 or not data.startswith(b"GGUF"):
        return False
    version, tensor_count, kv_count = struct.unpack_from("<IQQ", data, 4)
    return version in (2, 3) and tensor_count < 1_000_000 and kv_count < 1_000_000


def _check_archive_budget(data: bytes, is_zip: bool, max_unpacked: int) -> None:
    if is_zip:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            sizes = [i.file_size for i in zf.infolist()]  # reads are bounded by these declared sizes
    elif data.startswith(SEVENZ_MAGIC):
        import py7zr

        with py7zr.SevenZipFile(io.BytesIO(data)) as archive:
            sizes = [i.uncompressed or 0 for i in archive.list()]
    else:
        return
    if len(sizes) > MAX_ARCHIVE_MEMBERS:
        raise ScanLimitError(f"archive has {len(sizes)} members, limit {MAX_ARCHIVE_MEMBERS}")
    if sum(sizes) > max_unpacked:
        raise ScanLimitError(f"archive unpacks to {sum(sizes)} bytes, limit {max_unpacked}")


def _unreadable_zip_members(data: bytes) -> list[str]:
    bad = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            try:
                with zf.open(info) as f:
                    looks_pickle = f.read(1) == b"\x80"
                if looks_pickle or os.path.splitext(info.filename)[1] in PICKLE_MEMBER_SUFFIXES:
                    if not _parses_as_pickle(zf.read(info)):
                        bad.append(info.filename)
            except Exception:  # truncated member, bad CRC, encrypted
                bad.append(info.filename)
    return bad


def scan_bytes(name: str, data: bytes, max_unpacked: int = DEFAULT_MAX_UNPACKED) -> dict:
    """Report format is one of pickle | pytorch_zip | safetensors | gguf | unknown (as in the proto)."""
    try:
        return _scan(name, data, max_unpacked)
    except ScanLimitError as exc:
        return _report(name, data, "unknown", "unknown", note=str(exc))
    except Exception as exc:
        return _report(name, data, "unknown", "unknown", note=f"could not parse: {type(exc).__name__}: {exc}")


def _scan(name: str, data: bytes, max_unpacked: int) -> dict:
    is_pickle = _parses_as_pickle(data)
    if not is_pickle:
        if _is_gguf(data):
            return _report(name, data, "gguf", "safe", note="gguf stores tensors, not code")
        if _is_safetensors(data):
            return _report(name, data, "safetensors", "safe", note="safetensors cannot execute code")
        if data.startswith(b"GGUF") or name.endswith((".gguf", ".safetensors")):
            return _report(name, data, "unknown", "unknown", note="invalid gguf/safetensors structure")

    is_zip = zipfile.is_zipfile(io.BytesIO(data))
    is_container = is_zip or data.startswith((SEVENZ_MAGIC, NUMPY_MAGIC))
    _check_archive_budget(data, is_zip, max_unpacked)

    result = picklescan_bytes(io.BytesIO(data), name, os.path.splitext(name)[1] or None)
    if is_pickle and is_container:  # polyglot: picklescan only looked at the container view
        result.merge(scan_pickle_bytes(io.BytesIO(data), name))

    imports, seen = [], set()
    for g in result.globals:
        if (g.module, g.name) not in seen:
            seen.add((g.module, g.name))
            imports.append({"module": g.module, "name": g.name, "severity": SEVERITY[g.safety]})
    fmt = "pytorch_zip" if is_zip else "pickle"
    severities = {i["severity"] for i in imports}
    if "dangerous" in severities or "suspicious" in severities:
        verdict = "dangerous" if "dangerous" in severities else "suspicious"
        return _report(name, data, fmt, verdict, imports)

    # Nothing flagged: only "safe" if we actually understood the file (picklescan calls unparseable input clean).
    if result.scan_err or result.scanned_files == 0:
        return _report(name, data, "unknown", "unknown", imports, "could not parse")
    if is_zip and (bad := _unreadable_zip_members(data)):
        return _report(name, data, "unknown", "unknown", imports, f"unreadable archive members: {bad[:5]}")
    if data.startswith(SEVENZ_MAGIC) and not imports:
        return _report(name, data, "unknown", "unknown", imports, "no pickle content found in 7z archive")
    if not is_container and not is_pickle:
        return _report(name, data, "unknown", "unknown", imports, "could not parse as pickle")
    return _report(name, data, fmt, "safe", imports)


def summarize(reports: list[dict]) -> dict:
    verdict = next((v for v in VERDICT_ORDER if any(r["verdict"] == v for r in reports)), "safe")
    dangerous = [f'{i["module"]}.{i["name"]}' for r in reports for i in r["imports"] if i["severity"] == "dangerous"]
    return {"safe": verdict == "safe", "verdict": verdict, "dangerous_imports": sorted(set(dangerous)),
            "files": reports}
