import hashlib
from typing import Tuple, List, Optional
from enum import Enum

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

class Encoding(Enum):
    BECH32 = 1
    BECH32M = 2

def bech32_polymod(values: list[int]) -> int:
    generator = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    chk = 1
    for value in values:
        top = chk >> 25
        chk = (chk & 0x1ffffff) << 5 ^ value
        for i in range(5):
            chk ^= generator[i] if ((top >> i) & 1) else 0
    return chk

def bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]

def bech32_verify_checksum(hrp: str, data: list[int]) -> Optional[Encoding]:
    check = bech32_polymod(bech32_hrp_expand(hrp) + data)
    if check == 1:
        return Encoding.BECH32
    elif check == 0x2bc830a3:
        return Encoding.BECH32M
    return None

def bech32_decode(bech: str) -> Tuple[Optional[str], Optional[list[int]], Optional[Encoding]]:
    if any(ord(x) < 33 or ord(x) > 126 for x in bech):
        return None, None, None
    if bech.lower() != bech and bech.upper() != bech:
        return None, None, None
    bech = bech.lower()
    pos = bech.rfind("1")
    if pos < 1 or pos + 7 > len(bech) or len(bech) > 90:
        return None, None, None
    if not all(x in CHARSET for x in bech[pos + 1:]):
        return None, None, None
    hrp = bech[:pos]
    data = [CHARSET.find(x) for x in bech[pos + 1:]]
    spec = bech32_verify_checksum(hrp, data)
    if spec is None:
        return None, None, None
    return hrp, data[:-6], spec

def convertbits(data: list[int], frombits: int, tobits: int, pad: bool = True) -> Optional[list[int]]:
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            return None
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret

B58_DIGITS = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def _b58decode(v: str) -> Optional[bytes]:
    try:
        val = 0
        for c in v:
            val = val * 58 + B58_DIGITS.index(c)
        res = []
        while val > 0:
            val, mod = divmod(val, 256)
            res.append(mod)
        res = bytes(reversed(res))
        pad = 0
        for c in v:
            if c == '1':
                pad += 1
            else:
                break
        return b'\x00' * pad + res
    except Exception:
        return None

def address_to_script(address: str, network: str = "regtest") -> Optional[bytes]:
    """
    Decodes a Bitcoin address for the given network (mainnet, testnet, regtest) and
    returns its scriptPubKey, or None if the address is invalid for that network.
    Supports:
    - SegWit v0 (P2WPKH/P2WSH, Bech32) and Taproot v1 (P2TR, Bech32m):
      bc1 (mainnet), tb1 (testnet), bcrt1 (regtest)
    - Legacy P2PKH: 1 (mainnet), m or n (testnet/regtest)
    - Legacy P2SH: 3 (mainnet), 2 (testnet/regtest)
    Future witness versions (v2+) are rejected on purpose: we will not pay to
    scripts nobody can spend today.
    """
    if not address or not isinstance(address, str):
        return None
    if address != address.strip():
        return None

    expected_hrp = {
        "mainnet": "bc",
        "testnet": "tb",
        "regtest": "bcrt",
    }.get(network.lower())

    # 1. Bech32 / Bech32m
    if expected_hrp:
        hrp, data, spec = bech32_decode(address)
        if hrp == expected_hrp and data is not None and len(data) > 0:
            witness_version = data[0]
            program = convertbits(data[1:], 5, 8, False)
            if program is not None:
                prog_len = len(program)
                if witness_version == 0 and prog_len in (20, 32) and spec == Encoding.BECH32:
                    return bytes([0x00, prog_len]) + bytes(program)
                if witness_version == 1 and prog_len == 32 and spec == Encoding.BECH32M:
                    return bytes([0x51, prog_len]) + bytes(program)
            return None

    # 2. Base58Check (P2PKH and P2SH)
    decoded = _b58decode(address)
    if decoded and len(decoded) == 25:
        payload = decoded[:-4]
        checksum = decoded[-4:]
        expected_checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
        if checksum == expected_checksum:
            version_byte = payload[0]
            h = payload[1:]
            if network.lower() == "mainnet":
                p2pkh, p2sh = 0x00, 0x05
            else:
                p2pkh, p2sh = 0x6F, 0xC4
            if version_byte == p2pkh:
                return b"\x76\xa9\x14" + h + b"\x88\xac"
            if version_byte == p2sh:
                return b"\xa9\x14" + h + b"\x87"

    return None


def validate_bitcoin_address(address: str, network: str = "regtest") -> bool:
    return address_to_script(address, network) is not None
