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
- GGUF is not automatically safe: its Jinja chat template is rendered by llama-cpp-python, and a malicious
  template was a real RCE (CVE-2024-34359). The metadata is parsed and templates using Python internals are flagged.
"""

import hashlib
import io
import json
import logging
import os
import pickletools
import re
import struct
import tempfile
import zipfile
from pathlib import Path

import numpy.lib.format as npy_format
from picklescan.scanner import SafetyLevel, ScanResult, scan_bytes as picklescan_bytes, scan_numpy, scan_pickle_bytes

PICKLE_SUFFIXES = (".pkl", ".pickle", ".pt", ".pth", ".bin", ".ckpt", ".joblib", ".npy", ".npz", ".zip",
                   ".7z", ".safetensors", ".gguf")
PICKLE_MEMBER_SUFFIXES = {".pkl", ".pickle", ".joblib", ".dat", ".data"}  # what picklescan scans inside zips
# Same rule picklescan uses to decide a zip member is a pickle (PROTO opcode + protocol 0-5). A looser rule
# (any leading 0x80) would misread ~1 in 256 raw tensor files in a PyTorch zip as broken pickles.
PICKLE_MAGIC = tuple(bytes([0x80, v]) for v in range(6))
NESTED_ARCHIVE_SUFFIXES = {".zip", ".7z", ".npz", ".tar", ".gz", ".tgz", ".bz2", ".xz"}
# Repo files that cannot carry executable model content; everything else in a repo is scanned or reported.
BENIGN_REPO_SUFFIXES = {".json", ".md", ".txt", ".model", ".tiktoken", ".vocab",
                        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".yaml", ".yml", ".cfg", ".ini", ".csv",
                        ".tsv"}
# matched on the whole file name: os.path.splitext(".gitattributes") has no suffix
BENIGN_REPO_NAMES = {"license", "notice", "copying", "readme", ".gitattributes", ".gitignore"}
# Formats that can execute code on load but that this scanner cannot analyse (Keras Lambda layers, etc.).
UNSCANNABLE_SUFFIXES = {".h5", ".hdf5", ".keras", ".pb", ".tflite", ".onnx", ".msgpack", ".mlmodel", ".tar",
                        ".gz", ".tgz"}
SEVERITY = {SafetyLevel.Innocuous: "safe", SafetyLevel.Suspicious: "suspicious", SafetyLevel.Dangerous: "dangerous"}
VERDICT_ORDER = ["dangerous", "suspicious", "unknown", "safe"]
DEFAULT_MAX_UNPACKED = 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10_000
ZIP_MAGIC = b"PK\x03\x04"
SEVENZ_MAGIC = b"7z\xbc\xaf\x27\x1c"
NUMPY_MAGIC = b"\x93NUMPY"

log = logging.getLogger(__name__)


class ScanLimitError(Exception):
    pass


def _report(name: str, data: bytes, fmt: str, verdict: str, imports=(), note: str | None = None) -> dict:
    return {"name": name, "format": fmt, "verdict": verdict, "imports": list(imports), "note": note,
            "sha256": hashlib.sha256(data).hexdigest()}


# torch.save's legacy (non-zip) format: 5 pickles (magic, protocol, sys info, the object, storage keys),
# then raw tensor bytes. Its first pickle is always this one.
LEGACY_TORCH_MAGIC = b"\x80\x02\x8a\x0al\xfc\x9cF\xf9 j\xa8P\x19."
LEGACY_TORCH_PICKLES = 5


def _complete_pickles(data: bytes, limit: int) -> int:
    """How many complete pickles (up to `limit`) parse one after another from the start of `data`."""
    stream, count = io.BytesIO(data), 0
    try:
        while count < limit and stream.tell() < len(data):
            for _ in pickletools.genops(stream):
                pass
            count += 1
    except Exception:
        pass
    return count


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


GGUF_FIXED_SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
GGUF_STRING, GGUF_ARRAY = 8, 9
# Every Jinja sandbox escape (CVE-2024-34359 included) needs Python internals: an underscore attribute
# (__class__, __globals__), frame/generator internals, or a global whose attributes lead there. Names can be
# assembled at runtime ('__cla' ~ 'ss__', {% set %}, str(obj)[i]), so instead of looking for bad words the
# template's AST is checked against what real chat templates use (measured on tests/fixtures/chat_templates):
# subscripts by literal or integer arithmetic only, attribute-taking filters with literal names only.
INTERNAL_ATTRIBUTES = {"gi_frame", "gi_code", "cr_frame", "cr_code", "ag_frame", "f_globals", "f_locals",
                       "f_builtins", "f_back", "f_code", "tb_frame", "tb_next", "func_globals", "mro"}
ESCAPE_GADGETS = {"lipsum", "cycler", "joiner", "self", "config", "request", "url_for", "get_flashed_messages",
                  "__builtins__"}
ATTRIBUTE_FILTERS = {"map", "selectattr", "rejectattr", "groupby", "sort", "unique", "min", "max", "sum", "join"}
FORMAT_FIELD_ACCESS = re.compile(r"\{[^{}]*[.\[][^{}]*\}")  # '{0.__class__}' / '{0[x]}' in str.format


class _Malformed(Exception):
    pass


def _gguf_metadata_strings(data: bytes) -> list[tuple[str, str]]:
    """String values of the GGUF v2/v3 key-value metadata. Raises _Malformed on any structural problem."""
    if len(data) < 24 or not data.startswith(b"GGUF"):
        raise _Malformed("no GGUF header")
    version, tensor_count, kv_count = struct.unpack_from("<IQQ", data, 4)
    if version not in (2, 3) or tensor_count >= 1_000_000 or kv_count >= 1_000_000:
        raise _Malformed(f"implausible GGUF header (version {version})")
    off = 24

    def take(n: int) -> int:
        nonlocal off
        if n < 0 or off + n > len(data):
            raise _Malformed("GGUF metadata runs past the end of the file")
        start, off = off, off + n
        return start

    def read_u(fmt: str) -> int:
        return struct.unpack_from(fmt, data, take(struct.calcsize(fmt)))[0]

    def read_str() -> str:
        n = read_u("<Q")
        start = take(n)
        return data[start : start + n].decode("utf-8", errors="replace")

    def skip(value_type: int, depth: int = 0) -> None:
        if value_type in GGUF_FIXED_SIZES:
            take(GGUF_FIXED_SIZES[value_type])
        elif value_type == GGUF_STRING:
            read_str()
        elif value_type == GGUF_ARRAY and depth < 4:
            item_type, count = read_u("<I"), read_u("<Q")
            if item_type in GGUF_FIXED_SIZES:
                take(count * GGUF_FIXED_SIZES[item_type])
            else:
                for _ in range(count):  # each item consumes bytes, so a lying count runs out of data
                    skip(item_type, depth + 1)
        else:
            raise _Malformed(f"unknown GGUF value type {value_type}")

    strings = []  # (key, value) pairs in file order; duplicated keys are all kept
    for _ in range(kv_count):
        key = read_str()
        value_type = read_u("<I")
        if value_type == GGUF_STRING:
            strings.append((key, read_str()))
        else:
            skip(value_type)
    return strings


def template_risks(template: str) -> list[tuple[str, str]] | None:
    """(construct, severity) pairs for a Jinja template; None if it doesn't parse. Nothing is rendered."""
    from jinja2 import TemplateSyntaxError, nodes
    from jinja2.sandbox import ImmutableSandboxedEnvironment

    try:
        ast = ImmutableSandboxedEnvironment().parse(template)
    except (TemplateSyntaxError, RecursionError):
        return None

    def private(value) -> bool:
        return isinstance(value, str) and (value.startswith("_") or value in INTERNAL_ATTRIBUTES)

    def private_path(value) -> bool:  # map(attribute="role.__class__") is resolved one dotted part at a time
        return isinstance(value, str) and any(private(part) for part in value.split("."))

    def int_expr(node) -> bool:
        if isinstance(node, nodes.Const):
            return isinstance(node.value, int)
        if isinstance(node, (nodes.Neg, nodes.Pos)):
            return int_expr(node.node)
        if isinstance(node, (nodes.Add, nodes.Sub, nodes.Mul, nodes.FloorDiv, nodes.Mod)):
            return int_expr(node.left) and int_expr(node.right)
        if isinstance(node, nodes.Getattr):  # loop.index0 and friends
            return isinstance(node.node, nodes.Name) and node.node.name == "loop" and not private(node.attr)
        return isinstance(node, nodes.Filter) and node.name == "length"

    def literal_key(node) -> bool:
        if isinstance(node, nodes.Const):
            return isinstance(node.value, int) or (isinstance(node.value, str) and not private(node.value))
        if isinstance(node, nodes.Slice):
            return all(int_expr(part) for part in (node.start, node.stop, node.step) if part is not None)
        return int_expr(node)

    risks = []
    for node in ast.find_all((nodes.Getattr, nodes.Getitem, nodes.Filter, nodes.Name, nodes.Const, nodes.Call)):
        if isinstance(node, nodes.Getattr) and private(node.attr):
            risks.append((f"attribute {node.attr}", "dangerous"))
        elif isinstance(node, nodes.Getitem) and not literal_key(node.arg):
            private_key = isinstance(node.arg, nodes.Const) and private(node.arg.value)
            risks.append(("private subscript" if private_key else "subscript computed at runtime",
                          "dangerous" if private_key else "suspicious"))
        elif isinstance(node, nodes.Filter):
            first = node.args[0] if node.args else None
            if node.name == "attr" or (node.name == "map" and isinstance(first, nodes.Const) and first.value == "attr"):
                risks.append(("attr filter", "dangerous"))
            elif node.name in ATTRIBUTE_FILTERS:
                values = list(node.args) + [kw.value for kw in node.kwargs]
                if node.dyn_args is not None or node.dyn_kwargs is not None or \
                        not all(isinstance(v, nodes.Const) for v in values):
                    risks.append((f"{node.name} filter with a computed attribute", "suspicious"))
                elif any(private_path(v.value) for v in values):
                    risks.append((f"{node.name} filter on a private attribute", "dangerous"))
        elif isinstance(node, nodes.Name) and node.ctx == "load" and node.name in ESCAPE_GADGETS:
            risks.append((f"global {node.name}", "dangerous"))
        elif isinstance(node, nodes.Const) and isinstance(node.value, str) and node.value.startswith("__"):
            risks.append(("dunder string", "dangerous"))
        if isinstance(node, nodes.Getattr) and node.attr in ("format", "format_map"):
            # str.format resolves '{0.__class__}' inside the format string; the bound method can be stored in a
            # variable and called later, so the attribute itself is the risk (real templates never use it)
            risks.append(("str.format", "suspicious"))
        if isinstance(node, nodes.Const) and isinstance(node.value, str) and "_" in node.value and \
                FORMAT_FIELD_ACCESS.search(node.value):
            risks.append(("format string with field access", "dangerous"))
    return risks


def _scan_gguf(name: str, data: bytes) -> dict:
    try:
        metadata = _gguf_metadata_strings(data)
    except (_Malformed, struct.error) as exc:
        return _report(name, data, "unknown", "unknown", note=f"malformed gguf: {exc}")
    imports, unparseable = [], []
    for key, template in metadata:  # every value: a duplicated key must not hide an earlier template
        if "chat_template" not in key:
            continue
        risks = template_risks(template)
        if risks is None:
            unparseable.append(key)
        imports += [{"module": key, "name": risk, "severity": severity}
                    for risk, severity in dict.fromkeys(risks or [])]
    severities = {i["severity"] for i in imports}
    if severities:
        verdict = "dangerous" if "dangerous" in severities else "suspicious"
        return _report(name, data, "gguf", verdict, imports,
                       "chat template can reach Python internals (Jinja SSTI, cf. CVE-2024-34359)")
    if unparseable:
        return _report(name, data, "unknown", "unknown", note=f"chat template does not parse: {unparseable}")
    return _report(name, data, "gguf", "safe", note="tensors and metadata; chat templates checked")


def _valid_npy(data: bytes) -> bool:
    """A well-formed .npy; for object arrays (which are pickles) the payload must parse as a pickle too."""
    try:
        f = io.BytesIO(data)
        version = npy_format.read_magic(f)
        if version == (1, 0):
            _, _, dtype = npy_format.read_array_header_1_0(f)
        elif version == (2, 0):
            _, _, dtype = npy_format.read_array_header_2_0(f)
        else:
            return False
        return _parses_as_pickle(data[f.tell():]) if dtype.hasobject else True
    except Exception:
        return False


def classify_repo_file(name: str) -> str:
    """'scan', 'benign', or the reason a repo file is reported as unknown without being scanned."""
    lower = name.lower()
    suffix = os.path.splitext(lower)[1]
    if lower.endswith(PICKLE_SUFFIXES):
        return "scan"
    if suffix in BENIGN_REPO_SUFFIXES or os.path.basename(lower) in BENIGN_REPO_NAMES:
        return "benign"
    if suffix == ".py":
        return "custom code (executed with trust_remote_code), not scanned"
    if suffix in UNSCANNABLE_SUFFIXES:
        return f"{suffix} can execute code on load and is not scanned"
    return "unrecognized file type, not scanned"


def unscanned_report(name: str, note: str) -> dict:
    return {"name": name, "format": "unknown", "verdict": "unknown", "imports": [], "note": note, "sha256": None}


def _check_archive_budget(data: bytes, is_zip: bool, max_unpacked: int) -> None:
    if is_zip:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            sizes = [i.file_size for i in zf.infolist()]  # reads are bounded by these declared sizes
    elif data.startswith(SEVENZ_MAGIC):
        import py7zr

        with py7zr.SevenZipFile(io.BytesIO(data)) as archive:
            infos = [i for i in archive.list() if not i.is_directory]
        if any(i.uncompressed is None for i in infos):  # an undeclared size can't be budgeted
            raise ScanLimitError("7z archive does not declare member sizes")
        sizes = [i.uncompressed for i in infos]
    else:
        return
    if len(sizes) > MAX_ARCHIVE_MEMBERS:
        raise ScanLimitError(f"archive has {len(sizes)} members, limit {MAX_ARCHIVE_MEMBERS}")
    if sum(sizes) > max_unpacked:
        raise ScanLimitError(f"archive unpacks to {sum(sizes)} bytes, limit {max_unpacked}")


def _scan_zip(name: str, data: bytes) -> tuple[ScanResult, list[str]]:
    """Scan zip members one by one instead of through picklescan's zip path, which silently skips unreadable
    members, ignores nested archives, and can abort the whole scan on one malformed member (letting junk
    turn a malicious verdict into unknown). Every pickle member is scanned for globals even when other
    members are broken; members we could not verify are returned as `bad`."""
    result, bad = ScanResult([]), []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            member_id = f"{name}:{info.filename}"
            suffix = os.path.splitext(info.filename.lower())[1]
            try:
                member = zf.read(info)  # full read checks CRC and truncation; bounded by the archive budget
            except Exception:
                bad.append(info.filename)
                continue
            if suffix in NESTED_ARCHIVE_SUFFIXES or member.startswith((ZIP_MAGIC, SEVENZ_MAGIC)):
                bad.append(info.filename)  # not looked into
                continue
            if member.startswith(NUMPY_MAGIC) or suffix == ".npy":
                if not _valid_npy(member):
                    bad.append(info.filename)
                    continue
                result.merge(scan_numpy(io.BytesIO(member), member_id))
                continue
            looks_pickle = member.startswith(PICKLE_MAGIC) or suffix in PICKLE_MEMBER_SUFFIXES
            parses = _parses_as_pickle(member)
            # Scan anything that parses as a pickle, whatever its name: protocol 0/1 pickles have no magic,
            # and zip parser differentials (local vs central directory names) can disguise data.pkl.
            if looks_pickle or parses:
                # globals found before a parse error are still reported (a truncated malicious pickle)
                result.merge(scan_pickle_bytes(io.BytesIO(member), member_id))
            if looks_pickle and not parses:
                bad.append(info.filename)
            # anything else is raw tensor storage, which loaders never deserialize
    return result, bad


def _scan_7z(name: str, data: bytes) -> tuple[ScanResult, list[str], int]:
    """picklescan only extracts pickle-named 7z members and calls unparseable ones clean. 7z is not a format
    model loaders open directly, so every member must be a parseable pickle; anything else is unverified."""
    import py7zr

    result, bad = ScanResult([]), []
    with py7zr.SevenZipFile(io.BytesIO(data)) as archive, tempfile.TemporaryDirectory() as tmp:
        members = [i.filename for i in archive.list() if not i.is_directory]
        archive.extractall(path=tmp)
        root = Path(tmp).resolve()
        for member in members:
            path = (root / member).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                bad.append(member)
                continue
            content = path.read_bytes()
            if not _parses_as_pickle(content):
                bad.append(member)
                continue
            result.merge(scan_pickle_bytes(io.BytesIO(content), f"{name}:{member}"))
    return result, bad, len(members)


def scan_bytes(name: str, data: bytes, max_unpacked: int = DEFAULT_MAX_UNPACKED) -> dict:
    """Report format is one of pickle | pytorch_zip | safetensors | gguf | unknown (as in the proto)."""
    try:
        return _scan(name, data, max_unpacked)
    except ScanLimitError as exc:
        return _report(name, data, "unknown", "unknown", note=str(exc))
    except Exception as exc:
        # Fail closed for hostile input, but log loudly: a bug here would otherwise hide as "unknown".
        log.exception("scan of %s raised", name)
        return _report(name, data, "unknown", "unknown", note=f"could not parse: {type(exc).__name__}: {exc}")


def _worst(reports: list[dict]) -> dict:
    """Combine the views of a polyglot file: the most severe verdict wins, all findings are kept."""
    worst = min(reports, key=lambda r: VERDICT_ORDER.index(r["verdict"]))
    imports = [i for r in reports for i in r["imports"]]
    notes = "; ".join(r["note"] for r in reports if r["note"])
    return {**worst, "imports": imports, "note": notes or None}


def _scan(name: str, data: bytes, max_unpacked: int) -> dict:
    is_pickle = _parses_as_pickle(data)
    if data.startswith(b"GGUF"):
        gguf = _scan_gguf(name, data)
        # a file that is also a pickle is loaded by pickle loaders too: both views must be clean
        return _worst([gguf, _scan_pickle(name, data, max_unpacked, is_pickle)]) if is_pickle else gguf
    if not is_pickle:
        if _is_safetensors(data):
            return _report(name, data, "safetensors", "safe", note="safetensors cannot execute code")
        if name.lower().endswith((".gguf", ".safetensors")):
            return _report(name, data, "unknown", "unknown", note="invalid gguf/safetensors structure")
    return _scan_pickle(name, data, max_unpacked, is_pickle)


def _scan_pickle(name: str, data: bytes, max_unpacked: int, is_pickle: bool) -> dict:
    is_zip = zipfile.is_zipfile(io.BytesIO(data))
    is_7z = data.startswith(SEVENZ_MAGIC)
    is_npy = data.startswith(NUMPY_MAGIC)
    is_container = is_zip or is_7z or is_npy
    _check_archive_budget(data, is_zip, max_unpacked)

    bad: list[str] = []
    if is_zip:
        result, bad = _scan_zip(name, data)
    elif is_7z:
        result, bad, members = _scan_7z(name, data)
        if not members:
            bad = ["<empty archive>"]
    elif is_npy and not _valid_npy(data):
        return _report(name, data, "unknown", "unknown", note="malformed .npy")
    else:
        result = picklescan_bytes(io.BytesIO(data), name, os.path.splitext(name)[1].lower() or None)
    if is_pickle and is_container:  # polyglot: the container view above didn't look at the leading pickle
        result.merge(scan_pickle_bytes(io.BytesIO(data), name))

    imports, seen = [], set()
    for g in result.globals:
        if (g.module, g.name) not in seen:
            seen.add((g.module, g.name))
            imports.append({"module": g.module, "name": g.name, "severity": SEVERITY[g.safety]})
    fmt = "pytorch_zip" if is_zip else "pickle"
    severities = {i["severity"] for i in imports}
    # Flagged globals win over everything below: junk members must not downgrade "dangerous" to "unknown".
    if "dangerous" in severities or "suspicious" in severities:
        verdict = "dangerous" if "dangerous" in severities else "suspicious"
        return _report(name, data, fmt, verdict, imports)

    # Nothing flagged: only "safe" if we actually understood all of it (picklescan calls unparseable input clean).
    if bad:
        return _report(name, data, "unknown", "unknown", imports, f"unverified archive members: {bad[:5]}")
    if result.scan_err or result.scanned_files == 0:
        return _report(name, data, "unknown", "unknown", imports, "no parseable pickle content")
    if not is_container and not is_pickle:
        return _report(name, data, "unknown", "unknown", imports, "could not parse as pickle")
    # picklescan's legacy-torch path stops at a parse error without reporting it, so whatever follows is never
    # checked: all five pickles must parse in full (pickletools and torch reading the same bytes the same way)
    if data.startswith(LEGACY_TORCH_MAGIC) and _complete_pickles(data, LEGACY_TORCH_PICKLES) < LEGACY_TORCH_PICKLES:
        return _report(name, data, "unknown", "unknown", imports, "legacy torch file with unparseable pickles")
    return _report(name, data, fmt, "safe", imports)


def summarize(reports: list[dict]) -> dict:
    # Nothing scanned proves nothing: an empty report is unknown, never safe.
    verdict = next((v for v in VERDICT_ORDER if any(r["verdict"] == v for r in reports)), "unknown")
    dangerous = [f'{i["module"]}.{i["name"]}' for r in reports for i in r["imports"] if i["severity"] == "dangerous"]
    return {"safe": verdict == "safe", "verdict": verdict, "dangerous_imports": sorted(set(dangerous)),
            "files": reports}
