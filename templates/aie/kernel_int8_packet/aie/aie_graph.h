#ifndef __GRAPH_L{{layer}}_H__
#define __GRAPH_L{{layer}}_H__

#include <adf.h>
#include "para_L{{layer}}.h"
#include <stdio.h>
using namespace adf;


template <int COL_OFFSET, int ROW_OFFSET>
class mm_k7_B{{B}}_L{{layer}}: public graph {
  private:
    kernel mm[L{{layer}}_NUM_KERNEL];
    adf::pktsplit<L{{layer}}_NUM_KERNELS_PER_PAC>  sp_a0[L{{layer}}_NUM_PACK_IN];
    adf::pktsplit<L{{layer}}_NUM_KERNELS_PER_PAC>  sp_b0[L{{layer}}_NUM_PACK_IN];

  public:
    port<input> in0[L{{layer}}_NUM_PACK_IN],in1[L{{layer}}_NUM_PACK_IN];
    port<output> out;
    
    mm_k7_B{{B}}_L{{layer}}() {
      // AIE-ML cascades run west -> east on every row. Preserve the existing
      // chain footprint, including the right-edge anchor used on odd rows.
      const int first_col = (ROW_OFFSET % 2 == 0)
          ? COL_OFFSET : COL_OFFSET - L{{layer}}_NUM_KERNEL + 1;
      
      for (int j=0; j<L{{layer}}_NUM_PACK_IN; j++){
        sp_a0[j]  = adf::pktsplit<L{{layer}}_NUM_KERNELS_PER_PAC>::create();
		    sp_b0[j]  = adf::pktsplit<L{{layer}}_NUM_KERNELS_PER_PAC>::create();
		    adf::connect< adf::pktstream > (in0[j], sp_a0[j].in[0]);
		    adf::connect< adf::pktstream > (in1[j], sp_b0[j].in[0]);
      }

      for (int i=0; i<L{{layer}}_NUM_KERNEL;i++){
        if (L{{layer}}_NUM_KERNEL == 1) {
          mm[i] = kernel::create(mm7_kernel3_L{{layer}});
          source(mm[i]) = "mm7_kernel3_L{{layer}}.cc";
        }
        else if(i==0){
          mm[i] = kernel::create(mm7_kernel0_L{{layer}});
          source(mm[i]) = "mm7_kernel0_L{{layer}}.cc";
        }
        else if(i==L{{layer}}_NUM_KERNEL-1){
          mm[i] = kernel::create(mm7_kernel2_L{{layer}});
          source(mm[i]) = "mm7_kernel2_L{{layer}}.cc";
        }
        {% if B > 2 %}
        else{
          mm[i] = kernel::create(mm7_kernel1_L{{layer}});
          source(mm[i]) = "mm7_kernel1_L{{layer}}.cc";
        }
        {% endif %}
        runtime<ratio>(mm[i]) = 1;
        adf::location<kernel>(mm[i]) = adf::tile(first_col+i, ROW_OFFSET);
      }

      for (int i=0; i<L{{layer}}_NUM_KERNEL; i++) {
        const int col = first_col + i;
        const int a_row = ROW_OFFSET + ((ROW_OFFSET % 2 == 0) ? 1 : -1);
        // Retain CHARM's window sizes, ping/pong offsets and stack offset.
        // Placement still requires validation with the AIE-ML compiler.
        location<buffer>(mm[i].in[0]) =
          { address(col, a_row, 0x0000), address(col, a_row, 0x2000) };
        location<buffer>(mm[i].in[1]) =
          { address(col, ROW_OFFSET, 0x4000), address(col, ROW_OFFSET, 0x6000) };
        if (i == L{{layer}}_NUM_KERNEL-1) {
          const int out_col = (L{{layer}}_NUM_KERNEL == 1) ? col : col-1;
          location<buffer>(mm[i].out[0]) =
            { address(out_col, ROW_OFFSET, 0x5000), address(out_col, ROW_OFFSET, 0x7000) };
        }
        location<stack>(mm[i]) = address(col, ROW_OFFSET, 0x3000);
      }

      for (int j=0; j<L{{layer}}_NUM_PACK_IN; j++){
        for (int i=0; i<L{{layer}}_NUM_KERNELS_PER_PAC;i++){
          connect<pktstream,window<L{{layer}}_h1*L{{layer}}_w1*L{{layer}}_Byte>>(sp_a0[j].out[i], mm[i+j*L{{layer}}_NUM_KERNELS_PER_PAC].in[0]);
          connect<pktstream,window<L{{layer}}_w1*L{{layer}}_w2*L{{layer}}_Byte>>(sp_b0[j].out[i], mm[i+j*L{{layer}}_NUM_KERNELS_PER_PAC].in[1]);
        }
      }

      for (int i=0; i<L{{layer}}_NUM_KERNEL;i++){
        if(i==L{{layer}}_NUM_KERNEL-1){
          connect<window<L{{layer}}_h1*L{{layer}}_w2*L{{layer}}_Byte>>(mm[i].out[0], out);
        }
        else{
          connect<cascade>(mm[i].out[0], mm[i+1].in[2]);
        }
      }

    };
    
};

#endif /**********__GRAPH_H__**********/