from __future__ import absolute_import
from __future__ import print_function
import sys
import os
from optparse import OptionParser

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYVERILOG_ROOT = os.path.join(PROJECT_ROOT, "Pyverilog_NeuroAbs")
if PYVERILOG_ROOT not in sys.path:
    sys.path.insert(0, PYVERILOG_ROOT)

from pyverilog.dataflow.dataflow import *
from filtering import *


import pyverilog
from pyverilog.dataflow.dataflow_analyzer import VerilogDataflowAnalyzer


def lineno_extractor(filelist, topmodule):
    INFO = "Verilog module signal/module dataflow analyzer"
    VERSION = pyverilog.__version__
    USAGE = "Usage: python example_dataflow_analyzer.py -t TOPMODULE file ..."


    filelists = [filelist]
    for f in filelists:
        if not os.path.exists(f):
            raise IOError("file not found: " + f)

    analyzer = VerilogDataflowAnalyzer(filelists, topmodule,
                                       noreorder=None,
                                       nobind=None,
                                       preprocess_include=None,
                                       preprocess_define=None)
    analyzer.generate()
    # directives = analyzer.get_directives()
    # print('Directive:')
    # for dr in sorted(directives, key=lambda x: str(x)):
    #     print(dr)

    # instances = analyzer.getInstances()
    # print('Instance:')
    # for module, instname in sorted(instances, key=lambda x: str(x[1])):
    #     print((module, instname))

    # if options.nobind:
    # print('Signal:')
    # signals = analyzer.getSignals()
    # for sig in signals:
    #     print(sig)

    # print('Const:')
    # consts = analyzer.getConsts()
    # for con in consts:
    #     print(con)

    # else:
    # terms = analyzer.getTerms()
    # print('Term:')
    # for tk, tv in sorted(terms.items(), key=lambda x: str(x[0])):
    #     print(tv.tostr())

    # binddict = analyzer.getBinddict()
    # print('Bind:')
    # for bk, bv in sorted(binddict.items(), key=lambda x: str(x[0])):
    #     for bvi in bv:
    #         print(bvi.tostr())
    

    return analyzer.line_map, analyzer.signal_width, analyzer.instance_map, analyzer.module_map

def get_signals(assignment_trees):
    signal_lists = []
    if isinstance(assignment_trees,DFBranch):
        if assignment_trees.condnode is not None:
            signals = get_signals(assignment_trees.condnode)
            for signal in signals:
                signal_lists.append(signal)
        if assignment_trees.truenode is not None:
            signals = get_signals(assignment_trees.truenode)
            for signal in signals:
                signal_lists.append(signal)
        if assignment_trees.falsenode is not None:
            signals = get_signals(assignment_trees.falsenode)
            for signal in signals:
                signal_lists.append(signal)
    
    elif isinstance(assignment_trees, DFTerminal):
        signal_lists.append(str(assignment_trees))
    
    elif(isinstance(assignment_trees, DFFloatConst) or isinstance(assignment_trees, DFIntConst) or  
        isinstance(assignment_trees, DFStringConst) or  isinstance(assignment_trees, DFEvalValue) or isinstance(assignment_trees, DFUndefined) or
        isinstance(assignment_trees, DFHighImpedance)):
        return []
    elif isinstance(assignment_trees, DFPartselect):
        signal_lists.append(str(assignment_trees.var))
    elif isinstance(assignment_trees, DFPointer):
        if assignment_trees.ptr is not None:
            signals = get_signals(assignment_trees.ptr)
            for signal in signals:
                signal_lists.append(signal)
        if assignment_trees.var is not None:
            signals = get_signals(assignment_trees.var)
            for signal in signals:
                signal_lists.append(signal)
    else:
        for element in assignment_trees.nextnodes:

            #     continue
            # else:
                signals = get_signals(element)
                for signal in signals:
                    signal_lists.append(signal)
    return signal_lists

def coi_analyze(abstract_vars, DCOI_vars, analyzer, topmodule, bound = 10):   
    
    terms = analyzer.getTerms()
    print('Term:')
    vars_in_coi = []
    for tk, tv in sorted(terms.items(), key=lambda x: str(x[0])):
        print(tv.tostr())
    # signal_assignment = analyzer.get_signal_assignment()
    binddict = analyzer.getBinddict()
    binddict_str = {}
    for bk, bv in sorted(binddict.items(), key=lambda x: str(x[0])):
        var = str(bk)
        var_new = var.replace(topmodule + '.','')
        binddict_str[var_new] = bv
    
    print('Bind:')
    for bk, bv in sorted(binddict.items(), key=lambda x: str(x[0])):
        for bvi in bv:
            print(bvi.tostr())    
            var = str(bk)
            # if(var == 'wrapper.RTL.rg_state'):
            #     print(var)
            
            var_new = var.replace(topmodule + '.','')
            if var_new not in abstract_vars:
                continue
            else:
                
                visited_signal = []
                terms_to_tanverse = [bvi.tree]
                next_bvi = False
                for i in range(bound):
                    for term in terms_to_tanverse:
                        signals = get_signals(term)    
                        new_terms = []        
                        for signal in signals:
                            signal_new = signal.replace(topmodule + '.','')
                            if signal_new in DCOI_vars:## If we find an abstract variable that will affect the DCOI_vars, we remove the abstraction.
                                # print("The abstract variable {:s} may affect the variable {:s} in the D-COI".format(signal_new,var_new))
                                print("The D-COI variable {:s} may affect the abstract variable {:s} in the D-COI".format(signal_new,var_new))
                                vars_in_coi.append(var_new)
                                next_bvi = True  # 设置标记
                                break
                            else: ## If we cannot find, we will continue our COI analyze
                                if signal_new not in visited_signal:
                                    visited_signal.append(signal_new)
                                    if signal_new in  binddict_str:
                                        signal_assignments = binddict_str[signal_new]        
                                        for signal_assignment in signal_assignments:
                                            new_terms.append(signal_assignment.tree)
                    
                        if next_bvi:  # 检查标记
                            break
                    if next_bvi:  # 检查标记
                        break
                    terms_to_tanverse = new_terms

# filelists = ['/data/zhiyuany/LLM4Abstraction/Piccolo_verification/verification/ADD/wrapper_abstract_llm_new_refine.v']
# topmodule = 'wrapper'
# DCOI_file= '/data/zhiyuany/LLM4Abstraction/Piccolo_verification/verification/ADD/coi-check-rev.txt'
# DCOI_vars = parse_influential_vars_file(DCOI_file)
# DCOI_vars = list(DCOI_vars)
# abstract_vars_file = '/data/zhiyuany/LLM4Abstraction/Piccolo_verification/verification/ADD/target_signal.txt'
# with open(abstract_vars_file,'r') as f:
#     abstract_vars = [line.strip() for line in f]

# for f in filelists:
#     if not os.path.exists(f):
#         raise IOError("file not found: " + f)
# analyzer = VerilogDataflowAnalyzer(filelists, topmodule,
#                                     noreorder=None,
#                                     nobind=None,
#                                     preprocess_include=None,
#                                     preprocess_define=None)
# analyzer.generate()
# coi_analyze(abstract_vars, DCOI_vars, analyzer, topmodule)
# lineno_extractor("/data/zhiyuany/LLM4Abstraction/Piccolo_verification/verification/ADD/wrapper_abstract_llm_new_refine_1.v",'wrapper')
