#include <adf.h>
#include <stdio.h>
{% include "int8_mac8.inc" %}

const int h1=64;
const int w1=64;
const int w2=64;
const int boundry_i=h1/8;
const int boundry_j=w2/4;
const int boundry_k=w1/16-1;
const int jumpB0=w2*8;
const int jumpB1=w2*8+32;
const int jumpB2=32;
const int jumpA0=32;
const int jumpA1=(h1-8)*w1+32;


void mm_test(input_window_int8* __restrict matA,
		input_window_int8* __restrict matB,
		output_window_int8* __restrict matC){

	aie::vector<int8, 64> buf_matA0;//
	aie::vector<int8, 64> buf_matA1;//
			
	aie::vector<int8, 32> buf_matB0;// 
	aie::vector<int8, 32> buf_matB1;// 
	

	buf_matA0.insert(0, window_read_v<32>(matA));
	window_incr(matA,jumpA0);

	buf_matB0=window_read_v<32>(matB);
	window_incr(matB,jumpB0);

	buf_matA0.insert(1, window_read_v<32>(matA));
	window_incr(matA,jumpA0);
	
	for (int i=0;i<boundry_i;i++)
	//chess_prepare_for_pipelining
	//chess_loop_range(4,)
	{ //h1/8
		
		for (int j=0;j<boundry_j;j++)
		chess_prepare_for_pipelining
		chess_loop_range(boundry_j,){ //W2/4
			int jump;
			int jump1;
			if(j==boundry_j-1){
				jump=jumpA0;
				jump1=jumpB2;
			}
			else{
				jump=jumpA1;
				jump1=jumpB1;
			}
			

			aie::accum<acc64, 16> acc0 = aie::zeros<acc64, 16>();//
			aie::accum<acc64, 16> acc1 = aie::zeros<acc64, 16>();//
			for (int k=0;k<boundry_k;k++)
			chess_prepare_for_pipelining
			chess_loop_range(boundry_k,)
			{ //w1/16-1
				 
				acc0=int8_mac8<0x44440000>(acc0, buf_matA0, buf_matB0);
				buf_matA1.insert(0, window_read_v<32>(matA));
				window_incr(matA,jumpA0);
				buf_matB1=window_read_v<32>(matB);
				window_incr(matB,jumpB0);
			
				acc1=int8_mac8<0xCCCC8888>(acc1, buf_matA0, buf_matB0);
				buf_matA1.insert(1, window_read_v<32>(matA));
				window_incr(matA,jumpA0);

			
				acc0=int8_mac8<0x44440000>(acc0, buf_matA1, buf_matB1);
				buf_matA0.insert(0, window_read_v<32>(matA));
				window_incr(matA,jumpA0);
				buf_matB0=window_read_v<32>(matB);
				window_incr(matB,jumpB0);
			
				acc1=int8_mac8<0xCCCC8888>(acc1, buf_matA1, buf_matB1);
				buf_matA0.insert(1, window_read_v<32>(matA));
				window_incr(matA,jumpA0);
				
			}

			acc0=int8_mac8<0x44440000>(acc0, buf_matA0, buf_matB0);
			buf_matA1.insert(0, window_read_v<32>(matA));
			window_incr(matA,jumpA0);
			buf_matB1=window_read_v<32>(matB);
			window_incr(matB,jump1);
		
			acc1=int8_mac8<0xCCCC8888>(acc1, buf_matA0, buf_matB0);
			buf_matA1.insert(1, window_read_v<32>(matA));
			window_incr(matA,jump);
		
			acc0=int8_mac8<0x44440000>(acc0, buf_matA1, buf_matB1);
			buf_matA0.insert(0, window_read_v<32>(matA));
			window_incr(matA,jumpA0);
			buf_matB0=window_read_v<32>(matB);
			window_incr(matB,jumpB0);
			window_write(matC,acc0.to_vector<int8>(0));
			window_incr(matC,16);
			
		
			acc1=int8_mac8<0xCCCC8888>(acc1, buf_matA1, buf_matB1);
			buf_matA0.insert(1, window_read_v<32>(matA));
			window_incr(matA,jumpA0);
			window_write(matC,acc1.to_vector<int8>(0));
			window_incr(matC,16);
		}
	
	}
}