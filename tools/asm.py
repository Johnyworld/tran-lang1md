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
    # 글리프 ID 는 7비트 두 바이트로 담는다: ID = (b0 << 7) | b1.
    # 16비트로 담으면 ID 255 가 0x00FF 처럼 0xFF 를 포함하는데, 게임은 메시지를
    # 건너뛸 때 0xFF 를 바이트 단위로 훑으므로(0x15470) 헤더 중간에서 멈춘다.
    # 두 바이트 모두 0x80 미만이면 그 사고가 원천적으로 없다.
    body += w(0x7400)                            # moveq #0, d2
    body += w(0x1418)                            # move.b (a0)+, d2     상위 7비트
    body += w(0xEF4A)                            # lsl.w #7, d2
    body += w(0x8418)                            # or.b  (a0)+, d2      하위 7비트
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
    # 글리프 ID 는 7비트 두 바이트로 담는다: ID = (b0 << 7) | b1.
    # 16비트로 담으면 ID 255 가 0x00FF 처럼 0xFF 를 포함하는데, 게임은 메시지를
    # 건너뛸 때 0xFF 를 바이트 단위로 훑으므로(0x15470) 헤더 중간에서 멈춘다.
    # 두 바이트 모두 0x80 미만이면 그 사고가 원천적으로 없다.
    body += w(0x7400)                            # moveq #0, d2
    body += w(0x1418)                            # move.b (a0)+, d2     상위 7비트
    body += w(0xEF4A)                            # lsl.w #7, d2
    body += w(0x8418)                            # or.b  (a0)+, d2      하위 7비트
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


def _glyph_loop(kfont: int, tile_base: int | None = 0, areg: int = 0) -> bytes:
    """a{areg} = 글리프 ID 목록(7비트 두 바이트 x N), d7 = N-1 을 전제로 VRAM 에 올린다.
    d0..d2 / a2 / a3 를 스크래치로 쓴다. tile_base=None 이면 d1 이 이미 VRAM 주소다."""
    body = bytearray()
    if tile_base is not None:
        body += w(0x323C) + w(tile_base * 32)     # move.w #tile*32, d1
    body += lea_abs(VDP_DATA, 2)                  # lea (C00000).l, a2
    loop_at = len(body)
    body += vdp_set_write(0, 1)                   # d0 스크래치, d1 = VRAM 주소
    body += w(0x7400)                             # moveq #0, d2
    body += w(0x1418 | areg)                      # move.b (aN)+, d2   상위 7비트
    body += w(0xEF4A)                             # lsl.w #7, d2
    body += w(0x8418 | areg)                      # or.b  (aN)+, d2    하위 7비트
    body += w(0xE58A) + w(0xE58A) + w(0xE38A)     # lsl.l #2,#2,#1 -> x32
    body += lea_abs(kfont, 3)                     # lea KFONT, a3
    body += w(0xD7C2)                             # adda.l d2, a3
    body += w(0x249B) * 8                         # move.l (a3)+, (a2)  32바이트
    body += w(0x0641) + w(0x0020)                 # addi.w #32, d1
    body += w(0x51CF) + w((loop_at - (len(body) + 2)) & 0xFFFF)   # dbra d7, loop
    return bytes(body)


UI_MARKER = 0x01


def build_uploader_ui(kfont: int, uitbl: int, nrec: int, stride: int = 32,
                      table_at: int = 0x62BC, alt_table: int = 0) -> bytes:
    """UI 문자열 업로더. `0x5FD4` 의 `lea $62BC.l, a2` 자리를 그대로 대신한다.

    UI 텍스트는 예외 없이 `lea <문자열>, a1` + `jsr $5F60` 으로 그려진다. 그래서
    **문자열이 자기 글리프를 들고 다니게** 만들면 그리기 지점마다 훅을 걸 필요가
    없다. `$5F60` 의 문자열 루프 직전 한 곳이면 전부 걸린다.

    ```
    문자열 앞머리  [0x01][k]                 k 번째 글리프 기록을 올려라
    글리프 기록    [페이지][타일][N][ID x N]   uitbl + k*stride, ID 는 7비트 두 바이트
    페이지        0 = 원본 표, n = alt_table + (n-1)*256
    ```

    두 바이트만 붙이는 간접 방식인 이유: 클래스명 같은 표는 `lsl.w #4` 로 색인해
    **엔트리가 16바이트로 고정**이다. 글리프 목록을 문자열에 직접 담으면 넘친다.

    마커로 `0x01` 을 쓴 이유: 본문 코드(0x7F..0xA0/0xE0..0xFD)·이름 코드(0x0E..0x13)
    ·ASCII·줄바꿈(0x0D)과 겹치지 않는 값이어야 한다. 대사 본문 문자열도 이 훅을
    지나가는데(렌더러가 같다) 첫 바이트가 본문 코드라 절대 0x01 이 아니다.

    **코드 페이지 교체가 이 훅의 값이다.** 우리가 돌려주는 a2 가 `$5F60` 이 쓰는
    코드->타일 표이므로, 문자열마다 다른 표를 줄 수 있다. 저바이트 코드가 다 차서
    가나 코드를 훔치려 했으나 남은 대사 1026개가 가나 62종을 쓰고 있어(`。` `「` 까지
    포함) 전역 재매핑은 불가였다. 대신 **그 문자열만** 다른 표로 그리면 남은
    일본어는 원본 표를 그대로 쓴다.

    a1 과 a2 는 movem 에서 **빼둔다**. a1 은 헤더를 지나간 전진이 남아야 하고
    (`$5F60` 의 루프가 본문부터 읽는다), a2 는 우리가 고른 표를 들고 나가야 한다.

    `k` 는 범위를 검사한다. 아직 번역하지 않은 원본 문자열이 우연히 `0x01` 로
    시작하면 엉뚱한 기록을 읽어 VRAM 을 망가뜨리기 때문이다. 범위 밖이면 a1 을
    건드리지 않고 원본 표로 나가므로 원본과 완전히 같게 동작한다.
    """
    SAVE, REST = 0xFF9E, 0x79FF                   # d0-d7/a0/a3-a6 (a1·a2 제외)
    body = bytearray()
    body += w(0x0C11) + w(UI_MARKER)              # cmpi.b #$01, (a1)
    body += w(0x6600) + w(0x0000)                 # bne.w .plain
    bne_at = len(body) - 2

    body += w(0x48E7) + w(SAVE)                   # movem.l d0-d7/a0/a3-a6, -(a7)
    body += w(0x7000)                             # moveq #0, d0
    body += w(0x1029) + w(0x0001)                 # move.b 1(a1), d0    k
    body += w(0x0C40) + w(nrec)                   # cmpi.w #nrec, d0
    body += w(0x6400) + w(0x0000)                 # bcc.w .restore     범위 밖
    bcc_at = len(body) - 2
    body += w(0x5489)                             # addq.l #2, a1      마커 + k
    body += w(0x40E7)                             # move.w sr, -(a7)
    body += w(0x46FC) + w(0x2700)                 # move.w #$2700, sr
    body += w(0xC0FC) + w(stride)                 # mulu.w #stride, d0
    body += lea_abs(uitbl, 0)                     # lea UITBL, a0
    body += w(0xD0C0)                             # adda.w d0, a0
    body += w(0x7C00)                             # moveq #0, d6
    body += w(0x1C18)                             # move.b (a0)+, d6    플래그
    body += w(0x7200)                             # moveq #0, d1
    body += w(0x1218)                             # move.b (a0)+, d1    타일 번호
    body += w(0xEB49)                             # lsl.w #5, d1        x32 = VRAM 주소
    body += w(0x7E00)                             # moveq #0, d7
    body += w(0x1E18)                             # move.b (a0)+, d7    N
    body += w(0x6700) + w(0x0000)                 # beq.w .done
    beq_at = len(body) - 2
    body += w(0x5347)                             # subq.w #1, d7
    body += _glyph_loop(kfont, None, areg=0)      # d6 은 건드리지 않는다
    body[beq_at:beq_at + 2] = w(len(body) - (beq_at - 2) - 2)       # .done
    body += w(0x46DF)                             # move.w (a7)+, sr

    # 코드 페이지 선택 — a2 는 movem 밖이라 그대로 남는다.
    # 플래그는 **페이지 번호**다: 0 = 원본 표, n = alt_table + (n-1)*256.
    body += lea_abs(table_at, 2)                  # lea $62BC.l, a2
    if alt_table:
        body += w(0x4A06)                         # tst.b d6
        body += w(0x6700) + w(0x000C)             # beq.w .keep (아래 4명령 = 12바이트)
        body += w(0x5306)                         # subq.b #1, d6
        body += w(0xE14E)                         # lsl.w #8, d6      페이지 x 256
        body += lea_abs(alt_table, 2)             # lea ALT.l, a2
        body += w(0xD4C6)                         # adda.w d6, a2
    body += w(0x6000) + w(0x0000)                 # bra.w .restore_end
    bra_at = len(body) - 2

    body[bcc_at:bcc_at + 2] = w(len(body) - (bcc_at - 2) - 2)       # .restore
    body += lea_abs(table_at, 2)                  # lea $62BC.l, a2   원본과 같게

    body[bra_at:bra_at + 2] = w(len(body) - (bra_at - 2) - 2)       # .restore_end
    body += w(0x4CDF) + w(REST)                   # movem.l (a7)+, d0-d7/a0/a3-a6
    body += w(0x4E75)                             # rts

    body[bne_at:bne_at + 2] = w(len(body) - (bne_at - 2) - 2)       # .plain
    body += lea_abs(table_at, 2)                  # lea $62BC.l, a2   훔친 명령
    body += w(0x4E75)                             # rts
    return bytes(body)


def build_uploader_msg(kfont: int, body_base: int, name_base: int,
                       name_ids: int, name_n: int,
                       p_work: int = 0xFFFFE818, p_name: int = 0xFFFFE82A) -> bytes:
    """본편 대사용 업로더. `0x157C8` 의 `move.l a1, $E818` 자리를 그대로 대신한다.

    이름판 렌더러 `0x1579A` 안의 그 지점이 유일한 훅이면 되는 이유:
      - a1 이 이미 **본문 문자열**을 가리킨다 (0x157BA 가 $E824 에 따라 앞 문자열을
        건너뛴 뒤). 본문이 str1 인지 str2 인지는 런타임 값이라 알 수 없지만,
        여기서는 이미 정해져 있다.
      - 이름판(0x157EC)과 본문(0x15650) 두 그리기보다 **먼저** 실행된다. 네임테이블은
        타일 번호만 들고 있으니 그리기 전에 픽셀을 올려야 한다.
      - 메시지마다 창을 다시 열므로(0x154FE) 메시지마다 한 번 실행된다.

    이름 글리프는 **마커와 무관하게 항상** 올린다. 이름 문자열표(0x157D8 즉치)를
    우리 것으로 바꿔 두므로, 아직 번역하지 않은 일본어 메시지도 이름판은 한글로
    나와야 하기 때문이다.
    """
    body = bytearray()
    body += w(0x48E7) + w(0xFFF0)                 # movem.l d0-d7/a0-a3, -(a7)
    body += w(0x40E7)                             # move.w sr, -(a7)
    body += w(0x46FC) + w(0x2700)                 # move.w #$2700, sr

    # ---- 이름 글리프: $E82A(이름 인덱스) -> 우리 ID 표 -> 타일 name_base.. ----
    body += w(0x7000)                             # moveq #0, d0
    body += w(0x3039) + l(p_name)                 # move.w (E82A).l, d0
    body += w(0x0C40) + w(name_n)                 # cmpi.w #name_n, d0
    body += w(0x6400) + w(0x0000)                 # bcc.w .noname
    bcc_at = len(body) - 2
    body += w(0xE940)                             # lsl.w #4, d0        16B/엔트리
    body += lea_abs(name_ids, 0)                  # lea NAME_IDS, a0
    body += w(0xD0C0)                             # adda.w d0, a0
    body += w(0x7E00)                             # moveq #0, d7
    body += w(0x1E18)                             # move.b (a0)+, d7    N
    body += w(0x6700) + w(0x0000)                 # beq.w .noname
    beq_name_at = len(body) - 2
    body += w(0x5347)                             # subq.w #1, d7
    body += _glyph_loop(kfont, name_base)
    end = len(body)
    body[bcc_at:bcc_at + 2] = w(end - (bcc_at - 2) - 2)
    body[beq_name_at:beq_name_at + 2] = w(end - (beq_name_at - 2) - 2)

    # ---- 본문 글리프: 헤더 [0xFE][N][ID x N] 가 있을 때만 ----
    body += w(0x0C11) + w(MARKER)                 # cmpi.b #$FE, (a1)
    body += w(0x6600) + w(0x0000)                 # bne.w .plain
    bne_at = len(body) - 2
    body += w(0x2049)                             # movea.l a1, a0
    body += w(0x5288)                             # addq.l #1, a0       마커 건너뛰기
    body += w(0x7E00)                             # moveq #0, d7
    body += w(0x1E18)                             # move.b (a0)+, d7    N
    body += w(0x6700) + w(0x0000)                 # beq.w .store
    beq_body_at = len(body) - 2
    body += w(0x5347)                             # subq.w #1, d7
    body += _glyph_loop(kfont, body_base)
    body[beq_body_at:beq_body_at + 2] = w(len(body) - (beq_body_at - 2) - 2)
    body += move_l_a_abs(0, p_work)               # move.l a0, (E818).l  헤더 뒤
    body += w(0x6000) + w(0x0000)                 # bra.w .done
    bra_at = len(body) - 2

    body[bne_at:bne_at + 2] = w(len(body) - (bne_at - 2) - 2)      # .plain
    body += move_l_a_abs(1, p_work)               # move.l a1, (E818).l

    body[bra_at:bra_at + 2] = w(len(body) - (bra_at - 2) - 2)      # .done
    body += w(0x46DF)                             # move.w (a7)+, sr
    body += w(0x4CDF) + w(0x0FFF)                 # movem.l (a7)+, d0-d7/a0-a3
    body += w(0x4E75)                             # rts
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


def build_uploader_block(src: int, dst: int, tiles: int, call_first: int) -> bytes:
    """원래 호출을 먼저 하고, 고정 타일 블록을 VRAM 에 덮어쓴다.

    `jsr <그래픽 로드>` (6바이트) 자리를 그대로 대신한다. 압축 리소스를 풀 필요가
    없다 — 게임이 올린 뒤 그 자리를 우리 비압축 타일로 덮으면 된다. 승리/패배
    라벨에서 통한 방법이고, 여기서는 선택 창 제목 글리프에 쓴다.

    호출 규약: 원래 `jsr` 와 같아야 하므로 레지스터를 전부 보존한다.
    """
    body = bytearray()
    body += w(0x4EB9) + l(call_first)             # jsr <원래 로드>
    body += w(0x48E7) + w(0xFFF0)                 # movem.l d0-d7/a0-a3, -(a7)
    body += w(0x40E7)                             # move.w sr, -(a7)
    body += w(0x46FC) + w(0x2700)                 # move.w #$2700, sr
    body += w(0x323C) + w(dst)                    # move.w #dst, d1     VRAM 주소
    body += w(0x3E3C) + w(tiles - 1)              # move.w #tiles-1, d7
    body += lea_abs(VDP_DATA, 2)                  # lea (C00000).l, a2
    body += lea_abs(src, 3)                       # lea SRC, a3
    loop_at = len(body)
    body += vdp_set_write(0, 1)                   # d0 스크래치, d1 = VRAM 주소
    body += w(0x249B) * 8                         # move.l (a3)+, (a2)  32바이트
    body += w(0x0641) + w(0x0020)                 # addi.w #32, d1
    body += w(0x51CF) + w((loop_at - (len(body) + 2)) & 0xFFFF)   # dbra d7, loop
    body += w(0x46DF)                             # move.w (a7)+, sr
    body += w(0x4CDF) + w(0x0FFF)                 # movem.l (a7)+, d0-d7/a0-a3
    body += w(0x4E75)                             # rts
    return bytes(body)
