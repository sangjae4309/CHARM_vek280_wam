#ifndef PARA_L{{layer}}_H
#define PARA_L{{layer}}_H
#include <adf/stream/types.h>
const int L{{layer}}_Byte={{ data_type }};
const int L{{layer}}_NUM_KERNEL={{B}};
const int L{{layer}}_NUM_KERNELS_PER_PAC={{PACK_IN}};
const int L{{layer}}_NUM_PACK_IN=L{{layer}}_NUM_KERNEL/L{{layer}}_NUM_KERNELS_PER_PAC;
const int L{{layer}}_h1={{ h1 }};
const int L{{layer}}_w1=32;
const int L{{layer}}_w2={{ w2 }};
const int L{{layer}}_boundary_i=L{{layer}}_h1/16;
const int L{{layer}}_boundary_j=L{{layer}}_w2/2;
const int L{{layer}}_boundary_k=L{{layer}}_w1/16-1;
const int L{{layer}}_jump_B0=L{{layer}}_w1-8;
const int L{{layer}}_jump_A0=L{{layer}}_h1+16;
const int L{{layer}}_judge_i=L{{layer}}_boundary_i-1;
const int L{{layer}}_judge_j=L{{layer}}_boundary_j-1;

// Preserve the original 16-row / 2-col output blocking and K=32 contract.
static_assert(L{{layer}}_Byte == 2, "kernel5 requires INT16 inputs");
static_assert(L{{layer}}_h1 > 0 && L{{layer}}_h1 % 16 == 0, "h1 must be a positive multiple of 16");
static_assert(L{{layer}}_w2 > 0 && L{{layer}}_w2 % 2 == 0, "w2 must be a positive multiple of 2");
static_assert(L{{layer}}_NUM_KERNEL > 0 && L{{layer}}_NUM_KERNEL <= 4095,
              "Keep the worst-case INT16 cascade sum within signed acc48 range");
static_assert(L{{layer}}_NUM_KERNELS_PER_PAC > 0 &&
              L{{layer}}_NUM_KERNEL % L{{layer}}_NUM_KERNELS_PER_PAC == 0,
              "PACK_IN must divide the cascade length");

void mm5_kernel0_L{{layer}}(input_window_int16* __restrict matA, input_window_int16*  __restrict matB, output_cascade<acc64>* __restrict matC);
void mm5_kernel1_L{{layer}}(input_window_int16* __restrict matA, input_window_int16*  __restrict matB, input_cascade<acc64>* __restrict acc_in, output_cascade<acc64>* __restrict matC);
void mm5_kernel2_L{{layer}}(input_window_int16* __restrict matA, input_window_int16*  __restrict matB, input_cascade<acc64>* __restrict acc_in, output_window_int16 * __restrict matC);
void mm5_kernel3_L{{layer}}(input_window_int16* __restrict matA, input_window_int16*  __restrict matB, output_window_int16 * __restrict matC);

#endif
