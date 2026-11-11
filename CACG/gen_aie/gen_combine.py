def gen_combine(environment,port_width,freq,L_list,HW_Conf,Port_Conf_All,Port_Conf_Pre,port_total,aie_folder,simulation_iterations=None,input_files=None,io_mode="plio",graph_names=None,verbose=True):
    template = environment.get_template("aie_top.cpp" if io_mode == "plio" else "aie_top_ports.h")
    file_tmp = "aie_top_all.cpp"
    filename = aie_folder / file_tmp
    content = template.render(
        port_width=port_width,
        freq=freq,
        L_list=L_list,
        HW_Conf=HW_Conf,
        Port_Conf=Port_Conf_All,
        Port_Conf_Pre=Port_Conf_Pre,
        port_total=port_total,
        simulation_iterations=simulation_iterations or [4]*len(L_list),
        input_files=input_files or [["data/input0.txt","data/input1.txt"] for _ in L_list],
        graph_names=graph_names
    )
    if io_mode == "ports":
        (aie_folder / "aie_top_all.h").write_text(content)
        content = '#include "aie_top_all.h"\n\n'
        content += '\n'.join(f'charm_array_{layer} {graph_names[layer]};' for layer in L_list) + '\n'
    with open(filename, mode="w", encoding="utf-8") as message:
        message.write(content)
        if verbose:
            print(f"... wrote {filename}")
