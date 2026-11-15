"""The strategy blob embedded in dist/bot.py (BUILDMAP §7 Phase 6, §9.1).

Layout of the raw (decompressed) blob:
    MAGIC (16 bytes) | header length (u32 little-endian) | header (UTF-8 JSON) | payload
The header lists every array: name, dtype, shape, offset into the payload, nbytes; plus free-form
"meta" and the sha256 of the payload. Arrays start on 8-byte boundaries.
Stored form: base64(zlib.compress(raw, 9)). Deterministic: the same arrays and meta give the same bytes.
Standard library + numpy only (it runs inside the bot).
"""
import base64
import hashlib
import json
import struct
import zlib

import numpy as np

MAGIC = b"DHCFR-BLOB-v1\x00\x00\x00"
assert len(MAGIC) == 16


def encode_raw(arrays, meta):
    """arrays: {name: np.ndarray} (kept in insertion order). Returns the raw, uncompressed blob."""
    entries, chunks, offset = [], [], 0
    for name, a in arrays.items():
        a = np.ascontiguousarray(a)
        data = a.tobytes()
        pad = (-offset) % 8
        chunks.append(b"\x00" * pad)
        offset += pad
        entries.append({"name": name, "dtype": a.dtype.str, "shape": list(a.shape),
                        "offset": offset, "nbytes": len(data)})
        chunks.append(data)
        offset += len(data)
    payload = b"".join(chunks)
    header = {"version": 1, "arrays": entries, "meta": meta,
              "payload_sha256": hashlib.sha256(payload).hexdigest()}
    hb = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
    return MAGIC + struct.pack("<I", len(hb)) + hb + payload


def encode_blob(arrays, meta):
    """base64(zlib(raw)) as ASCII bytes."""
    return base64.b64encode(zlib.compress(encode_raw(arrays, meta), 9))


def decode_raw(raw):
    """(header, {name: read-only np.ndarray view into raw}). Raises ValueError on any problem."""
    if raw[:16] != MAGIC:
        raise ValueError("strategy blob: bad magic")
    (hlen,) = struct.unpack("<I", raw[16:20])
    header = json.loads(raw[20:20 + hlen].decode())
    payload = memoryview(raw)[20 + hlen:]
    if hashlib.sha256(payload).hexdigest() != header["payload_sha256"]:
        raise ValueError("strategy blob: payload sha256 mismatch")
    arrays = {}
    for e in header["arrays"]:
        n = e["nbytes"]
        a = np.frombuffer(payload, dtype=np.dtype(e["dtype"]), count=n // np.dtype(e["dtype"]).itemsize,
                          offset=e["offset"])
        arrays[e["name"]] = a.reshape(e["shape"])
    return header, arrays


def decode_blob(b64):
    """Inverse of encode_blob. b64: ASCII bytes or str (newlines are ignored)."""
    try:
        raw = zlib.decompress(base64.b64decode(b64))
    except (ValueError, zlib.error) as e:
        raise ValueError(f"strategy blob: cannot decode ({e})") from None
    return decode_raw(raw)
