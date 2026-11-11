# INT16 원본 커널과 그래프

확인일: 2026-11-09. 상태: 소스 읽기 확인. 이 문서는 실행 검증 보고서가 아니다.
범위는 `templates/aie/kernel_int16_packet/aie/`이며 다른 커널 계열 전체로 일반화하지 않는다.

## kernel0/1/2/3의 관계

네 개를 순서대로 모두 실행하는 구조가 아니다. 각 함수는 자신의 A, B 입력에
대한 곱셈·누산을 수행하며, 누산 시작값과 입출력 형태가 다르다.

| 함수 | 누산 시작 | 출력 |
| --- | --- | --- |
| kernel0 | 0 (`null_v16acc48`) | 48비트 누산값을 cascade로 전달 |
| kernel1 | cascade 입력 (`readincr_v8`) | 자신의 부분곱을 더해 cascade로 전달 |
| kernel2 | cascade 입력 (`readincr_v8`) | 자신의 부분곱을 더한 뒤 `srs(acc, 0)`으로 INT16 window에 저장 |
| kernel3 | 0 (`null_v16acc48`) | 자신의 곱셈을 완료한 뒤 `srs(acc, 0)`으로 INT16 window에 저장 |

근거: [kernel0](../../templates/aie/kernel_int16_packet/aie/mm5_kernel0.cc),
[kernel1](../../templates/aie/kernel_int16_packet/aie/mm5_kernel1.cc),
[kernel2](../../templates/aie/kernel_int16_packet/aie/mm5_kernel2.cc),
[kernel3](../../templates/aie/kernel_int16_packet/aie/mm5_kernel3.cc).

현재 [aie_graph.h](../../templates/aie/kernel_int16_packet/aie/aie_graph.h)는
첫 인스턴스에 kernel0, 마지막에 kernel2, 중간에 kernel1을 배치한다.
인스턴스 사이에는 `connect<cascade>`를 사용한다. kernel3를 생성하는 분기는 없다.
따라서 kernel3는 단독 계산용 함수이지만 현재 그래프의 활성 실행 경로는 아니다.

## 세 조각으로 고정된 것이 아니다

[para.h](../../templates/aie/kernel_int16_packet/aie/para.h)의 `NUM_KERNEL={{B}}`가
cascade 길이를 정한다. 입력 행렬 B와 이 설정값 B는 다른 개념이다.

- B=2: kernel0 → kernel2.
- B=3: kernel0 → kernel1 → kernel2.
- B=4: kernel0 → kernel1 → kernel1 → kernel2.

위 예시는 역할 배치를 설명한다. 패킷 수의 나눗셈, 메모리, 배치 제약까지
검사한 유효 설정 목록은 아니다. B=1에서 kernel3를 선택하는 분기도 없다.
현재 첫 인스턴스 분기가 kernel0를 선택하므로 B=1을 단독 지원으로 간주하면 안 된다.

## 타일 행렬곱에서 담당하는 부분

출력 타일은 `C[i,j] = sum_k A[i,k] B[k,j]`이다. cascade는 같은 출력 타일에
대한 K축 부분곱들을 더한다. 각 AIE의 결과를 M/N축으로 이어 붙이는 과정이 아니다.

kernel5의 로컬 K는 `w1=32`로 고정되어 있다. h1=w2=48을 가정하면:

- 각 AIE: (48×32) × (32×48)의 부분곱.
- 길이 B의 cascade: K=32B에 해당하는 부분곱을 더해 48×48 타일 출력.
- kernel3 한 번: 자기 입력 (48×32) × (32×48) 계산을 단독 완료.

전체 시스템의 더 큰 K 반복과 타일 공급·결과 누적은 상위 PL/그래프 로직의
검토가 필요하다. kernel3 혼자 전체 큰 행렬의 모든 타일을 처리한다고 해석하지 않는다.
48은 설명에 사용한 설정이며, h1과 w2는 템플릿 인자다.

## kernel0 첫 선언 읽기

```cpp
v32int16 chess_storage(xa) buf_matA0 = undef_v32int16();
```

| 요소 | 의미 |
| --- | --- |
| `v32int16` | signed INT16 32개, 총 512비트(64바이트)의 벡터 타입 |
| `buf_matA0` | C++ 변수 이름 |
| `chess_storage(xa)` | Chess 컴파일러의 저장 위치 지정 확장 문법 |
| `xa` | 1세대 AIE의 512비트 벡터 레지스터 지정자; C++ 변수가 아님 |
| `undef_v32int16()` | 값이 정해지지 않은 초기 벡터; 0 초기화가 아님 |

이 선언 자체는 A 데이터를 읽지 않는다. 이어지는 `window_read_v16`과 `upd_w`가
읽기 및 벡터 채우기에 관여한다. 정확한 원소별 추적은 다음 코드 설명에서 확인한다.
`chess_storage`는 실행 시 호출하는 일반 C++ 함수가 아니다.
레지스터 구조의 공식 근거와 포팅 주의점은 [호환성 문서](vek280_compatibility.md)를 참조한다.

## kernel0의 15~16행: 최초 A 입력 읽기

확인일: 2026-11-09. 원본 소스와 설치된 Vitis 2025.2의
`aietools/include/adf/window/window.h`,
`aietools/include/aie_api/detail/aie1/vector.hpp`를 읽어 확인했다.
실행 검증은 하지 않았다.

```cpp
buf_matA0=upd_w(buf_matA0,0,window_read_v16(matA));
window_incr(matA,L{{layer}}_h1);
```

- `window_read_v16(matA)`는 현재 window 위치의 연속 INT16 16개(256비트)를
  읽으며, 그 자체는 읽기 위치를 증가시키지 않는다.
- `upd_w(..., 0, ...)`는 512비트 벡터의 0번 256비트 부분, 즉 원소 0~15를
  교체한다. 나머지 원소 16~31은 보존되며 이 시점에는 아직 미정의다.
- `window_incr(..., h1)`은 INT16 원소 h1개만큼 읽기 위치를 이동한다.
  h1=48이면 처음 위치 기준 +48원소(+96바이트)이며 +16 다음에 +48이 아니다.
- 다음 17행은 그 새 위치에서 읽은 16개를 벡터의 1번 부분에 넣는다.
  버퍼 오프셋으로 표현하면 이후 벡터는 `[A[0:16], A[h1:h1+16]]`이다.
  여기서 A는 논리적 2차원 행렬이 아닌 입력 window의 선형 원소 배열을 뜻한다.
- 열 우선으로 저장된 h1행 행렬을 가정하면 같은 행 범위의 인접 두 열에
  해당한다. PL이 실제로 만드는 입력 순서와의 대응은 별도 추적이 필요하다.

## A/B 벡터 버퍼가 담는 부분

확인일: 2026-11-09. kernel0의 초기 window 읽기, stride 및 첫 계산 구간을
소스로 추적했다. 아래 row/col 대응은 col-major 입력을 가정하며 PL 전송 순서는
별도 검증 대상이다. 인덱스는 0부터 시작한다.

| 버퍼 | 타입 | 처음 채워지는 데이터 |
| --- | --- | --- |
| buf_matA0 | v32int16 | A의 row 0~15, col 0~1 |
| buf_matA1 | v32int16 | A의 row 0~15, col 2~3 |
| buf_matB0 | v16int16 | B의 row 0~7, col 0~1 |
| buf_matB1 | v16int16 | B의 row 8~15, col 0~1 |

A 버퍼는 각각 16×2=32개, B 버퍼는 각각 8×2=16개의 INT16을 담는다.
각 버퍼의 0/1은 고정된 row/col 번호가 아니라 번갈아 재사용하는 저장 공간을
구분한다. B0의 첫 8개는 col0, 다음 8개는 col1 데이터다.
`window_incr(matB, w1)`과 `window_decr(matB, w1-8)`의 순효과는 +8원소이므로,
다음 B1 읽기는 row8에서 시작한다. 이후 B0는 row16~23, B1은 row24~31로
갱신된다. B 버퍼 하나가 K축 원소 8개씩을 두 col에 대해 담으므로, A0와 B0,
A1과 B1만 고정적으로 짝지어 계산한다고 해석하면 안 된다. 실제 피연산자
선택은 각 `mac16` 호출의 인덱스와 선택 상수로 결정된다.

## i/j 루프와 dot product 진행 방향

확인일: 2026-11-09. kernel0의 루프 경계, 누산기 초기화 및 cascade 출력을
소스로 확인했다. 수학적 블록 순서를 설명하며 물리적인 명령 타이밍은 미검증이다.

- 바깥 `i < h1/16`: 출력의 row 블록을 16씩 이동한다.
- 안쪽 `j < w2/2`: 같은 row 블록에서 출력의 col 블록을 2씩 이동한다.
- `(i,j)` 한 번은 `C[16i:16i+16, 2j:2j+2]`의 K=32 부분곱을 계산한다.
  acc0는 첫 col의 16개, acc1은 두 번째 col의 16개 누산값이다.
- 각 출력 원소의 K축 dot product는 A의 고정 row에서 col 방향으로,
  B의 고정 col에서 row 방향으로 진행한다. 원본에는 반복된 `mac16` 호출로
  K 계산이 펼쳐져 있으며, i/j 자체가 K축 반복을 뜻하지 않는다.
- h1=w2=48 예에서 출력 블록 순서는 `(0,0)…(0,23),(1,0)…(2,23)`으로 총 72개다.
  kernel0의 출력은 다음 AIE로 전달하는 부분합이며 최종 INT16 출력은 아니다.

[루프 방향 HTML](../../int16_loop_visualization.html)은 실제 크기 48×32×48의
논리적 좌표와 숫자 예제로 i/j 이동, K 방향 및 누산값을 보여준다. K pair 슬라이더는
수학적 진행을 나타내며 추가 소스 루프나 명령 수준 시뮬레이션이 아니다.

## line43부터: 첫 i=0, j=0 구간의 2D 인덱스 대응

확인일: 2026-11-09. 원본 line43~79의 버퍼 읽기와 호출 순서를 확인했다.
다음은 col-major 논리적 입력에 대한 수학적 대응이며 mac16 선택 상수의
명령 수준 실행 검증이나 PL 입력 배치 검증을 대신하지 않는다. slice 끝은 제외한다.

| line | 논리적 의미 |
| --- | --- |
| 43 | `acc0[:] += A[0:16,0:2] @ B[0:2,0]` |
| 44~45 | A1의 앞 16개에 `A[0:16,2]`를 읽고 A window를 다음 col로 이동 |
| 46~47 | B1의 앞 8개에 `B[8:16,0]`를 읽고 B window를 다음 col로 이동 |
| 48 | `acc1[:] += A[0:16,0:2] @ B[0:2,1]` |
| 49~50 | A1의 뒤 16개에 `A[0:16,3]`를 읽고 A window를 col4 시작으로 이동 |
| 51~52 | B1의 뒤 8개에 `B[8:16,1]`를 읽고 B window를 col0의 row16 위치로 되돌림 |
| 54 | `acc0[:] += A[0:16,2:4] @ B[2:4,0]` |
| 55~56 | A0의 앞 16개를 `A[0:16,4]`로 교체하고 다음 col로 이동 |
| 57 | `acc1[:] += A[0:16,2:4] @ B[2:4,1]` |
| 58~59 | A0의 뒤 16개를 `A[0:16,5]`로 교체하고 다음 col로 이동 |

이후 line61/64는 A col4:6과 B row4:6, line68/71은 A col6:8과 B row6:8을
사용한다. line76/79에서는 미리 준비한 B1을 사용해 A col8:10과 B row8:10의
부분곱을 더한다. acc0/acc1은 입력 버퍼 교체 중에도 같은 출력 위치의 부분합을
유지한다. acc0는 출력 col0, acc1은 출력 col1의 16개 값을 나타낸다.

## 큰 행렬은 공간 분할과 시간 반복을 함께 사용

확인일: 2026-11-09. PL kernel5의 `compute.cpp`에서 `TX*TY*TZ` 반복과
load/send/receive/store 흐름을 확인했고, `send_receive.cpp`의 `receiveC`에서
기존 c_buf 값에 수신한 결과를 더하는 동작을 확인했다. AIE 내부 acc48 누산과
PL 출력 버퍼 누적은 서로 다른 단계다. PL 코드는 INT16 성분 단위 덧셈을 포함하므로
전체 정밀도가 끝까지 acc48로 유지된다고 가정하면 안 된다.

설명용 예로 (480×960) @ (960×480)을 48×48 출력 타일과 길이 3 cascade로
처리한다면 출력 타일은 10×10개이고, 타일 하나에 K 길이 96의 계산을 10번
반복해 더한다. 실제 생성 구성은 병렬 배열 및 X/Y/Z 버퍼 타일링에 따라 묶임과
스케줄이 달라진다. 이 예시는 생성·배치·실행 검증한 하드웨어 설정이 아니다.

## Cascade의 전달 단위

확인일: 2026-11-09. kernel0는 acc0/acc1 각각을 `ext_lo`, `ext_hi`로 나눠
두 번의 `writeincr_v8`로 전송한다. 이는 output vector 하나당 acc48 원소
16개이며, 전체 48×48 타일 계산 완료까지 기다렸다가 일괄 전송하는 구조가 아니다.
kernel1/2는 `readincr_v8`로 부분합을 받는다. A/B의 packet-to-window 입력과
부분합 cascade는 서로 다른 경로다. 단계별 계산이 겹칠 수 있으나 실제 cycle,
stall, throughput은 검증하지 않았다.

## 아직 확인해야 할 수치 동작

`srs(acc, 0)`은 시프트 0의 INT16 변환이다. 이것만 보고 overflow가 항상 wrap 또는
saturate라고 확정하지 않는다. 모드 설정과 실제 실행을 확인해야 한다.
현재 누산기는 원본의 48비트이며 AIE-ML의 다른 폭으로 변경하는 선택은 미확정이다.
