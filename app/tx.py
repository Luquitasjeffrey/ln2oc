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
    vsize: int  # virtual size in vbytes (BIP-141: ceil(weight / 4))


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
    for _ in range(n_out):
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
    base_size = len(version) + len(body) + len(locktime)
    vsize = (base_size * 3 + len(raw) + 3) // 4
    return ParsedTx(txid=txid, inputs=inputs, outputs=outputs, vsize=vsize)
