#pragma once
#include <adf.h>
{% for layer in L_list -%}
#include "layer{{layer}}/aie_top_L{{layer}}.h"
{% endfor %}
// Logical packet interfaces only: no PLIO binding or simulator fixtures.
// Keep arrays separately controllable: their iteration counts are different.
{% for layer in L_list %}
{% set A = HW_Conf[layer][0] -%}
{% set B = HW_Conf[layer][1] -%}
{% set C = HW_Conf[layer][2] -%}
{% set A_BRO = HW_Conf[layer][3] -%}
{% set C_BRO = HW_Conf[layer][4] -%}
{% set PACK_IN = HW_Conf[layer][5] -%}
class charm_array_{{layer}} : public adf::graph {
public:
    adf::input_port lhs[{{Port_Conf[layer][0]}}];
    adf::input_port rhs[{{Port_Conf[layer][1]}}];
    adf::output_port out[{{Port_Conf[layer][2]}}];
    mm_x{{A}}_x{{B}}_x{{C}}_graph{{layer}} compute;

    charm_array_{{layer}}() {
        for (int i = 0; i < {{A * (C//A_BRO)}}; ++i) {
            for (int k = 0; k < {{B//PACK_IN}}; ++k) {
                adf::connect<adf::pktstream>(lhs[i*{{B//PACK_IN}}+k], compute.in_lhs[i][k]);
            }
        }
        for (int i = 0; i < {{C * (A//C_BRO)}}; ++i) {
            for (int k = 0; k < {{B//PACK_IN}}; ++k) {
                adf::connect<adf::pktstream>(rhs[i*{{B//PACK_IN}}+k], compute.in_rhs[i][k]);
            }
        }
        for (int i = 0; i < {{Port_Conf[layer][2]}}; ++i) {
            adf::connect<adf::pktstream>(compute.out[i], out[i]);
        }
    }
};
{% endfor %}
