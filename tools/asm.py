#!/usr/bin/env python3
"""손으로 어셈블한 68000 코드 조각. capstone 역어셈블로 왕복 검증한다.

어셈블러가 없어 직접 바이트를 적는다. 실수하면 조용히 폭주하므로
반드시 disasm() 으로 의도와 대조할 것.
"""
import struct


def w(v: int) -> bytes:
    return struct.pack(">H", v & 0xFFFF)


def l(v: int) -> bytes:
    return struct.pack(">I", v & 0xFFFFFFFF)


# ---------------------------------------------------------------- 명령 조각
def movea_l_abs_a(addr: int, an: int) -> bytes:
    """movea.l (xxx).l, An"""
    return w(0x2079 | (an << 9)) + l(addr)


def move_l_a_abs(an: int, addr: int) -> bytes:
    """move.l An, (xxx).l"""
    return w(0x23C8 | an) + l(addr)


def move_l_imm_abs(imm: int, addr: int) -> bytes:
    """move.l #imm, (xxx).l"""
    return w(0x23FC) + l(imm) + l(addr)


def lea_abs(addr: int, an: int) -> bytes:
    """lea (xxx).l, An"""
    return w(0x41F9 | (an << 9)) + l(addr)


VDP_CTRL, VDP_DATA = 0xC00004, 0xC00000


def vdp_set_write(dreg: int, areg: int) -> bytes:
    """d{areg} 의 VRAM 주소로 쓰기 설정. d{dreg} 를 스크래치로 쓴다.
    0x54B6 의 게임 코드와 같은 방식."""
    return (
        w(0x3000 | (dreg << 9) | areg)          # move.w dA, dD
        + w(0x0240 | dreg) + w(0x3FFF)          # andi.w #$3FFF, dD
        + w(0x0040 | dreg) + w(0x4000)          # ori.w  #$4000, dD
        + w(0x4840 | dreg)                      # swap   dD
        + w(0x3000 | (dreg << 9) | areg)        # move.w dA, dD
        + w(0x0240 | dreg) + w(0xC000)          # andi.w #$C000, dD
        + w(0xE048 | dreg)                      # lsr.w  #8, dD
        + w(0xEC48 | dreg)                      # lsr.w  #6, dD
        + w(0x23C0 | dreg) + l(VDP_CTRL)        # move.l dD, (VDP_CTRL).l
    )


MARKER = 0xFE


def build_uploader(kfont: int, slot_base: int, p_work: int, resume: int) -> bytes:
    """헤더 마커를 만나면 글리프를 VRAM 슬롯에 올린 뒤 렌더러 본체로 돌아간다.

    메시지 형식:  [0xFE][N: byte][글리프 ID: word x N][텍스트...][0xFF]

    렌더러 진입점(0x15576)에 훅을 거니 글자마다 호출된다. 메시지 시작 판별에
    `$E818 == $E82C` 를 쓰려 했으나 틀렸다 — 인터프리터가 0x1536E 에서 두 값을
    같게 만든 뒤 워드를 읽어가며 포인터를 전진시켜 $E818 에 다시 쓰므로,
    텍스트 렌더 시점에는 이미 두 값이 다르다.

    그래서 우리가 심은 **마커 바이트**로 판별한다. 우리가 만드는 데이터이므로
    확실하고, 0xFE 는 텍스트 코드 범위 밖이라 오탐이 없다. 업로드 후 $E818 이
    마커를 지나가므로 같은 메시지에서 두 번 실행되지 않는다.
    """
    body = bytearray()
    body += movea_l_abs_a(p_work, 0)             # movea.l (E818).l, a0
    body += w(0x0C10) + w(MARKER)                # cmpi.b #$FE, (a0)
    body += w(0x6600) + w(0x0000)                # bne.w  .skip        (뒤에서 채움)
    bne_at = len(body) - 2

    body += w(0x40E7)                            # move.w sr, -(a7)
    body += w(0x46FC) + w(0x2700)                # move.w #$2700, sr   인터럽트 차단
    body += w(0x5288)                            # addq.l #1, a0       마커 건너뛰기
    body += w(0x7E00)                            # moveq #0, d7
    body += w(0x1E18)                            # move.b (a0)+, d7    N
    body += w(0x6700) + w(0x0000)                # beq.w  .store
    beq_at = len(body) - 2
    body += w(0x5347)                            # subq.w #1, d7
    body += w(0x323C) + w(slot_base * 32)        # move.w #slot*32, d1  VRAM 주소
    body += lea_abs(VDP_DATA, 2)                 # lea (C00000).l, a2
    loop_at = len(body)
    body += vdp_set_write(0, 1)                  # d0 스크래치, d1 = 주소
    body += w(0x7400)                            # moveq #0, d2
    body += w(0x3418)                            # move.w (a0)+, d2     글리프 ID
    body += w(0xE58A) + w(0xE58A) + w(0xE38A)    # lsl.l #2,#2,#1 -> x32
    body += lea_abs(kfont, 1)                    # lea KFONT, a1
    body += w(0xD3C2)                            # adda.l d2, a1
    body += w(0x2499) * 8                        # move.l (a1)+, (a2)   32바이트
    body += w(0x0641) + w(0x0020)                # addi.w #32, d1
    body += w(0x51CF) + w((loop_at - (len(body) + 2)) & 0xFFFF)   # dbra d7, loop

    body[beq_at:beq_at + 2] = w(len(body) - (beq_at - 2) - 2)     # .store
    body += move_l_a_abs(0, p_work)              # move.l a0, (E818).l  헤더 뒤로
    body += w(0x46DF)                            # move.w (a7)+, sr

    body[bne_at:bne_at + 2] = w(len(body) - (bne_at - 2) - 2)     # .skip
    body += movea_l_abs_a(p_work, 1)             # movea.l (E818).l, a1  훔친 명령 복원
    body += w(0x4EF9) + l(resume)                # jmp (resume).l
    return bytes(body)


def build_hook(target: int) -> bytes:
    """0x15576 의 첫 명령(movea.l (E818).l, a1 — 6바이트)을 jmp 로 교체한다.

    앞서 0x1556C 에 훅을 걸었으나 그 자리는 죽은 코드였다.
      015560  move.w #$2, d0
      015564  cmpi.w #$2, d0
      015568  beq.w  $15650     <- d0 은 항상 2 이므로 항상 분기
      01556C  ...               <- 도달하지 않는다
    """
    return w(0x4EF9) + l(target)                 # jmp (target).l — 정확히 6바이트


def disasm(code: bytes, base: int) -> list[str]:
    from capstone import Cs, CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_000
    md = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)
    return [f"  {i.address:06X}  {i.bytes.hex():<20} {i.mnemonic:<9} {i.op_str}"
            for i in md.disasm(code, base)]


if __name__ == "__main__":
    code = build_uploader(kfont=0x80200, slot_base=128, renderer=0x15576,
                          p_work=0xFFFFE818, p_state=0xFFFF8010)
    print(f"루틴 {len(code)} bytes\n")
    print("\n".join(disasm(code, 0x80000)))


def build_uploader_a1(kfont: int, slot_base: int, target: int) -> bytes:
    """a1 로 넘어온 문자열의 헤더를 읽어 글리프를 올린 뒤 target 으로 꼬리호출한다.

    프롤로그 렌더러(0x18D2A)의 `jsr $5F60` 을 이 루틴 호출로 바꿔 쓴다.
    주소가 RAM 변수가 아니라 a1 에 직접 실려 오므로 $E818 을 볼 필요가 없다.

    d1..d5 는 $5F60 의 인자이므로 반드시 보존한다. d0 은 $5F60 이 진입 후
    스스로 채우므로 자유롭게 쓴다.
    """
    body = bytearray()
    body += w(0x0C11) + w(MARKER)                # cmpi.b #$FE, (a1)
    body += w(0x6600) + w(0x0000)                # bne.w .out
    bne_at = len(body) - 2

    body += w(0x48E7) + w(0xFFF0)                # movem.l d0-d7/a0-a3, -(a7)
    body += w(0x40E7)                            # move.w sr, -(a7)
    body += w(0x46FC) + w(0x2700)                # move.w #$2700, sr
    body += w(0x2049)                            # movea.l a1, a0
    body += w(0x5288)                            # addq.l #1, a0        마커 건너뛰기
    body += w(0x7E00)                            # moveq #0, d7
    body += w(0x1E18)                            # move.b (a0)+, d7     N
    body += w(0x6700) + w(0x0000)                # beq.w .rest
    beq_at = len(body) - 2
    body += w(0x5347)                            # subq.w #1, d7
    body += w(0x323C) + w(slot_base * 32)        # move.w #slot*32, d1
    body += lea_abs(VDP_DATA, 2)                 # lea (C00000).l, a2
    loop_at = len(body)
    body += vdp_set_write(0, 1)                  # d0 스크래치, d1 = VRAM 주소
    body += w(0x7400)                            # moveq #0, d2
    body += w(0x3418)                            # move.w (a0)+, d2     글리프 ID
    body += w(0xE58A) + w(0xE58A) + w(0xE38A)    # lsl.l #2,#2,#1 -> x32
    body += lea_abs(kfont, 3)                    # lea KFONT, a3
    body += w(0xD7C2)                            # adda.l d2, a3
    body += w(0x249B) * 8                        # move.l (a3)+, (a2)   32바이트
    body += w(0x0641) + w(0x0020)                # addi.w #32, d1
    body += w(0x51CF) + w((loop_at - (len(body) + 2)) & 0xFFFF)   # dbra d7, loop

    body[beq_at:beq_at + 2] = w(len(body) - (beq_at - 2) - 2)      # .rest
    body += w(0x46DF)                            # move.w (a7)+, sr
    body += w(0x4CDF) + w(0x0FFF)                # movem.l (a7)+, d0-d7/a0-a3

    # a1 을 헤더 뒤(본문)로 옮긴다. 헤더 길이 = 2 + 2N.
    body += w(0x7000)                            # moveq #0, d0
    body += w(0x1029) + w(0x0001)                # move.b 1(a1), d0     N
    body += w(0xD040)                            # add.w d0, d0         2N
    body += w(0x5440)                            # addq.w #2, d0        +2
    body += w(0xD2C0)                            # adda.w d0, a1

    body[bne_at:bne_at + 2] = w(len(body) - (bne_at - 2) - 2)      # .out
    body += w(0x4EF9) + l(target)                # jmp (target).l  꼬리호출
    return bytes(body)


def build_uploader_labels(kfont: int, slot_base: int, target: int,
                          label_src: int, label_dst: int, label_tiles: int) -> bytes:
    """글리프 업로드에 이어 고정 타일 블록(승리/패배 라벨)도 올린다.

    라벨은 원본이 2플레인 압축 형식(타일당 16B = 색상15 마스크 + 색상14+15 합집합)
    이지만 **그 형식을 알 필요가 없다.** 우리가 만든 비압축 4bpp 타일을 같은 VRAM
    자리에 덮어쓰면 되기 때문이다. 원본 데이터를 찾거나 맞출 이유가 없었다.
    """
    body = bytearray(build_uploader_a1(kfont, slot_base, target))
    # 꼬리의 jmp target (6B) 을 떼고 라벨 업로드를 끼운 뒤 다시 붙인다
    tail = body[-6:]
    assert tail[:2] == w(0x4EF9), "꼬리가 jmp 가 아니다"
    body = body[:-6]

    body += w(0x48E7) + w(0xFFF0)                # movem.l d0-d7/a0-a3, -(a7)
    body += w(0x40E7)                            # move.w sr, -(a7)
    body += w(0x46FC) + w(0x2700)                # move.w #$2700, sr
    body += w(0x323C) + w(label_dst)             # move.w #dst, d1
    body += w(0x7E00 | 0)                        # moveq #0, d7
    body += w(0x3E3C) + w(label_tiles - 1)       # move.w #tiles-1, d7
    body += lea_abs(VDP_DATA, 2)                 # lea (C00000).l, a2
    body += lea_abs(label_src, 3)                # lea LABEL, a3
    loop_at = len(body)
    body += vdp_set_write(0, 1)                  # d0 스크래치, d1 = VRAM 주소
    body += w(0x249B) * 8                        # move.l (a3)+, (a2)  32바이트
    body += w(0x0641) + w(0x0020)                # addi.w #32, d1
    body += w(0x51CF) + w((loop_at - (len(body) + 2)) & 0xFFFF)   # dbra d7, loop
    body += w(0x46DF)                            # move.w (a7)+, sr
    body += w(0x4CDF) + w(0x0FFF)                # movem.l (a7)+, d0-d7/a0-a3
    body += tail
    return bytes(body)
