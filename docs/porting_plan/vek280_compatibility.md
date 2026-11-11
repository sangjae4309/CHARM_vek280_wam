> Current implementation status (2026-11-09): the initial kernel5 AIE-ML source
> port is now applied. See [the port notes](kernel5_aie_ml_port.md). Older proposal
> and baseline sections below describe the investigation before these edits.
> Target compilation/simulation of the port is still pending.

# VEK280 호환성 검토

기록일: 2026-11-09. 대상: VCK190의 1세대 AIE → VEK280의 AIE-ML.
실물 보드 revision은 미확인이다. 아래 레지스터 구조는 공식 문서 확인 결과이며,
이 저장소 커널의 AIE-ML 컴파일 성공을 의미하지 않는다.

## 512비트 벡터 레지스터

| 아키텍처 | 512비트 레지스터 이름 | 근거 |
| --- | --- | --- |
| 1세대 AIE | xa, xb, xc, xd | [AMD AM009 Register Files](https://docs.amd.com/r/en-US/am009-versal-ai-engine/Register-Files) |
| AIE-ML | x0 … x11 | [AMD AM020 Register Files](https://docs.amd.com/r/en-US/am020-versal-aie-ml/Register-Files) |

`v32int16`이 표현하는 32×16=512비트 데이터 폭 자체는 AIE-ML에서도 표현 가능하다.
그러나 원본의 `chess_storage(xa)`를 같은 물리 레지스터 지정으로 그대로 적용할 수
있다고 가정하면 안 된다. 공식 레지스터 이름과 구성이 다르다.

이 대화에서는 “xa 지정을 수정해야 한다”고 설명했다. 엄밀하게는 **아키텍처상
같은 xa 레지스터가 없다는 사실**과 **2025.2 컴파일러가 해당 소스 표기를 거부하는지**는
별개다. 후자는 별칭·호환 처리까지 포함한 컴파일 확인을 하지 않았으므로 미검증이다.
`xa → x0`의 기계적 치환으로 동등한 배치나 계산을 보장한다고도 주장하지 않는다.

## 입력 타일 확대 여지 — 공식 사양 확인

확인일: 2026-11-09. 아래는 AM009/AM020 문서 확인과 용량 산술이며,
컴파일·배치·성능 검증 결과가 아니다.

| 항목 | AIE | AIE-ML |
| --- | --- | --- |
| 전체 vector register 저장량 | 16×128bit = 256 bytes | 24×256bit = 768 bytes |
| 512bit register 묶음 | xa…xd, 4개 | x0…x11, 12개 |
| 512bit에 담기는 INT16 | 32개 | 32개 |
| tile 자체 data memory | 32 KB | 64 KB |
| 별도 memory tile | 없음 | 개당 512 KB |
| INT16 operations/tile, AMD 비교표 표기 | 64 | 128 |
| cycle당 memory load/store | 512/256bit | 512/256bit |

레지스터 근거는 위 AM009/AM020 Register Files 링크다. 나머지는
[AM020 Summary](https://docs.amd.com/r/en-US/am020-versal-aie-ml/Summary)를 따른다.
vector 저장량은 기본 register를 합산한 값이며, X/Y 등 겹치는 alias를 중복 계산하지
않는다. accumulator는 별도 자원이다. 2048 **bits**는 256 **bytes**다.
전체 vector 저장량은 3배지만 512bit vector 하나의 INT16 원소 수는 그대로다.
512 KB memory tile은 각 compute tile의 private memory나 register가 아니다.

원본 `(48×32) @ (32×48)`은 현재 커널의 설정이지 하드웨어 최대 입력 크기가
아니다. 아래 포팅 후보에서 이를 유지한다는 것은 비교 기준 제안일 뿐이며,
AIE-ML의 최종 타일 크기를 고정한 결정이 아니다. 원본의 16×2 내부 출력 블록도
재검토 대상이다. 전체 커널 타일과 한 명령/API가 계산하는 작은 블록은 구별한다.

예시 산술: A/B/C를 모두 INT16로 저장하고 세 버퍼를 모두 ping-pong하면,
데이터만 필요한 용량은 `4*(M*K + K*N + M*N)` bytes다.

- M=48,K=32,N=48: 21 KiB.
- M=64,K=64,N=64: 48 KiB.

64×64 후보는 자체 64 KB 메모리 안에서 검토할 여지가 있으나 stack, 정렬,
packing, 넓은 부분합 임시 저장, bank/주소 배치 등은 위 계산에 없다.
실제 cascade 단계마다 C buffer 요구량도 다르므로 실제 graph 메모리 사용량이
아니다. 이 산술만으로 컴파일 가능·최적 성능을 주장하지 않는다. 기존 AIE도 인접
메모리 활용이나 streaming으로 더 큰 입력을 처리할 수 있으므로, 큰 타일 자체가
AIE-ML에서 처음 가능해진다는 뜻은 아니다.

포팅 시 큰 타일과 내부 계산 블록을 함께 비교할 필요가 있다. load/store 대역폭은
위 표에서 같으므로 계산 자원 증가가 그대로 처리량 증가를 보장하지 않는다.
타일 확대, 누산 형식과 데이터 배치 변경은 아직 제안이며 구현 승인이 아니다.

## 함께 검토할 원본 의존성

근거 파일: [mm5_kernel0.cc](../../templates/aie/kernel_int16_packet/aie/mm5_kernel0.cc),
[para.h](../../templates/aie/kernel_int16_packet/aie/para.h),
[aie_graph.h](../../templates/aie/kernel_int16_packet/aie/aie_graph.h).

| 항목 | 현재 소스에서 확인한 것 | 이후 검토할 것 |
| --- | --- | --- |
| 벡터 저장 위치 | xa, xb, wc0, wc1을 명시 | AIE-ML 레지스터와 명령 제약; 수동 지정 필요성 |
| 벡터 조작 | upd_w, upd_v 및 window 읽기 | 같은 데이터 순서를 보존하는 AIE-ML 구현 |
| 곱셈 | mac16 및 원소 선택 상수 | 지원 명령/API와 원소별 대응 |
| 누산 | v16acc48, acc48 cascade | 지원 누산 폭, cascade 인터페이스, 수치 동등성 |
| 출력 | srs(acc, 0), INT16 window | 포화·overflow·rounding 설정과 정확한 결과 |
| 그래프 | 고정 tile 좌표 및 buffer/stack 주소 | AIE-ML 메모리·배치 제약 |

위 표는 검토 목록이며 구현 선택의 승인이 아니다. `aie::mmul` 도입, 버퍼 API 교체,
레지스터 고정 해제, 누산 폭 변경은 사용자에게 이유와 검증 방식을 제안한 뒤 결정한다.

## 계산부 포팅 후보 — 아직 채택·구현하지 않은 제안

검토일: 2026-11-09. 외부 타일 `(48×32) @ (32×48)`과 kernel0/1/2의
시작·누적·마무리 역할은 유지하면서 계산 내부를 AIE-ML용으로 바꾸는 접근을 제안했다.

1. 원본 intrinsic를 AIE-ML intrinsic로 직접 재작성할 수 있으나, 레지스터뿐 아니라
   선택 상수, 벡터 조작, 누산 형식과 전달 순서를 재설계해야 한다.
2. 대안으로 `aie::mmul`을 사용하는 계산부를 작성한다. Vitis 2025.2 API와 설치된
   `aie_api/detail/aie2/mmul_16_16.hpp`에는 INT16 4×4×4와 64비트 누산 구현이 있다.
   이는 후보이며 컴파일·성능 검증 결과는 아니다.

4×4×4 후보의 논리적 계산은 `A[r:r+4,k:k+4] @ B[k:k+4,c:c+4]`를
k=0,4,…,28에서 합산해 4×4 결과를 얻는 것이다. r,c는 0,4,…,44로 움직인다.
16×2였던 내부 블록을 유지할 필요는 없지만, 외부 출력 타일의 값·순서와 cascade
계약은 유지하거나 변경 근거를 사용자와 합의해야 한다.

API는 각 작은 입력 블록이 요구하는 순서로 vector에 담겨야 한다.
원본 col-major window 포인터를 그대로 연속 load하여 대체하면 안 된다.
입력·출력 경계에서 packing/reordering을 넣는 접근을 우선 검토하고, 이를 PL에서
수행할지 AIE에서 수행할지는 비용을 비교한 뒤 결정한다.

원본 acc48 대신 acc64를 쓰더라도 cascade 양 끝 형식, lane 순서, packet 경계,
최종 INT16 변환 설정을 함께 맞춰야 한다. 전체 수치 동등성은 별도 검증 대상이다.
진행 후보는 단일 타일 계산 검증 → cascade 부분합 검증 → PL 연동 → 생성기/DSE
반영이며, 각 단계 실행에는 사용자와 범위 합의가 필요하다.

공식 참고: [Vitis 2025.2 Matrix Multiplication API](https://download.amd.com/docnav/aiengine/xilinx2025_2/aiengine_api/aie_api/doc/group__group__mmul.html).

## 도구와 검증 이력의 한계

### 2026-11-09 원본 보존 포팅 착수

사용자가 kernel5부터 CHARM 방식 그대로 포팅하도록 요청했고, 뒤이어 AIE 사양에
맞춘 재설계 없이 그대로 진행하도록 범위를 한정했다. 따라서 앞선 acc64/vector MAC
재작성 제안은 적용하지 않았다. 원본 template는 수정하지 않았다.
TODO: [templates/aie/README.md](../../templates/aie/README.md).

`sim/tmp_kernel5_vek280_r_m2fb2i/`에서 `aiecompiler --version`은 2025.2와
exit code 0을 반환했다. 원본을 48×32×48, B=3, PACK_IN=3으로 렌더링해 VEK280
platform 컴파일을 시도했으나 약 3분간 시작 단계에서 소스 진단이 없어 SIGTERM으로
중단했다. wrapper는 0을 반환했지만 성공한 컴파일이 아니다. register 오류 여부와
대기 원인은 미확인이다. 시뮬레이션은 실행하지 않았다. 이 과거 case는 이후
사용자의 `sim/tmp_*` 정리 요청으로 삭제했다. 현재 실행 경로와 기록은
[생성기 기반 simulation 문서](aie_simulation.md)를 따른다.

### 이전 관찰

- 앞선 읽기 점검에서 환경의 Vitis/Vivado 경로는 2025.2였고,
  Vitis base_platforms 아래 `xilinx_vek280_base_202520_1` 플랫폼을 확인했다.
  현재 세션에서 재실행한 도구 검증이나 보드 연결 확인은 아니다.
- 취소된 실험 중 `v++ --version`은 호스트 GLIBC_2.28 요구 오류를 출력했다.
  원인 해결은 하지 않았고, AIE 컴파일 시도도 성공 결과 없이 중단했다.
- 해당 시도의 코드·실험 디렉터리·로그는 사용자 요청으로 삭제되었다.
  따라서 이 항목은 이전 세션 관찰의 기록이며 재현 가능한 검증 증거가 남아 있지 않다.
- 사용자는 도구와 라이선스가 준비됐다고 알렸다. 다음 승인된 실행에서 실제 실행
  환경을 확인할 필요가 있으나, 이 기록을 근거로 임의의 환경 변경을 해서는 안 된다.
- 현재 성공 판정: AIE-ML 컴파일 미검증 / 시뮬레이션 미검증 / 보드 실행 미검증.

## Confirmed original-source compilation failure (2026-11-09)

The user reported Vitis 2025.2 graph-preprocessor errors in generated
`aie/layer0/para_L0.h` lines 19-21: unknown `input_stream_acc48` and
`output_stream_acc48` types. This is a source-compatibility failure, not merely
an observed startup delay. The duration/cause of the earlier delay remains unknown.

The installed `aietools/include/adf/stream/types.h` was inspected directly:
acc48 stream aliases are defined only under `__AIE_ARCH__ < 20`; the branch for
`__AIE_ARCH__ >= 20` provides acc32/acc64 stream aliases instead. The original
kernel5 `para.h` already includes this header. Adding the same header cannot
resolve the architecture-dependent absence of these types.

This failure occurs while processing graph-visible function declarations. It
does not yet establish compiler results for `chess_storage(xa)`, `mac16`, or the
kernel bodies. The trailing 77-753 graph-preprocessor message follows the four
unknown-type diagnostics; it is not evidence of a separate root cause.

A future fix must coordinate declarations, kernel accumulator computation,
cascade reads/writes and final INT16 conversion. Renaming acc48 stream aliases
alone is not a complete port. No implementation change or vendor tool execution
was performed in response to this diagnostic. Successful compilation/simulation
remains unestablished.
