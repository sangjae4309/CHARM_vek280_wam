from jinja2 import Environment, FileSystemLoader
from pathlib import Path
import numpy as np
import subprocess
import os
from .gen_krl import*
from ..kernel_families import KERNEL_FAMILIES

def gen_pl_top(prj_dir,template_dir,hw_config,BUFF_SEL):
    num_krl=hw_config.shape[0]
    pl_dir= prj_dir + '/kernel'
    gen_conn_top(prj_dir,template_dir,hw_config)
    for acc in range(num_krl):
        h1,w1,w2,A,B,C,A_BRO,C_BRO,PACK_IN,PACK_OUT,X,Y,Z,data_type=np.asarray(hw_config[acc,:14],dtype=int)
        family=hw_config[acc,14]
        if family not in KERNEL_FAMILIES:
            raise ValueError(f"Use a supported template family name, not a numeric ID: {family!r}")
        if data_type != KERNEL_FAMILIES[family]['bytes']:
            raise ValueError(f"Element width does not match {family}")
        pl_dir_krl=pl_dir + str(acc)
        subprocess.run(['mkdir','-p' ,f'{pl_dir_krl}'])
        environment = Environment(loader=FileSystemLoader(os.path.join(template_dir, family)))

        krl_folder = Path(pl_dir_krl)
        
        BUFF_SEL_TEXT=['BRAM','BRAM','BRAM']
        for i in range(3):
            if BUFF_SEL[acc,i]==0:
                BUFF_SEL_TEXT[i]='BRAM'
            else:
                BUFF_SEL_TEXT[i]='URAM'

        gen_para(environment,h1,w1,w2,A,B,C,A_BRO,C_BRO,PACK_IN,PACK_OUT,X,Y,Z,data_type,acc,krl_folder)
        gen_ddr (environment,acc,krl_folder)
        gen_send(environment,A,C,A_BRO,C_BRO,PACK_IN,PACK_OUT,acc,krl_folder)
        gen_compute(environment,A,B,C,A_BRO,C_BRO,PACK_IN,PACK_OUT,BUFF_SEL_TEXT,acc,krl_folder)
        gen_krl_top(environment,A,B,C,A_BRO,C_BRO,PACK_IN,PACK_OUT,acc,krl_folder)

def gen_conn_top(prj_dir,template_dir,hw_config):
    prj_folder = Path(prj_dir)
    Conn_Array_temp = np.asarray(hw_config[:,3:10],dtype=int)
    num_layer = hw_config.shape[0]
    Conn_Array=np.zeros((num_layer,7)).astype(int)
    Conn_Array[:,0:3]=Conn_Array_temp[:,0:3]
    Conn_Array[:,3]=np.floor_divide(Conn_Array_temp[:,2],Conn_Array_temp[:,3])#NUM_TXL
    Conn_Array[:,4]=np.floor_divide(Conn_Array_temp[:,0],Conn_Array_temp[:,4])#NUM_TXR
    Conn_Array[:,5:7]=Conn_Array_temp[:,5:7]
    
    ### Define template PATH
    environment = Environment(loader=FileSystemLoader(template_dir))
    gen_conn(environment,Conn_Array,num_layer,prj_folder)
