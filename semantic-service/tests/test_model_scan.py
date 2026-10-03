import collections
import io
import os
import pickle
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
    assert verdict("weights.bin", b"\x00\x01garbage") == "unknown"


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
    assert verdict("model.pt", buf.getvalue()) == "unknown"


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
