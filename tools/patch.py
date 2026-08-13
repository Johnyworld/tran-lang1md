#!/usr/bin/env python3
"""배포용 패치 생성 — IPS + BPS. 만든 패치를 **다시 적용해 검증**한다.

패치가 최종 산출물이므로 "만들었다" 로 끝내면 안 된다. 이 도구는 생성 직후 원본에
패치를 적용해 배포판과 바이트 단위로 같은지 확인하고, 다르면 실패한다.

두 형식을 내는 이유
-------------------
```
BPS  원본·결과 CRC32 를 품는다. 롬이 다르면 패처가 거부한다 -> 권장
IPS  구형이지만 어디서나 열린다 (3바이트 오프셋, 16MB 까지)
```

롬이 512KB -> 1MB 로 커지는데 두 형식 모두 문제없다. IPS 는 원본 끝을 넘는 레코드를
그냥 이어 붙이고, BPS 는 결과 크기를 헤더에 적는다.

주의: IPS 는 오프셋이 `0x454F46`("EOF") 인 레코드를 쓸 수 없다. 그 자리에서 시작하는
레코드는 한 바이트 앞으로 당겨 쓴다.
"""
import sys
import zlib
from pathlib import Path

SRC = Path("/Users/rotein/Downloads/Langrisser.md")
ROM = Path("work/korom_all.md")
OUT_IPS, OUT_BPS = Path("work/korom.ips"), Path("work/korom.bps")
IPS_EOF = 0x454F46          # "EOF" 와 겹치는 오프셋
IPS_MAX = 0xFFFF            # 레코드 최대 길이
RLE_MIN = 9                 # 이 길이 이상 같은 바이트면 RLE 가 이득


# ------------------------------------------------------------------------- IPS
def diff_runs(src: bytes, dst: bytes) -> list[tuple[int, bytes]]:
    """달라진 구간 목록. 원본보다 길어진 뒷부분도 한 구간으로 포함한다."""
    runs, i, n = [], 0, len(dst)
    while i < n:
        same = i < len(src) and src[i] == dst[i]
        if same:
            i += 1
            continue
        j = i
        while j < n and not (j < len(src) and src[j] == dst[j]):
            j += 1
        runs.append((i, dst[i:j]))
        i = j
    return runs


def build_ips(src: bytes, dst: bytes) -> bytes:
    out = bytearray(b"PATCH")
    for off, data in diff_runs(src, dst):
        p = 0
        while p < len(data):
            # 같은 바이트가 길게 이어지면 RLE 레코드
            run = 1
            while p + run < len(data) and data[p + run] == data[p]:
                run += 1
            if run >= RLE_MIN:
                at = off + p
                if at == IPS_EOF:                 # "EOF" 오프셋은 못 쓴다
                    out += (at - 1).to_bytes(3, "big") + b"\x00\x01" + dst[at - 1:at]
                    at, run = at, run             # 다음 레코드가 이어서 처리
                    out += at.to_bytes(3, "big")
                else:
                    out += at.to_bytes(3, "big")
                while run:
                    take = min(run, IPS_MAX)
                    out += b"\x00\x00" + take.to_bytes(2, "big") + data[p:p + 1]
                    run -= take
                    p += take
                    if run:
                        out += (off + p).to_bytes(3, "big")
                continue
            # 보통 레코드 — 다음 RLE 시작 전까지
            q = p
            while q < len(data) and q - p < IPS_MAX:
                r = 1
                while q + r < len(data) and data[q + r] == data[q]:
                    r += 1
                if r >= RLE_MIN and q > p:
                    break
                q += max(r, 1) if r < RLE_MIN else r
                if r >= RLE_MIN:
                    break
            q = min(q, p + IPS_MAX)
            at = off + p
            if at == IPS_EOF:
                at -= 1
                chunk = dst[at:off + q]
            else:
                chunk = data[p:q]
            out += at.to_bytes(3, "big") + len(chunk).to_bytes(2, "big") + chunk
            p = q
    return bytes(out + b"EOF")


def apply_ips(src: bytes, patch: bytes) -> bytes:
    assert patch[:5] == b"PATCH", "IPS 헤더가 아니다"
    out, p = bytearray(src), 5
    while patch[p:p + 3] != b"EOF":
        off = int.from_bytes(patch[p:p + 3], "big")
        size = int.from_bytes(patch[p + 3:p + 5], "big")
        p += 5
        if size == 0:                                     # RLE
            n = int.from_bytes(patch[p:p + 2], "big")
            data = patch[p + 2:p + 3] * n
            p += 3
        else:
            data = patch[p:p + size]
            p += size
        if off + len(data) > len(out):
            out += b"\x00" * (off + len(data) - len(out))
        out[off:off + len(data)] = data
    return bytes(out)


# ------------------------------------------------------------------------- BPS
def vint(n: int) -> bytes:
    """BPS 가변길이 정수 — 7비트씩, 마지막 바이트에 0x80."""
    out = bytearray()
    while True:
        x = n & 0x7F
        n >>= 7
        if not n:
            out.append(0x80 | x)
            return bytes(out)
        out.append(x)
        n -= 1


def build_bps(src: bytes, dst: bytes) -> bytes:
    """선형 인코더. 같은 구간은 SourceRead, 다른 구간은 TargetRead 로 낸다.

    같은 바이트가 이어지는 곳(대부분 0 패딩)은 한 바이트만 싣고 **TargetCopy** 로
    자기 자신을 되읽어 늘린다 — 이것 없이는 확장 영역의 0 이 그대로 실린다.
    """
    body = bytearray()
    i, n, tgt_rel = 0, len(dst), 0
    lit = bytearray()

    def flush_lit() -> None:
        if lit:
            body.extend(vint(((len(lit) - 1) << 2) | 1))    # TargetRead
            body.extend(lit)
            lit.clear()

    while i < n:
        # 1) 원본과 같은 구간
        j = i
        while j < n and j < len(src) and src[j] == dst[j]:
            j += 1
        if j > i:
            flush_lit()
            body.extend(vint(((j - i - 1) << 2) | 0))       # SourceRead
            i = j
            continue
        # 2) 같은 바이트 반복 구간
        j = i + 1
        while j < n and dst[j] == dst[i] and not (j < len(src) and src[j] == dst[j]):
            j += 1
        if j - i >= 4:
            lit.append(dst[i])
            flush_lit()
            src_off = i                                     # 방금 쓴 한 바이트
            rel = src_off - tgt_rel
            body.extend(vint(((j - i - 1 - 1) << 2) | 3))    # TargetCopy
            body.extend(vint((abs(rel) << 1) | (1 if rel < 0 else 0)))
            tgt_rel = src_off + (j - i - 1)
            i = j
            continue
        # 3) 낱개 리터럴
        lit.append(dst[i])
        i += 1
    flush_lit()

    head = bytearray(b"BPS1")
    head += vint(len(src)) + vint(len(dst)) + vint(0)
    patch = bytes(head) + bytes(body)
    patch += zlib.crc32(src).to_bytes(4, "little")
    patch += zlib.crc32(dst).to_bytes(4, "little")
    return patch + zlib.crc32(patch).to_bytes(4, "little")


def apply_bps(src: bytes, patch: bytes) -> bytes:
    assert patch[:4] == b"BPS1", "BPS 헤더가 아니다"
    p = 4

    def rd() -> int:
        nonlocal p
        val, shift = 0, 0
        while True:
            b = patch[p]
            p += 1
            val += (b & 0x7F) << shift
            if b & 0x80:
                return val
            shift += 7
            val += 1 << shift

    src_size, tgt_size, meta = rd(), rd(), rd()
    assert src_size == len(src), f"원본 크기 불일치 {src_size} != {len(src)}"
    p += meta
    out = bytearray()
    src_rel = tgt_rel = 0
    end = len(patch) - 12
    while p < end:
        cmd = rd()
        length, action = (cmd >> 2) + 1, cmd & 3
        if action == 0:                                   # SourceRead
            out += src[len(out):len(out) + length]
        elif action == 1:                                 # TargetRead
            out += patch[p:p + length]
            p += length
        elif action == 2:                                 # SourceCopy
            d = rd()
            src_rel += (-1 if d & 1 else 1) * (d >> 1)
            out += src[src_rel:src_rel + length]
            src_rel += length
        else:                                             # TargetCopy
            d = rd()
            tgt_rel += (-1 if d & 1 else 1) * (d >> 1)
            for _ in range(length):
                out.append(out[tgt_rel])
                tgt_rel += 1
    assert len(out) == tgt_size, f"결과 크기 불일치 {len(out)} != {tgt_size}"
    want_src, want_tgt = (int.from_bytes(patch[end + i:end + i + 4], "little")
                          for i in (0, 4))
    assert zlib.crc32(src) == want_src, "원본 CRC 불일치"
    assert zlib.crc32(bytes(out)) == want_tgt, "결과 CRC 불일치"
    return bytes(out)


def main() -> None:
    src, dst = SRC.read_bytes(), ROM.read_bytes()
    if int.from_bytes(dst[0x18E:0x190], "big") == 0:
        raise SystemExit("체크섬 우회가 남아 있다 — python3 tools/build_all.py --release 로 빌드할 것")
    if b"DEBUG" in dst[0x1C8:0x1E8]:
        raise SystemExit("디버그 롬이다 — 배포 빌드로 패치를 만들 것")

    for name, build, apply_ in (("IPS", build_ips, apply_ips), ("BPS", build_bps, apply_bps)):
        patch = build(src, dst)
        got = apply_(src, patch)
        if got != dst:
            bad = next(i for i in range(min(len(got), len(dst))) if got[i] != dst[i])
            raise SystemExit(f"{name} 검증 실패 — 첫 불일치 {bad:06X}")
        out = OUT_IPS if name == "IPS" else OUT_BPS
        out.write_bytes(patch)
        print(f"{name}  {out}  {len(patch):,}B  (적용 후 배포판과 일치 확인)")

    print(f"\n원본   {SRC.name}  {len(src):,}B  CRC32 {zlib.crc32(src):08X}")
    print(f"패치본 {ROM.name}  {len(dst):,}B  CRC32 {zlib.crc32(dst):08X}")


if __name__ == "__main__":
    main()
