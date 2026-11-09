#include <adf.h>
    #include <stdio.h>
    #include "para_L{{layer}}.h"
{% include "kernel5_mac_pair.inc" %}

    void mm5_kernel1_L{{layer}}(input_window_int16* __restrict matA,
            input_window_int16* __restrict matB,
            input_cascade<acc64>* __restrict acc_in,
            output_cascade<acc64>* __restrict matC){


        aie::vector<int16, 32> buf_matA0;
        aie::vector<int16, 32> buf_matA1;
        aie::vector<int16, 16> buf_matB0;
        aie::vector<int16, 16> buf_matB1;

        buf_matA0.insert(0, window_read_v<16>(matA));
        window_incr(matA,L{{layer}}_h1);
        buf_matA0.insert(1, window_read_v<16>(matA));
        window_incr(matA,L{{layer}}_h1);

        buf_matB0.insert(0, window_read_v<8>(matB));
        window_incr(matB,L{{layer}}_w1);
        buf_matB0.insert(1, window_read_v<8>(matB));
        window_decr(matB,L{{layer}}_jump_B0);

        for (unsigned int i=0;i<L{{layer}}_boundary_i;i++)  //i/16
        chess_prepare_for_pipelining
        chess_loop_range(L{{layer}}_boundary_i,)
        {
            for (unsigned int j=0;j<L{{layer}}_boundary_j;j++)  // j/2
            chess_prepare_for_pipelining
            chess_loop_range(L{{layer}}_boundary_j,)
            {
                aie::accum<acc64, 16> acc0;
                acc0.insert(0, readincr_v<8>(acc_in));
                acc0.insert(1, readincr_v<8>(acc_in));
                aie::accum<acc64, 16> acc1;
                acc1.insert(0, readincr_v<8>(acc_in));
                acc1.insert(1, readincr_v<8>(acc_in));
                int jump=L{{layer}}_h1;
                if (j==L{{layer}}_judge_j){
                    jump=L{{layer}}_jump_A0;
                }
                else{
                    jump=L{{layer}}_h1;
                }

                acc0 = mm5_mac_pair<0>(acc0, buf_matA0, buf_matB0);
                buf_matA1.insert(0, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);
                buf_matB1.insert(0, window_read_v<8>(matB));
                window_incr(matB,L{{layer}}_w1);
                acc1 = mm5_mac_pair<8>(acc1, buf_matA0, buf_matB0);
                buf_matA1.insert(1, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);
                buf_matB1.insert(1, window_read_v<8>(matB));
                window_decr(matB,L{{layer}}_jump_B0);

                acc0 = mm5_mac_pair<2>(acc0, buf_matA1, buf_matB0);
                buf_matA0.insert(0, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);
                acc1 = mm5_mac_pair<10>(acc1, buf_matA1, buf_matB0);
                buf_matA0.insert(1, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);

                acc0 = mm5_mac_pair<4>(acc0, buf_matA0, buf_matB0);
                buf_matA1.insert(0, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);
                acc1 = mm5_mac_pair<12>(acc1, buf_matA0, buf_matB0);
                buf_matA1.insert(1, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);

                acc0 = mm5_mac_pair<6>(acc0, buf_matA1, buf_matB0);
                buf_matA0.insert(0, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);
                acc1 = mm5_mac_pair<14>(acc1, buf_matA1, buf_matB0);
                buf_matA0.insert(1, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);


                acc0 = mm5_mac_pair<0>(acc0, buf_matA0, buf_matB1);
                buf_matA1.insert(0, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);
                acc1 = mm5_mac_pair<8>(acc1, buf_matA0, buf_matB1);
                buf_matA1.insert(1, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);


                acc0 = mm5_mac_pair<2>(acc0, buf_matA1, buf_matB1);
                buf_matA0.insert(0, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);
                acc1 = mm5_mac_pair<10>(acc1, buf_matA1, buf_matB1);
                buf_matA0.insert(1, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);

                acc0 = mm5_mac_pair<4>(acc0, buf_matA0, buf_matB1);
                buf_matA1.insert(0, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);
                acc1 = mm5_mac_pair<12>(acc1, buf_matA0, buf_matB1);
                buf_matA1.insert(1, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);

                acc0 = mm5_mac_pair<6>(acc0, buf_matA1, buf_matB1);
                buf_matA0.insert(0, window_read_v<16>(matA));
                buf_matB0.insert(0, window_read_v<8>(matB));
                window_incr(matA,L{{layer}}_h1);
                window_incr(matB,L{{layer}}_w1);

                acc1 = mm5_mac_pair<14>(acc1, buf_matA1, buf_matB1);
                buf_matA0.insert(1, window_read_v<16>(matA));
                buf_matB0.insert(1, window_read_v<8>(matB));
                window_incr(matA,L{{layer}}_h1);
                window_decr(matB,L{{layer}}_jump_B0);

                acc0 = mm5_mac_pair<0>(acc0, buf_matA0, buf_matB0);
                buf_matA1.insert(0, window_read_v<16>(matA));
                buf_matB1.insert(0, window_read_v<8>(matB));
                window_incr(matA,L{{layer}}_h1);
                window_incr(matB,L{{layer}}_w1);
                acc1 = mm5_mac_pair<8>(acc1, buf_matA0, buf_matB0);
                buf_matB1.insert(1, window_read_v<8>(matB));
                buf_matA1.insert(1, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);
                window_incr(matB,8);
                acc0 = mm5_mac_pair<2>(acc0, buf_matA1, buf_matB0);
                buf_matA0.insert(0, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);
                acc1 = mm5_mac_pair<10>(acc1, buf_matA1, buf_matB0);
                buf_matA0.insert(1, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);

                acc0 = mm5_mac_pair<4>(acc0, buf_matA0, buf_matB0);
                buf_matA1.insert(0, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);
                acc1 = mm5_mac_pair<12>(acc1, buf_matA0, buf_matB0);
                buf_matA1.insert(1, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);

                acc0 = mm5_mac_pair<6>(acc0, buf_matA1, buf_matB0);
                buf_matA0.insert(0, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);
                acc1 = mm5_mac_pair<14>(acc1, buf_matA1, buf_matB0);
                buf_matA0.insert(1, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);


                acc0 = mm5_mac_pair<0>(acc0, buf_matA0, buf_matB1);
                buf_matA1.insert(0, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);
                acc1 = mm5_mac_pair<8>(acc1, buf_matA0, buf_matB1);
                buf_matA1.insert(1, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);


                acc0 = mm5_mac_pair<2>(acc0, buf_matA1, buf_matB1);
                buf_matA0.insert(0, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);
                acc1 = mm5_mac_pair<10>(acc1, buf_matA1, buf_matB1);
                buf_matA0.insert(1, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);

                acc0 = mm5_mac_pair<4>(acc0, buf_matA0, buf_matB1);
                buf_matA1.insert(0, window_read_v<16>(matA));
                window_incr(matA,L{{layer}}_h1);
                acc1 = mm5_mac_pair<12>(acc1, buf_matA0, buf_matB1);
                buf_matA1.insert(1, window_read_v<16>(matA));
                window_incr(matA,jump);


                acc0 = mm5_mac_pair<6>(acc0, buf_matA1, buf_matB1);
                writeincr(matC, acc0.extract<8>(0));
                writeincr(matC, acc0.extract<8>(1));

                buf_matA0.insert(0, window_read_v<16>(matA));
                buf_matB0.insert(0, window_read_v<8>(matB));
                window_incr(matA,L{{layer}}_h1);
                window_incr(matB,L{{layer}}_w1);

                acc1 = mm5_mac_pair<14>(acc1, buf_matA1, buf_matB1);
                writeincr(matC, acc1.extract<8>(0));
                writeincr(matC, acc1.extract<8>(1));

                buf_matA0.insert(1, window_read_v<16>(matA));
                buf_matB0.insert(1, window_read_v<8>(matB));
                window_incr(matA,L{{layer}}_h1);
                window_decr(matB,L{{layer}}_jump_B0);
            }
        }
    }
