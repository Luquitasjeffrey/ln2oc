"""Minimal, strict Bitcoin transaction parser used to verify what LND signed before
we commit to it. Any malformed input raises ValueError."""
import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class TxInput:
    txid: str  # display (big-endian) hex
    vout: int


@dataclass(frozen=True)
class TxOutput:
    value: int
    script: bytes


@dataclass(frozen=True)
class ParsedTx:
    txid: str
    inputs: list[TxInput]
    outputs: list[TxOutput]


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def read(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise ValueError("truncated transaction")
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out

    def u32(self) -> int:
        return int.from_bytes(self.read(4), "little")

    def u64(self) -> int:
        return int.from_bytes(self.read(8), "little")

    def varint(self) -> int:
        first = self.read(1)[0]
        if first < 0xFD:
            return first
        if first == 0xFD:
            return int.from_bytes(self.read(2), "little")
        if first == 0xFE:
            return int.from_bytes(self.read(4), "little")
        return int.from_bytes(self.read(8), "little")


def parse_tx(raw: bytes) -> ParsedTx:
    return _parse(raw)[0]


def _parse(raw: bytes) -> tuple[ParsedTx, list[int], bool]:
    """Returns the parsed tx, the byte offset of each output's 8-byte value, and segwit."""
    r = _Reader(raw)
    version = r.read(4)

    segwit = False
    if r.data[r.pos:r.pos + 2] == b"\x00\x01":
        segwit = True
        r.read(2)

    body_start = r.pos
    n_in = r.varint()
    if n_in == 0:
        raise ValueError("transaction has no inputs")
    inputs = []
    for _ in range(n_in):
        prev = r.read(32)
        vout = r.u32()
        r.read(r.varint())  # scriptSig
        r.read(4)  # sequence
        inputs.append(TxInput(txid=prev[::-1].hex(), vout=vout))

    n_out = r.varint()
    if n_out == 0:
        raise ValueError("transaction has no outputs")
    outputs = []
    value_offsets = []
    for _ in range(n_out):
        value_offsets.append(r.pos)
        value = r.u64()
        script = r.read(r.varint())
        outputs.append(TxOutput(value=value, script=script))
    body = r.data[body_start:r.pos]

    if segwit:
        for _ in range(n_in):
            for _ in range(r.varint()):
                r.read(r.varint())

    locktime = r.read(4)
    if r.pos != len(raw):
        raise ValueError("trailing bytes after transaction")

    txid = hashlib.sha256(hashlib.sha256(version + body + locktime).digest()).digest()[::-1].hex()
    return ParsedTx(txid=txid, inputs=inputs, outputs=outputs), value_offsets, segwit


# --------------------------------------------------------------------------- PSBT (v0)

_PSBT_MAGIC = b"psbt\xff"
_MAX_SAT = 21_000_000 * 100_000_000


def _psbt_unsigned_tx_span(psbt: bytes) -> tuple[int, int]:
    """Byte span of the unsigned tx in a BIP-174 (v0) PSBT's global map."""
    if not psbt.startswith(_PSBT_MAGIC):
        raise ValueError("not a PSBT")
    r = _Reader(psbt)
    r.read(len(_PSBT_MAGIC))
    span = None
    while True:
        key_len = r.varint()
        if key_len == 0:
            break
        key = r.read(key_len)
        value_len = r.varint()
        start = r.pos
        value = r.read(value_len)
        if key == b"\x00":
            if span is not None:
                raise ValueError("PSBT has two unsigned transactions")
            span = (start, start + value_len)
        elif key[0] == 0xFB and int.from_bytes(value, "little") != 0:
            raise ValueError("only PSBT version 0 is supported")
    if span is None:
        raise ValueError("PSBT has no unsigned transaction")
    return span


def psbt_unsigned_tx(psbt: bytes) -> ParsedTx:
    start, end = _psbt_unsigned_tx_span(psbt)
    tx, _, segwit = _parse(psbt[start:end])
    if segwit:
        raise ValueError("PSBT unsigned tx must not carry witnesses")
    return tx


def psbt_set_output_values(psbt: bytes, values: dict[int, int]) -> bytes:
    """Rewrites output amounts of an unsigned PSBT in place. Amounts are fixed 8-byte
    fields, so the size of the tx (and its fee at a given rate) does not change."""
    start, end = _psbt_unsigned_tx_span(psbt)
    _, offsets, segwit = _parse(psbt[start:end])
    if segwit:
        raise ValueError("PSBT unsigned tx must not carry witnesses")
    out = bytearray(psbt)
    for idx, value in values.items():
        if not 0 <= idx < len(offsets):
            raise ValueError(f"PSBT has no output #{idx}")
        if not 0 < value <= _MAX_SAT:
            raise ValueError(f"invalid output value {value}")
        pos = start + offsets[idx]
        out[pos:pos + 8] = value.to_bytes(8, "little")
    return bytes(out)
