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

배포 페이지: **https://johnyworld.github.io/tran-lang1md/**
최신 패치: [Releases](https://github.com/Johnyworld/tran-lang1md/releases/latest)

## 현황 — 한글화 완료 (실기 검수 완료)

```
프롤로그 화면 20스테이지        완료
본편 대사 576메시지             완료 (사망 대사 포함)
이름판 78개                     완료 (원본 표를 읽는 lea 0곳)
클래스 91 / 마법 14 / 아이템 10 / 시스템 단문   완료
메뉴 그래픽 (풀 재배치 + 서술자 재작성)         완료
전투씬 · 출전 준비 · 대상 선택 라벨             완료
엔딩 스크롤 문장 + 에필로그 카드 11개           완료
```

원문으로 남는 것은 둘뿐이다. 영어 라벨(`PLAYER` `Yes/No` `LV` `HP` `NEW GAME` 등)은
**원본 픽셀 유지 결정**이고, `030A1A` 메뉴는 **도달 불가한 죽은 코드**다(창을 여는
루틴 `0x103F0` 을 부르는 곳이 롬 전체에 없고 원본에서도 항목이 깨져 있다).

배포판 빌드 · 검사 · 패치 생성:

```
python3 tools/build_all.py --release     # work/korom_all.md (정상 체크섬)
python3 tools/release_check.py           # 체크섬·디버그 표식·스탯 표·코드·롬 크기
python3 tools/patch.py                   # work/korom.bps + work/korom.ips
```

`patch.py` 는 만든 패치를 **다시 적용해 배포판과 바이트 단위로 같은지 확인**하고
다르면 실패한다. 패치 파일은 원본 그래픽 일부를 품으므로 레포에 커밋하지 않는다
(`work/` 는 gitignore).

패치 적용도 이 도구로 된다 (맥에서 별도 패처 설치 없이).

```
python3 tools/patch.py --apply work/korom.bps <원본롬> [출력파일]
```

```
적용 대상   Langrisser.md  524288B  SHA1 cc67c5a3b91e706b495eb561a95a038fff72b5da
                                    CRC32 B6EA5016
적용 결과   1048576B                CRC32 A0285D68
패처        BPS 권장 (원본 CRC 검사) — Flips, beat, Rom Patcher JS
            IPS 는 구형 패처 호환용
```

분석 내용과 실측 근거는 [docs/STATUS.md](docs/STATUS.md), 번역이 아닌 변경(체크섬
우회·롬 확장·디버그 롬)은 [docs/RELEASE.md](docs/RELEASE.md) 에 모아 둔다.

## 도구

| 파일 | 용도 |
|---|---|
| `tools/build_all.py` | 한글화 롬 빌드 → `work/korom_all.md` |
| `tools/menu.py` | 메뉴 그래픽 — 글리프 풀 재배치 + `$5CDC` 타일맵 서술자 재작성 |
| `tools/uiscan.py` | 남은 일본어 UI 문자열 전수 조사 (lea 즉치 + 창 레코드 + 표) |
| `tools/tilescan.py` | 타일맵 라벨 전수 조사 (`$5CDC` 호출 61곳) |
| `tools/debug_rom.py` | 테스트용 — 아군을 강하게 → `work/korom_debug.md` |
| `tools/release_check.py` | 배포판 검사 — 번역 아닌 변경이 남았는지 (`docs/RELEASE.md`) |
| `tools/patch.py` | 배포 패치 생성 (IPS + BPS) — 재적용 검증 포함 |
| `tools/webfont.py` | 배포 페이지용 웹폰트 부분집합 (`assets/*.woff2`) — fonttools 필요 |
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
| `translation/ending.tsv` | 엔딩 가로 스크롤 문장. 조각 번호로 식별 |
| `translation/epilogue.tsv` | 에필로그 인물 카드 11개 |
| `translation/glossary.tsv` | 고유명사 표기 결정과 근거 |

## 폰트

빌드가 쓰는 것은 둘이다.

```
font/galmuri7/    본문·UI 글리프 (8x8 급)   Galmuri7  OFL-1.1  (c) Lee Minseo (quiple)
font/dunggeunmo/  메뉴·라벨 그래픽 (16x16)  DungGeunMo  Public Domain  Kil Hyung-jin / Kim Jung-tae
```

배포 페이지도 **같은 폰트**를 쓴다. `tools/webfont.py` 가 `index.html` 의 표시 문자만
골라 부분집합을 굽고(합쳐서 16KB), 두 폰트의 합집합이 페이지를 덮는지 검사한다.
Galmuri 의 OFL 에는 예약 폰트 이름 조항이 없어 부분집합도 같은 이름으로 쓸 수 있다
(라이선스 사본 `assets/OFL.txt`).

`font/galmuri11/` 등 나머지는 초기 비교용으로 남겨 둔 것이다 (선정 근거는 STATUS).

## 작업 환경

- **ares** (`brew install --cask ares-emulator`) — 메가드라이브 에뮬·디버거.
  Memory Editor 로 VRAM / CPU RAM / CRAM 을 덤프한다.
  Export 가 무반응이면 `Settings → Paths → Debugging` 이 비어 있는 것이니 지정할 것.
- **capstone** (`pip3 install capstone`) — 68000 디스어셈블
- Mesen 2 는 메가드라이브를 지원하지 않고, BlastEm 은 x86 JIT 라 Apple Silicon
  네이티브 빌드가 안 된다.
