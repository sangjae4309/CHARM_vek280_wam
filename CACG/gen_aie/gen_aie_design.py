from jinja2 import Environment, FileSystemLoader
from pathlib import Path
import numpy as np
import subprocess
import os
import sys
from .gen_array import*
from .gen_kernel import*
from .gen_combine import*
from .gen_plio_place import*
from ..kernel_families import KERNEL_FAMILIES

def gen_aie_top(prj_dir,template_dir,Model_MM,placement,input_data_dir=None,
                simulation_iterations=None, input_files=None, copy_input_data=True,
                io_mode="plio", graph_names=None, verbose=True):
    num_layer=Model_MM.shape[0]
    if io_mode not in ("plio", "ports"):
        raise ValueError("io_mode must be plio or ports")
    if graph_names is None:
        graph_names = [f"array_{i}" for i in range(num_layer)]
    if len(graph_names) != num_layer or len(set(graph_names)) != num_layer:
        raise ValueError("graph_names must be unique, one per array")
    if simulation_iterations is None:
        simulation_iterations = [4] * num_layer
    if len(simulation_iterations) != num_layer or any(int(n) != n or n <= 0 for n in simulation_iterations):
        raise ValueError("simulation_iterations must contain one positive integer per layer")
    if input_files is None:
        input_files = [["data/input0.txt", "data/input1.txt"] for _ in range(num_layer)]
    if len(input_files) != num_layer or any(len(paths) != 2 for paths in input_files):
        raise ValueError("input_files must contain one lhs/rhs pair per layer")
    port_width=128
    freq=230
    L_list=list(range(0,num_layer,1))
    families = list(Model_MM[:,11])
    for family, row in zip(families, Model_MM):
        if family not in KERNEL_FAMILIES:
            raise ValueError(f"Use a supported template family name, not a numeric ID: {family!r}")
        if int(row[10]) != KERNEL_FAMILIES[family]['bytes']:
            raise ValueError(f"Element width does not match {family}")
    dimensions = np.asarray(Model_MM[:,:11], dtype=int)
    HW_Conf=dimensions[:,3:]

    aie_dir= prj_dir + '/aie'
    subprocess.run(['mkdir','-p' ,f'{aie_dir}'])

    ### Copy Data 
    # A case may supply fixtures matching its tile shape and transport.
    data_dir = input_data_dir if input_data_dir is not None else os.path.join(template_dir, "data", families[0]) ##### Fix Me For Multiple Kernels#####
    copy_data = Path(data_dir)
    if copy_input_data:
        subprocess.run(['cp', '-r', copy_data, f'{prj_dir + "/data"}'], check=True)
    
    environment = {
        family: Environment(loader=FileSystemLoader(os.path.join(template_dir, family, "aie")))
        for family in set(families)
    }

    environment_combine = Environment(loader=FileSystemLoader(template_dir))

    
    Port_Conf_All = np.zeros((HW_Conf.shape[0],3)).astype(int)
    for i in range(HW_Conf.shape[0]):
        Port_Conf_All[i][0]=HW_Conf[i][0]*(HW_Conf[i][2]//HW_Conf[i][3])*(HW_Conf[i][1]//HW_Conf[i][5])  #lhs_port
        Port_Conf_All[i][1]=HW_Conf[i][2]*(HW_Conf[i][0]//HW_Conf[i][4])*(HW_Conf[i][1]//HW_Conf[i][5])  #rhs_port
        Port_Conf_All[i][2]=HW_Conf[i][0]*HW_Conf[i][2]//HW_Conf[i][6]                                   #out_port



    Port_Conf=Port_Conf_All[L_list,:]
    port_total=np.sum(Port_Conf, 0)

    Port_Conf_Temp = np.zeros((Port_Conf.shape[0],3)).astype(int)
    for i in range(Port_Conf.shape[0]):
        if i!=0:
            Port_Conf_Temp[i][0]=Port_Conf_Temp[i-1][0]+Port_Conf[i-1][0]
            Port_Conf_Temp[i][1]=Port_Conf_Temp[i-1][1]+Port_Conf[i-1][1]
            Port_Conf_Temp[i][2]=Port_Conf_Temp[i-1][2]+Port_Conf[i-1][2]
    Port_Conf_Pre = np.zeros((HW_Conf.shape[0],3)).astype(int)
    Port_Conf_Pre[L_list,:]= Port_Conf_Temp

    gen_combine(environment_combine,port_width,freq,L_list,HW_Conf,Port_Conf_All,Port_Conf_Pre,port_total,Path(aie_dir),simulation_iterations,input_files,io_mode,graph_names,verbose)

    Place_config=np.zeros((Port_Conf.shape[0],10)).astype(int)
    Place_config[:,0:7]=HW_Conf[:,0:7]
    Place_config[:,7:10]=placement[:,1:4]
    if io_mode == "plio":
        json_object=plio_placement(Place_config)
        with open(prj_dir+'/aie_top_all_aie_mapped.aiecst', "w") as outfile:
            outfile.write(json_object)

    for i in L_list:
        layer=i
        h1,w1,w2,A,B,C,A_BRO,C_BRO,PACK_IN,PACK_OUT,data_type = dimensions[layer]
        family = families[layer]
        file_dir=aie_dir + "/layer" + str(layer)
        layer_name=str(layer)

        pos_col  = placement[i][1]
        pos_row  = placement[i][2]
        height   = placement[i][3]
        subprocess.run(['mkdir','-p' ,file_dir])
        aie_folder = Path(file_dir)
        gen_para(environment[family],h1,w1,w2,A,B,C,A_BRO,C_BRO,PACK_IN,data_type,layer_name,aie_folder,verbose)
        gen_krnl(environment[family],w1,KERNEL_FAMILIES[family]['source_prefix'],layer_name,aie_folder,verbose)
        gen_grah(environment[family],B,layer_name,aie_folder,verbose)
        gen_toph(environment[family],A,B,C,A_BRO,C_BRO,PACK_IN,PACK_OUT,pos_col,pos_row,height,layer_name,aie_folder,verbose)

