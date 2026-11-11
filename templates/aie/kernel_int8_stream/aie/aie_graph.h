#ifndef __GRAPH_L{{layer}}_H__
#define __GRAPH_L{{layer}}_H__

#include <adf.h>
#include "para_L{{layer}}.h"
#include <stdio.h>
using namespace adf;


template <int COL_OFFSET, int ROW_OFFSET>
class mm_k6_B{{B}}_L{{layer}}: public graph {
  private:
    kernel mm[L{{layer}}_NUM_KERNEL];

  public:
    port<input> in0[L{{layer}}_NUM_KERNEL],in1[L{{layer}}_NUM_KERNEL];
    port<output> out;
    
    mm_k6_B{{B}}_L{{layer}}() {
      const int first_col = (ROW_OFFSET % 2 == 0)
          ? COL_OFFSET : COL_OFFSET - L{{layer}}_NUM_KERNEL + 1;
      {% if B ==1 %}
      mm[0] = kernel::create(mm6_kernel3_L{{layer}});
      source(mm[0]) = "mm6_kernel3_L{{layer}}.cc";
      runtime<ratio>(mm[0]) = 1;
      connect<window<L{{layer}}_h1*L{{layer}}_w1*L{{layer}}_Byte>>(in0[0], mm[0].in[0]);
      connect<window<L{{layer}}_w1*L{{layer}}_w2*L{{layer}}_Byte>>(in1[0], mm[0].in[1]);
      connect<window<L{{layer}}_h1*L{{layer}}_w2*L{{layer}}_Byte>>(mm[0].out[0], out);
      adf::location<kernel>(mm[0]) = adf::tile(COL_OFFSET,ROW_OFFSET);
      {% elif B > 1 %}
      for (int i=0; i<L{{layer}}_NUM_KERNEL;i++){
        if(i==0){
          mm[i] = kernel::create(mm6_kernel0_L{{layer}});
          source(mm[i]) = "mm6_kernel0_L{{layer}}.cc";
        }
        else if(i==L{{layer}}_NUM_KERNEL-1){
          mm[i] = kernel::create(mm6_kernel2_L{{layer}});
          source(mm[i]) = "mm6_kernel2_L{{layer}}.cc";
        }
        {% if B > 2 %}
        else{
          mm[i] = kernel::create(mm6_kernel1_L{{layer}});
          source(mm[i]) = "mm6_kernel1_L{{layer}}.cc";
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


      for (int i=0; i<L{{layer}}_NUM_KERNEL;i++){
        connect<window<L{{layer}}_h1*L{{layer}}_w1*L{{layer}}_Byte>>(in0[i], mm[i].in[0]);
        connect<window<L{{layer}}_w1*L{{layer}}_w2*L{{layer}}_Byte>>(in1[i], mm[i].in[1]);
      }

      for (int i=0; i<L{{layer}}_NUM_KERNEL;i++){
        if(i==L{{layer}}_NUM_KERNEL-1){
          connect<window<L{{layer}}_h1*L{{layer}}_w2*L{{layer}}_Byte>>(mm[i].out[0], out);
        }
        else{
          connect<cascade>(mm[i].out[0], mm[i+1].in[2]);
        }
      }
      {% endif %}

    };
    
};

#endif /**********__GRAPH_H__**********/