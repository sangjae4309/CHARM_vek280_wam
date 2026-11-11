#ifndef PARA_L{{layer}}_H
#define PARA_L{{layer}}_H
#include <adf/stream/types.h>
const int L{{layer}}_Byte={{ data_type }};
const int L{{layer}}_NUM_KERNEL={{B}};
const int L{{layer}}_h1={{ h1 }};
const int L{{layer}}_w1={{ w1 }};
const int L{{layer}}_w2={{ w2 }};
const int L{{layer}}_boundary_i=L{{layer}}_h1/8;
const int L{{layer}}_boundary_j=L{{layer}}_w2/4;
const int L{{layer}}_boundary_k=L{{layer}}_w1/16-1;
const int L{{layer}}_judge_j=L{{layer}}_boundary_j-1;
const int L{{layer}}_jumpA0=32;
const int L{{layer}}_jumpA1=(L{{layer}}_h1-8)*L{{layer}}_w1+32;
const int L{{layer}}_jumpB0=32;
const int L{{layer}}_jumpB1=(L{{layer}}_w2-2)*16;
const int L{{layer}}_jumpB2=(L{{layer}}_w2+2)*16;

// The original sources unroll exactly 64 K terms per output value.
static_assert(L{{layer}}_Byte == 1, "INT8 requires one byte per element");
static_assert(L{{layer}}_w1 == 64, "Original INT8 schedule requires K=64");
static_assert(L{{layer}}_h1 > 0 && L{{layer}}_h1 % 8 == 0, "h1 must be a positive multiple of 8");
static_assert(L{{layer}}_w2 > 0 && L{{layer}}_w2 % 4 == 0, "w2 must be a positive multiple of 4");
static_assert(L{{layer}}_NUM_KERNEL > 0 &&
              1LL * L{{layer}}_NUM_KERNEL * 64 * 16384 < (1LL << 47),
              "Preserve the original acc48 range");
// Retained explicit addresses reserve 8 KiB for A and 4 KiB each for B/C.
static_assert(1LL * L{{layer}}_h1 * L{{layer}}_w1 <= 8192 &&
              1LL * L{{layer}}_w1 * L{{layer}}_w2 <= 4096 &&
              1LL * L{{layer}}_h1 * L{{layer}}_w2 <= 4096,
              "Tile exceeds the retained CHARM buffer regions");
static_assert({{PACK_IN}} == 1, "Ordinary stream requires PACK_IN=1");

void mm6_kernel0_L{{layer}}(input_window_int8* __restrict matA, input_window_int8*  __restrict matB, output_cascade<acc64>* __restrict matC);
void mm6_kernel1_L{{layer}}(input_window_int8* __restrict matA, input_window_int8*  __restrict matB, input_cascade<acc64>* __restrict acc_in, output_cascade<acc64>* __restrict matC);
void mm6_kernel2_L{{layer}}(input_window_int8* __restrict matA, input_window_int8*  __restrict matB, input_cascade<acc64>* __restrict acc_in, output_window_int8 * __restrict matC);
void mm6_kernel3_L{{layer}}(input_window_int8* __restrict matA, input_window_int8*  __restrict matB, output_window_int8 * __restrict matC);

#endif