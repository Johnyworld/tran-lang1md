# tran-lang1md

랑그릿사 (메가드라이브, 1991 / NCS·Masaya) 한글화 프로젝트.

대상 롬은 각자 소유한 카트리지에서 덤프한 것을 쓴다. 이 레포에는 롬도,
롬에서 추출한 원저작물 데이터(대본·그래픽·메모리 덤프)도 포함하지 않는다.
분석 도구와 문서만 담는다.

```
대상   Langrisser.md  524288 bytes (4Mbit)
SHA1   cc67c5a3b91e706b495eb561a95a038fff72b5da
헤더   (C)T-25 1991.JAN / GM T-25103-00 / J
```

## 현황

분석 진행 상황은 [docs/STATUS.md](docs/STATUS.md) 에 정리한다.
폰트 구조·텍스트 인코딩·주소지정 방식은 규명 완료.

## 도구

| 파일 | 용도 |
|---|---|
| `tools/build_all.py` | 한글화 롬 빌드 → `work/korom_all.md` |
| `tools/menu.py` | 메뉴 그래픽 — 글리프 풀 재배치 + `$5CDC` 타일맵 서술자 재작성 |
| `tools/uiscan.py` | 남은 일본어 UI 문자열 전수 조사 (lea 즉치 + 창 레코드 + 표) |
| `tools/debug_rom.py` | 테스트용 — 아군을 강하게 → `work/korom_debug.md` |
| `tools/chain.py` | 본편 대사 체인 파서 (앵커 하나 = 대화 한 덩이) |
| `tools/events.py` | 스테이지 이벤트 표 -> 앵커 (이야기 순서) |
| `tools/sheet.py` | `translation/dialogue.tsv` 재생성 (기존 번역 보존) |
| `tools/script.py` | 대본 코덱 + 추출기 → `work/script.json`, `work/script.tsv` |
| `tools/textcodec.py` | 타일 인덱스 기준 코덱 (화면 복원용) |
| `tools/refs.py` | 대본 주소를 싣는 68000 즉치 전수 탐색 → `work/refs.json` |
| `tools/decode_screen.py` | VRAM 네임테이블 → 화면 텍스트 복원 |
| `tools/vramsheet.py` | VRAM 덤프를 4bpp 타일 시트 PNG 로 |
| `tools/tilepng.py` | 롬 구간을 1bpp/4bpp 타일 PNG 로 (Tile Molester 대용) |
| `tools/fontdump.py` | Galmuri11 한글 폰트 렌더 확인 |

모든 도구는 레포 루트에서 `python3 tools/<name>.py` 로 실행한다.
`work/` 는 gitignore 되어 있으며 도구가 알아서 채운다.

## 번역 원고

| 파일 | 내용 |
|---|---|
| `translation/ko.tsv` | 프롤로그 화면 (스테이지명·프롤로그·승패조건) |
| `translation/dialogue.tsv` | 본편 대사. 앵커 + 메시지 번호로 식별 |
| `translation/names.tsv` | 이름판 78개 (`0x2AE64` 표 순서) |
| `translation/ui.tsv` | UI — 클래스·마법·아이템 이름 |
| `translation/menu.tsv` | 메뉴 그래픽. 창 레코드 + 줄 번호로 식별 |
| `translation/glossary.tsv` | 고유명사 표기 결정과 근거 |

## 폰트

`font/galmuri11/` — Galmuri11 한글 2350자, 16×16 1bpp (OFL-1.1).
출처: https://font.emulog.app

## 작업 환경

- **ares** (`brew install --cask ares-emulator`) — 메가드라이브 에뮬·디버거.
  Memory Editor 로 VRAM / CPU RAM / CRAM 을 덤프한다.
  Export 가 무반응이면 `Settings → Paths → Debugging` 이 비어 있는 것이니 지정할 것.
- **capstone** (`pip3 install capstone`) — 68000 디스어셈블
- Mesen 2 는 메가드라이브를 지원하지 않고, BlastEm 은 x86 JIT 라 Apple Silicon
  네이티브 빌드가 안 된다.
