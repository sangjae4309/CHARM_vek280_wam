{% for layer in L_list -%}
#include "layer{{layer}}/aie_top_L{{layer}}.h"
{% endfor %}
using namespace adf;

// Each layer remains a separately controllable graph named mm_graph<layer>.
// PLIOs belong to that graph; simulation::platform is obsolete in Vitis 2025.2.
{% for layer in L_list %}
{% set A = HW_Conf[layer][0] -%}
{% set B = HW_Conf[layer][1] -%}
{% set C = HW_Conf[layer][2] -%}
{% set A_BRO = HW_Conf[layer][3] -%}
{% set C_BRO = HW_Conf[layer][4] -%}
{% set PACK_IN = HW_Conf[layer][5] -%}
{% set PACK_OUT = HW_Conf[layer][6] -%}
class mm_io_graph_L{{layer}} : public adf::graph {
public:
    adf::input_plio lhs[{{Port_Conf[layer][0]}}];
    adf::input_plio rhs[{{Port_Conf[layer][1]}}];
    adf::output_plio result[{{Port_Conf[layer][2]}}];
    mm_x{{A}}_x{{B}}_x{{C}}_graph{{layer}} compute;

    mm_io_graph_L{{layer}}() {
{% for i in range(A) -%}
{% for j in range(C//A_BRO) -%}
{% for k in range(B//PACK_IN) -%}
{% set port = k+j*(B//PACK_IN)+i*(C//A_BRO)*(B//PACK_IN) %}
        lhs[{{port}}] = adf::input_plio::create(
            "LHS_in{{port}}_L{{layer}}", adf::plio_{{port_width}}_bits, {{ input_files[layer][0] | tojson }}, {{freq}});
        adf::connect<>(lhs[{{port}}].out[0], compute.in_lhs[{{j+i*(C//A_BRO)}}][{{k}}]);
{% endfor -%}
{% endfor -%}
{% endfor %}
{% for j in range(C) -%}
{% for i in range(A//C_BRO) -%}
{% for k in range(B//PACK_IN) -%}
{% set port = k+i*(B//PACK_IN)+j*(A//C_BRO)*(B//PACK_IN) %}
        rhs[{{port}}] = adf::input_plio::create(
            "RHS_in{{port}}_L{{layer}}", adf::plio_{{port_width}}_bits, {{ input_files[layer][1] | tojson }}, {{freq}});
        adf::connect<>(rhs[{{port}}].out[0], compute.in_rhs[{{i+j*(A//C_BRO)}}][{{k}}]);
{% endfor -%}
{% endfor -%}
{% endfor %}
{% for i in range(A) -%}
{% for j in range(C//PACK_OUT) -%}
{% set port = j+i*(C//PACK_OUT) %}
        result[{{port}}] = adf::output_plio::create(
            "out{{port}}_L{{layer}}", adf::plio_{{port_width}}_bits,
            "data/output{{port + Port_Conf_Pre[layer][2]}}.txt", {{freq}});
        adf::connect<>(compute.out[{{port}}], result[{{port}}].in[0]);
{% endfor -%}
{% endfor %}
    }
};

mm_io_graph_L{{layer}} mm_graph{{layer}};
{% endfor %}
#ifdef __AIESIM__
int main(int argc, char** argv) {
{% for layer in L_list %}
    mm_graph{{layer}}.init();
{% endfor %}
{% for layer in L_list %}
    mm_graph{{layer}}.run({{simulation_iterations[layer]}});
{% endfor %}
{% for layer in L_list %}
    mm_graph{{layer}}.end();
{% endfor %}
    return 0;
}
#endif
