# Execute from the case directory; all artifacts remain inside it.
set cfg [open hls_settings.tcl r]
eval [read $cfg]
close $cfg
open_project -reset hls_project
set_top imagewam_mlp
add_files src/mlp.cpp -cflags "-Isrc"
add_files -tb src/mlp_tb.cpp -cflags "-Isrc"
open_solution -reset solution1 -flow_target vivado
set_part $imagewam_part
create_clock -period $imagewam_clock_ns -name default
csim_design
csynth_design
cosim_design -rtl verilog -trace_level port
exit
