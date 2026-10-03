import collections
import io
import os
import pickle
import pickletools
import struct
import zipfile

import pytest

from app.model_scan import scan_bytes, summarize


class Exploit:
    def __reduce__(self):
        return (os.system, ("echo pwned",))


class EvalExploit:
    def __reduce__(self):
        return (eval, ("__import__('os').system('id')",))


def verdict(name: str, data: bytes) -> str:
    return summarize([scan_bytes(name, data)])["verdict"]


def unknown_because(name: str, data: bytes) -> str:
    """The note of an `unknown` verdict; a scanner crash must not pass as an intended unknown."""
    report = scan_bytes(name, data)
    assert report["verdict"] == "unknown", report
    assert not (report["note"] or "").startswith("could not parse:"), report["note"]
    return report["note"]


def test_benign_pickle_is_safe():
    data = pickle.dumps(collections.OrderedDict(weights=[1.0, 2.0], meta={"epoch": 3}), protocol=4)
    assert verdict("model.pkl", data) == "safe"


def test_os_system_is_dangerous_in_every_protocol():
    for protocol in range(0, pickle.HIGHEST_PROTOCOL + 1):
        result = summarize([scan_bytes("evil.pkl", pickle.dumps(Exploit(), protocol=protocol))])
        assert result["verdict"] == "dangerous", protocol
        assert any(i["name"] == "system" for i in result["files"][0]["imports"])


def test_builtins_eval_is_dangerous():
    assert verdict("evil.pkl", pickle.dumps(EvalExploit(), protocol=4)) == "dangerous"


def test_unknown_class_is_suspicious():
    data = pickle.dumps(Exploit, protocol=4)  # reference to a class in an unknown module
    assert verdict("x.pkl", data) == "suspicious"


def test_pytorch_style_zip_with_malicious_data_pkl():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("archive/data.pkl", pickle.dumps(Exploit(), protocol=2))
        zf.writestr("archive/version", "3")
    result = summarize([scan_bytes("pytorch_model.bin", buf.getvalue())])
    assert result["verdict"] == "dangerous"
    assert result["safe"] is False
    assert "posix.system" in result["dangerous_imports"]


def test_safetensors_is_safe():
    header = b'{"w":{"dtype":"F32","shape":[1],"data_offsets":[0,4]}}'
    data = struct.pack("<Q", len(header)) + header + b"\x00" * 4
    assert verdict("model.safetensors", data) == "safe"


def test_garbage_is_unknown_not_safe():
    assert unknown_because("weights.bin", b"\x00\x01garbage") == "could not parse as pickle"


# --- review findings: each test is the attack that used to pass ---------------------------------------------

def gguf_header(tensors=1, kvs=1) -> bytes:
    return b"GGUF" + struct.pack("<IQQ", 3, tensors, kvs)


def test_valid_gguf_is_safe():
    result = scan_bytes("model.gguf", gguf_header() + b"\x00" * 64)
    assert (result["format"], result["verdict"]) == ("gguf", "safe")


def test_pickle_disguised_as_gguf_is_scanned():
    polyglot = b"GGUF" + b"\0" * 5 + b"0" + pickle.dumps(Exploit(), protocol=2)
    assert verdict("model.gguf", polyglot) == "dangerous"


def test_pickle_with_zip_appended_is_scanned():
    # picklescan sees a clean zip (it finds the trailing directory); torch.load would run the leading pickle
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("archive/data.pkl", pickle.dumps({"ok": 1}, protocol=2))
    assert verdict("model.pt", pickle.dumps(Exploit(), protocol=2) + buf.getvalue()) == "dangerous"


def test_zip_bomb_is_refused_before_extraction():
    payload = pickle.dumps(b"\0" * 8_000_000, protocol=4)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("archive/data.pkl", payload)
    assert len(buf.getvalue()) < 20_000
    result = scan_bytes("bomb.pt", buf.getvalue(), max_unpacked=1_000_000)
    assert result["verdict"] == "unknown" and "unpacks to" in result["note"]


@pytest.mark.parametrize("member", [b"\x00\x01garbage", pickle.dumps(Exploit(), protocol=2)[:5]])
def test_unreadable_zip_member_is_unknown(member):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("archive/data.pkl", member)
    assert "data.pkl" in unknown_because("model.pt", buf.getvalue())


def test_npy_parser_crash_is_unknown_with_hash():
    result = scan_bytes("a.npy", b"\x93NUMPY")
    assert result["verdict"] == "unknown" and len(result["sha256"]) == 64


def test_7z_archive_is_scanned(tmp_path):
    import py7zr

    (tmp_path / "data.pkl").write_bytes(pickle.dumps(Exploit(), protocol=2))
    archive = tmp_path / "model.7z"
    with py7zr.SevenZipFile(archive, "w") as z:
        z.write(tmp_path / "data.pkl", "data.pkl")
    assert verdict("model.7z", archive.read_bytes()) == "dangerous"


# --- review round 2 ----------------------------------------------------------------------------------------

from app.model_scan import classify_repo_file


def npy_bytes(obj_payload: bytes | None = None) -> bytes:
    import numpy as np

    buf = io.BytesIO()
    np.save(buf, np.arange(4) if obj_payload is None else np.array([{"a": 1}], dtype=object), allow_pickle=True)
    data = buf.getvalue()
    if obj_payload is not None:  # replace the pickled payload after the header
        header_end = data.index(b"\n") + 1
        data = data[:header_end] + obj_payload
    return data


def zip_of(**members: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in members.items():
            zf.writestr(name.replace("__", "/"), content)
    return buf.getvalue()


def test_numpy_object_array_with_garbage_payload_is_unknown():
    assert unknown_because("a.npy", npy_bytes(obj_payload=b"\x00garbage")) == "malformed .npy"


def test_plain_numpy_array_is_safe():
    assert verdict("a.npy", npy_bytes()) == "safe"


def test_npz_with_broken_npy_member_is_unknown():
    assert "a.npy" in unknown_because("w.npz", zip_of(**{"a.npy": b"\x93NUMPY"}))


def test_nested_archive_member_is_unknown():
    inner = zip_of(**{"data.pkl": pickle.dumps(Exploit(), protocol=2)})
    assert "inner.zip" in unknown_because("m.zip", zip_of(**{"inner.zip": inner}))


def test_raw_tensor_file_starting_with_0x80_is_not_a_false_positive():
    good = zip_of(**{"archive__data.pkl": pickle.dumps(collections.OrderedDict(w=1), protocol=2),
                     "archive__data__0": b"\x80\x90\x00\x00" * 16})  # float bytes, not a pickle
    assert verdict("model.pt", good) == "safe"


def seven_zip(tmp_path, **members: bytes) -> bytes:
    import py7zr

    archive = tmp_path / "m.7z"
    with py7zr.SevenZipFile(archive, "w") as z:
        for name, content in members.items():
            z.writestr(content, name)
    return archive.read_bytes()


def test_7z_with_unscanned_member_is_unknown(tmp_path):
    data = seven_zip(tmp_path, **{"data.pkl": pickle.dumps({"ok": 1}), "weights.h5": b"\x89HDF\r\n"})
    assert "weights.h5" in unknown_because("m.7z", data)


def test_7z_with_garbage_pickle_is_unknown(tmp_path):
    assert "data.pkl" in unknown_because("m.7z", seven_zip(tmp_path, **{"data.pkl": b"\x00garbage"}))


def test_7z_with_clean_pickles_is_safe(tmp_path):
    assert verdict("m.7z", seven_zip(tmp_path, **{"data.pkl": pickle.dumps(collections.OrderedDict(a=1))})) == "safe"


def test_empty_report_is_never_safe():
    assert summarize([]) | {"files": None} == {"safe": False, "verdict": "unknown", "dangerous_imports": [],
                                               "files": None}


@pytest.mark.parametrize("name,kind", [
    ("pytorch_model.BIN", "scan"), ("model.Safetensors", "scan"), ("config.json", "benign"),
    ("LICENSE", "benign"), ("tf_model.h5", "unknown"), ("modeling_evil.py", "unknown"),
    ("weights.xyz", "unknown"), ("Dockerfile", "unknown"),
])
def test_repo_file_classification(name, kind):
    result = classify_repo_file(name)
    assert (result if result in ("scan", "benign") else "unknown") == kind


def test_junk_member_cannot_downgrade_malicious_to_unknown():
    data = zip_of(**{"archive__data.pkl": pickle.dumps(Exploit(), protocol=2), "junk.pkl": b"\x00garbage",
                     "broken.npy": b"\x93NUMPY"})
    assert verdict("model.pt", data) == "dangerous"


def test_truncated_malicious_pickle_still_reports_its_globals():
    evil = pickle.dumps(Exploit(), protocol=0)  # GLOBAL 'posix system' comes first, then the arguments
    truncated = evil[: evil.index(b"system") + len(b"system\n") + 2]
    assert verdict("model.pt", zip_of(**{"archive__data.pkl": truncated})) == "dangerous"


# --- review round 2, own pass ----------------------------------------------------------------------------

def gguf_file(**metadata: str) -> bytes:
    def gguf_str(value: str) -> bytes:
        raw = value.encode()
        return struct.pack("<Q", len(raw)) + raw

    kvs = b"".join(gguf_str(k) + struct.pack("<I", 8) + gguf_str(v) for k, v in metadata.items())
    return b"GGUF" + struct.pack("<IQQ", 3, 0, len(metadata)) + kvs + b"\x00" * 32


LLAMA3_TEMPLATE = ("{% for message in messages %}<|start_header_id|>{{ message['role'] }}<|end_header_id|>\n\n"
                   "{{ message['content'] | trim }}<|eot_id|>{% endfor %}")
# The CVE-2024-34359 payload shape: walk from a string to os.popen through Python internals.
SSTI_TEMPLATE = ("{% for x in ().__class__.__base__.__subclasses__() %}{% if 'warning' in x.__name__ %}"
                 "{{ x()._module.__builtins__['__import__']('os').popen('id').read() }}{% endif %}{% endfor %}")


def test_gguf_with_normal_chat_template_is_safe():
    result = scan_bytes("llama.gguf", gguf_file(**{"general.name": "llama", "tokenizer.chat_template": LLAMA3_TEMPLATE}))
    assert (result["format"], result["verdict"]) == ("gguf", "safe")


def test_gguf_with_ssti_chat_template_is_malicious():
    result = scan_bytes("evil.gguf", gguf_file(**{"tokenizer.chat_template": SSTI_TEMPLATE}))
    assert result["verdict"] == "dangerous" and "CVE-2024-34359" in result["note"]


def test_gguf_with_lying_metadata_count_is_unknown():
    data = b"GGUF" + struct.pack("<IQQ", 3, 0, 500) + b"\x00" * 64  # claims 500 entries, has none
    assert unknown_because("x.gguf", data).startswith("malformed gguf")


def test_protocol0_pickle_with_innocent_member_name_is_scanned():
    # no 0x80 magic and no .pkl suffix: a name/magic-based member filter would skip it
    evil_p0 = pickle.dumps(Exploit(), protocol=0)
    assert not evil_p0.startswith(b"\x80")
    assert verdict("model.pt", zip_of(**{"archive__data__7": evil_p0})) == "dangerous"


# --- GGUF chat templates: AST analysis instead of word matching ----------------------------------------------

import pathlib

REAL_TEMPLATES = sorted((pathlib.Path(__file__).parent / "fixtures" / "chat_templates").glob("*.jinja"))


@pytest.mark.parametrize("path", REAL_TEMPLATES, ids=lambda p: p.stem)
def test_real_chat_templates_are_not_flagged(path):
    # Fetched from the models' tokenizer_config.json on Hugging Face. All of them contain the word "system";
    # a word-matching scanner would flag every legitimate model.
    result = scan_bytes("model.gguf", gguf_file(**{"tokenizer.chat_template": path.read_text()}))
    assert (result["format"], result["verdict"]) == ("gguf", "safe"), result["imports"]


@pytest.mark.parametrize("template", [
    SSTI_TEMPLATE,                                                                    # CVE-2024-34359 shape
    "{{ ''|attr('__cla' ~ 'ss__') }}",                                                # name built at runtime
    "{% set n = '__glo' ~ 'bals__' %}{{ lipsum[n] }}",                                # gadget + dynamic key
    "{{ cycler.__init__.__globals__.os.popen('id').read() }}",
    "{{ x[('__cl' ~ 'ass__')] }}",
    "{{ messages|map(attribute='__class__')|list }}",
    "{{ (messages|map('upper')).gi_frame.f_back.f_globals }}",                     # generator frame walk
    "{{ joiner().__init__ }}",
])
def test_template_escape_techniques_are_flagged(template):
    assert scan_bytes("evil.gguf", gguf_file(**{"tokenizer.chat_template": template}))["verdict"] == "dangerous"


def test_unparseable_chat_template_is_unknown():
    note = unknown_because("x.gguf", gguf_file(**{"tokenizer.chat_template": "{% for x in %}"}))
    assert "does not parse" in note


@pytest.mark.parametrize("template", [
    # review round 3: confirmed bypasses of the first AST rule
    '{% set k = "__glo" ~ "bals__" %}{{ raise_exception[k] }}',
    '{{ messages|map("attr", "__class__")|list }}',
    '{{ messages|selectattr("__class__")|list }}',
    '{{ x["__cla" + "ss__"] }}',
    '{{ messages|map(**{"attribute": "__class__"})|list }}',
    '{{ x[("_", "_class__")|join] }}',
    # no underscore literal at all: "_" taken from the repr of a function
    '{% set u = (raise_exception|string)[13] %}{{ raise_exception[u ~ u ~ "globals" ~ u ~ u] }}',
    "{{ '{0.__class__.__base__}'.format(messages) }}",                                 # str.format field access
    "{% set f = fmt %}{{ f.format(messages) }}",
])
def test_dynamic_attribute_access_is_never_safe(template):
    result = scan_bytes("evil.gguf", gguf_file(**{"tokenizer.chat_template": template}))
    assert result["verdict"] in ("dangerous", "suspicious"), result


def test_duplicate_chat_template_keys_are_all_checked():
    def gguf_str(value: str) -> bytes:
        return struct.pack("<Q", len(value.encode())) + value.encode()

    entries = [("tokenizer.chat_template", SSTI_TEMPLATE), ("tokenizer.chat_template", LLAMA3_TEMPLATE)]
    kvs = b"".join(gguf_str(k) + struct.pack("<I", 8) + gguf_str(v) for k, v in entries)
    data = b"GGUF" + struct.pack("<IQQ", 3, 0, len(entries)) + kvs
    assert verdict("dup.gguf", data) == "dangerous"


@pytest.mark.parametrize("template", [
    # review round 4: confirmed bypasses
    '{% set f = "{0.__init__.__globals__}".format %}{{ f(messages) }}',
    '{{ messages|map(attribute="role.__class__.__mro__")|list }}',
    '{{ messages|selectattr("x.__init__.__globals__")|list }}',
])
def test_round4_template_bypasses_are_caught(template):
    result = scan_bytes("evil.gguf", gguf_file(**{"tokenizer.chat_template": template}))
    assert result["verdict"] in ("dangerous", "suspicious"), result


# --- review round 5 ----------------------------------------------------------------------------------------

def legacy_torch_file() -> bytes:
    import torch

    buf = io.BytesIO()
    torch.save({"w": torch.ones(3)}, buf, _use_new_zipfile_serialization=False)
    return buf.getvalue()


def test_real_legacy_torch_file_is_safe():
    data = legacy_torch_file()
    assert not data.startswith(b"PK")  # really the legacy format, not a zip
    assert verdict("model.pt", data) == "safe"


def test_legacy_torch_file_with_an_unparseable_pickle_is_unknown():
    data = legacy_torch_file()
    stream = io.BytesIO(data)
    for _ in range(3):  # keep magic, protocol and sys info; corrupt the object pickle right after them
        for _op in pickletools.genops(stream):
            pass
    corrupted = data[: stream.tell()] + b"\xff" + data[stream.tell() + 1 :]
    assert unknown_because("model.pt", corrupted) == "legacy torch file with unparseable pickles"
