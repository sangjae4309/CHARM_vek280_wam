#include <adf.h>
#include <stdio.h>
{% include "int8_mac8.inc" %}
#include "para_L{{layer}}.h"
void mm7_kernel0_L{{layer}}(input_window_int8* __restrict matA, 
        input_window_int8*  __restrict matB,
        output_cascade<acc64>* __restrict matC){

    aie::vector<int8, 64> buf_matA0;
    aie::vector<int8, 64> buf_matA1;
            
    aie::vector<int8, 32> buf_matB0; 
    aie::vector<int8, 32> buf_matB1; 
    

    buf_matA0.insert(0, window_read_v<32>(matA));
    window_incr(matA,L{{layer}}_jumpA0);

    buf_matB0=window_read_v<32>(matB);
    window_incr(matB,L{{layer}}_jumpB0);

    buf_matA0.insert(1, window_read_v<32>(matA));
    window_incr(matA,L{{layer}}_jumpA0);

    for (int i=0;i<L{{layer}}_boundary_i;i++)
    chess_prepare_for_pipelining
    chess_loop_range(L{{layer}}_boundary_i,)
    {
        for (int j=0;j<L{{layer}}_boundary_j;j++)
        chess_prepare_for_pipelining
        chess_loop_range(L{{layer}}_boundary_j,)
        {

            int jumpA=L{{layer}}_jumpA1;
            int jumpB=L{{layer}}_jumpB2;
            if(j==L{{layer}}_judge_j){
                jumpA=L{{layer}}_jumpA0;
                jumpB=L{{layer}}_jumpB0;
            }

            aie::accum<acc64, 16> acc0 = aie::zeros<acc64, 16>();
            aie::accum<acc64, 16> acc1 = aie::zeros<acc64, 16>();      

            //K iteration 0
            acc0=int8_mac8<0x88880000>(acc0, buf_matA0, buf_matB0);
            buf_matA1.insert(0, window_read_v<32>(matA));
            window_incr(matA,L{{layer}}_jumpA0);
            buf_matB1=window_read_v<32>(matB);
            window_incr(matB,L{{layer}}_jumpB1);

            acc1=int8_mac8<0x88880000>(acc1, buf_matA0, buf_matB1);
            buf_matA1.insert(1, window_read_v<32>(matA));
            window_incr(matA,L{{layer}}_jumpA0);

            acc0=int8_mac8<0xCCCC4444>(acc0, buf_matA1, buf_matB0);
            buf_matA0.insert(0, window_read_v<32>(matA));
            window_incr(matA,L{{layer}}_jumpA0);

            acc1=int8_mac8<0xCCCC4444>(acc1, buf_matA1, buf_matB1);
            buf_matA0.insert(1, window_read_v<32>(matA));
            window_incr(matA,L{{layer}}_jumpA0);
            buf_matB0=window_read_v<32>(matB); 
            window_incr(matB,L{{layer}}_jumpB0);

            //K iteration 1
            acc0=int8_mac8<0x88880000>(acc0, buf_matA0, buf_matB0);
            buf_matA1.insert(0, window_read_v<32>(matA));
            window_incr(matA,L{{layer}}_jumpA0);
            buf_matB1=window_read_v<32>(matB);
            window_incr(matB,L{{layer}}_jumpB1);

            acc1=int8_mac8<0x88880000>(acc1, buf_matA0, buf_matB1);
            buf_matA1.insert(1, window_read_v<32>(matA));
            window_incr(matA,L{{layer}}_jumpA0);

            acc0=int8_mac8<0xCCCC4444>(acc0, buf_matA1, buf_matB0);
            buf_matA0.insert(0, window_read_v<32>(matA));
            window_incr(matA,L{{layer}}_jumpA0);

            acc1=int8_mac8<0xCCCC4444>(acc1, buf_matA1, buf_matB1);
            buf_matA0.insert(1, window_read_v<32>(matA));
            window_incr(matA,L{{layer}}_jumpA0);
            buf_matB0=window_read_v<32>(matB); 
            window_incr(matB,L{{layer}}_jumpB0);

            //K iteration 2
            acc0=int8_mac8<0x88880000>(acc0, buf_matA0, buf_matB0);
            buf_matA1.insert(0, window_read_v<32>(matA));
            window_incr(matA,L{{layer}}_jumpA0);
            buf_matB1=window_read_v<32>(matB);
            window_incr(matB,L{{layer}}_jumpB1);

            acc1=int8_mac8<0x88880000>(acc1, buf_matA0, buf_matB1);
            buf_matA1.insert(1, window_read_v<32>(matA));
            window_incr(matA,L{{layer}}_jumpA0);

            acc0=int8_mac8<0xCCCC4444>(acc0, buf_matA1, buf_matB0);
            buf_matA0.insert(0, window_read_v<32>(matA));
            window_incr(matA,L{{layer}}_jumpA0);

            acc1=int8_mac8<0xCCCC4444>(acc1, buf_matA1, buf_matB1);
            buf_matA0.insert(1, window_read_v<32>(matA));
            window_incr(matA,L{{layer}}_jumpA0);
            buf_matB0=window_read_v<32>(matB); 
            window_incr(matB,L{{layer}}_jumpB0);

            //K iteration 3
            acc0=int8_mac8<0x88880000>(acc0, buf_matA0, buf_matB0);
            buf_matA1.insert(0, window_read_v<32>(matA));
            window_incr(matA,L{{layer}}_jumpA0);
            buf_matB1=window_read_v<32>(matB);
            window_incr(matB,jumpB);

            acc1=int8_mac8<0x88880000>(acc1, buf_matA0, buf_matB1);
            buf_matA1.insert(1, window_read_v<32>(matA));
            window_incr(matA,jumpA);//jump

            acc0=int8_mac8<0xCCCC4444>(acc0, buf_matA1, buf_matB0);
            buf_matA0.insert(0, window_read_v<32>(matA));
            window_incr(matA,L{{layer}}_jumpA0);
            writeincr(matC, acc0.extract<8>(0));
            writeincr(matC, acc0.extract<8>(1));

            acc1=int8_mac8<0xCCCC4444>(acc1, buf_matA1, buf_matB1);
            buf_matA0.insert(1, window_read_v<32>(matA));
            window_incr(matA,L{{layer}}_jumpA0);
            buf_matB0=window_read_v<32>(matB); 
            window_incr(matB,L{{layer}}_jumpB0);
            writeincr(matC, acc1.extract<8>(0));
            writeincr(matC, acc1.extract<8>(1));
            
        }
    }

}