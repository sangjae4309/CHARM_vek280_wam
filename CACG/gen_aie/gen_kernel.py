def gen_para(environment,h1,w1,w2,A,B,C,A_BRO,C_BRO,PACK_IN,data_type,layer,aie_folder,verbose=True):
    template = environment.get_template("para.h")
    file_tmp = "para_L" + str(layer) + ".h"
    filename = aie_folder / file_tmp
    content = template.render(
        h1=h1,
        w1=w1,
        w2=w2,
        A=A,
        B=B,
        C=C,
        A_BRO=A_BRO,
        C_BRO=C_BRO,
        PACK_IN=PACK_IN,
        data_type=data_type,
        layer=layer
    )
    with open(filename, mode="w", encoding="utf-8") as message:
        message.write(content)
        if verbose:
            print(f"... wrote {filename}")

def gen_krnl(environment,w1,source_prefix,layer,aie_folder,verbose=True):
    for i in range(4):
        bound_k=int(w1/16)-1
        kernel_name=f"{source_prefix}_kernel{i}.cc"
        template = environment.get_template(kernel_name)
        file_tmp=f"{source_prefix}_kernel{i}_L{layer}.cc"
        filename = aie_folder / file_tmp
        content = template.render(
            bound_k=bound_k,
            layer=layer
        )
        with open(filename, mode="w", encoding="utf-8") as message:
            message.write(content)
            if verbose:
                print(f"... wrote {filename}")

def gen_grah(environment,B,layer,aie_folder,verbose=True):
    graph_name= "aie_graph.h"
    template = environment.get_template(graph_name)
    file_tmp = "aie_graph_L" + str(layer) + ".h"
    filename = aie_folder / file_tmp
    content = template.render(
        B=B,
        layer=layer
    )
    with open(filename, mode="w", encoding="utf-8") as message:
        message.write(content)
        if verbose:
            print(f"... wrote {filename}")

