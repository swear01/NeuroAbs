

import os


def print_err_info(info_str):
    print("[ERROR] [aig] -- {}".format(info_str))

def print_warning_info(info_str):
    print("[WARNING] [aig] -- {}".format(info_str))

def print_info(info_str):
    print("[INFO] [aig] -- {}".format(info_str))

class aig:
    '''
    aig 
    '''
    def __init__(self, aig_file_path, aig_map_file_path = None):
        self.aig_map_file_path = aig_map_file_path
        self.aig_file_path = aig_file_path

        self.input_count = None
        self.latch_count = None
        self.output_count = None
        self.M = None
        self.and_gate_count = None


        self.aig_index_to_name = dict()
        self.name_to_aig_index = dict()

        # 
        self.latch_name_set = set()

        # derived by analyzing aig map
        self.name_to_width = dict()
        self.wire_name_to_aig_index = dict()


        self.error_info_file_path = "aig_index_to_name.log"
        self.analyze_aig_file()
        self.analyze_aig_map_file()

        self.is_verbose = False
    
    def get_aig_file_path(self):
        return self.aig_file_path
    

    def analyze_aig_map_file(self):
        if self.aig_map_file_path is None:
            return
        if not os.path.isfile(self.aig_map_file_path):
            print_warning_info(f"the aig map file path is invalid, get {self.aig_map_file_path}")
            return 
        with open(self.aig_map_file_path, 'r') as aig_map_file:
            aig_map_file_content = aig_map_file.readlines()
            for line in aig_map_file_content:
                line = line.strip()
                if "$" in line:
                    continue
                if not line.startswith("wire"):
                    # it's enough to only care about wire
                    continue
                var_name = line.split(" ")[-1]
                if not var_name in self.name_to_width:
                    self.name_to_width[var_name] = 1
                else:
                    self.name_to_width[var_name] += 1
                var_index = int(line.split(" ")[-2])
                try:
                    if var_index > 0:
                        # consider add some indexing stuff
                        if var_name in self.wire_name_to_aig_index:
                            tmp_aig_idx = self.wire_name_to_aig_index[var_name]
                            self.wire_name_to_aig_index.pop(var_name)
                            self.wire_name_to_aig_index[f"{var_name}[0]"] = tmp_aig_idx
                        # ↑ did some fix
                        self.wire_name_to_aig_index[f"{var_name}[{var_index}]"] = int(line.split(" ")[1])
                    else:
                        self.wire_name_to_aig_index[var_name] = int(line.split(" ")[1])
                        self.wire_name_to_aig_index[f"{var_name}[0]"] = int(line.split(" ")[1])
                except Exception as e:
                    l_l = line.split(" ")
                    print_err_info(f"var index = {var_index}, line split = {l_l}")
                    raise e

        # post process
        updated_name_to_width = dict()
        for var_name in self.name_to_width:
            width = self.name_to_width[var_name]
            updated_name_to_width[var_name] = width
            for i in range(width):
                updated_name_to_width[f"{var_name}[{i}]"] = 1
        self.name_to_width = updated_name_to_width
        print_info(f"aig map file {self.aig_map_file_path} is analyzed, get {len(self.name_to_width.keys())} variables in the width record")


    def analyze_aig_file(self):
        try:
            with open(self.aig_file_path, 'r', encoding='ascii') as aig_file:
                aig_file_content = aig_file.read()
                self.analyze_aig_file_content(aig_file_content = aig_file_content)
        except UnicodeDecodeError:
            print_err_info('the aig file {} is not encoded in ASCII'.format(self.aig_file_path))
            assert(False)

    def analyze_aig_file_content(self, aig_file_content):
        print_info("analyzing aig file {}".format(self.aig_file_path))
        aig_file_content = aig_file_content.split("\n")
        self.input_count = 0
        self.latch_count = 0
        for l in aig_file_content:
            if l.strip().startswith("aag"):
                line = l.strip()
                line_l = line.split(" ")
                self.M = int(line_l[1])
                self.latch_count = int(line_l[3])
                self.output_count = int(line_l[4])
                self.and_gate_count = int(line_l[5])
            l:str
            if l.startswith("i"):
                self.input_count += 1
            elif l.startswith("l"):
                # self.latch_count += 1
                latch_names = l.strip().split(" ")
                if len(latch_names) < 1:
                    print_err_info(f"there is unexpected latch name line at {l}, aig file name: {self.aig_file_path}")
                    raise ValueError()
                for ln in latch_names:
                    if ln.startswith("l"):
                        continue
                    if ln.startswith("!"):
                        ln = ln[1:]
                    if "[" in ln:
                        ln = ln.split("[")[0]
                    self.latch_name_set.add(ln)

        for l in aig_file_content:
            l:str
            if l.startswith("i"):
                l = l.strip()
                aig_index = int(l.split(" ")[0][1:])
                aig_name_list = l.split(" ")[1:]
                aig_index = aig_index + 1
                self.aig_index_to_name[aig_index] = aig_name_list
                for name in aig_name_list:
                    if name in self.name_to_aig_index:
                        print_err_info("overlapped name {} on aig index {}, existing aig index {}".format(name))
                        assert(False)
                    else:
                        self.name_to_aig_index[name] = aig_index
            elif l.startswith("l"):
                l = l.strip()
                aig_index = int(l.split(" ")[0][1:]) + self.input_count
                aig_index = aig_index + 1
                aig_name_list = l.split(" ")[1:]
                self.aig_index_to_name[aig_index] = aig_name_list
                for name in aig_name_list:
                    if name in self.name_to_aig_index:
                        print_err_info("overlapped name {} on aig index {}, existing aig index {}".format(name))
                        assert(False)
                    else:
                        self.name_to_aig_index[name] = aig_index
        
    def get_name_list(self, literal_index):
        assert(isinstance(literal_index, int))
        assert(literal_index > 1)
        if self.is_verbose:
            print_info(f"get name list for literal index {literal_index}, in aig file {self.aig_file_path}")
        invert = None
        if literal_index % 2 == 0:
            var_index = int(literal_index / 2)
            invert = False
        else:
            assert(literal_index % 2 == 1)
            var_index = int((literal_index - 1) / 2)
            invert = True
        try:
            name_list = self.aig_index_to_name[var_index]
        except KeyError:
            if self.is_verbose:
                print_warning_info("var index {} cannot find a name list, aig file name is {}".format(var_index, self.aig_file_path))
                if var_index >= self.input_count:
                    print_warning_info("try to check l{} in aig file".format(var_index - self.input_count))
                else:
                    print_warning_info("try to check i{} in aig file".format(var_index))
            return None, None
        
        if len(name_list) == 0:
            print_err_info("[ERROR] the length of aig name list is 0, current literal index = {}, aig file = {}".format(literal_index, self.aig_file_path))
            assert(False)
        
        if self.is_verbose:
            print_info(f"got name list for literal index {literal_index}: {name_list}")
        return name_list, invert
    
    def dump_aig_index_to_name_map_to_file(self):
        print_err_info("meet keyerror in get_name_list(), dump the aig index to name map for debugging")
        aig_index_to_name_map_str = ""

        for _ in self.aig_index_to_name.keys():
            aig_index_to_name_map_str += "{}:\t\t{}\n".format(_, self.aig_index_to_name[_])
        
        with open(self.error_info_file_path, 'w+') as error_info_file:
            error_info_file.write(aig_index_to_name_map_str)

    def dump_aig_name_to_index_map_to_file(self):
        print_err_info("meet keyerror in get_literal_index(), dump the aig index to name map for debugging")
        aig_index_to_name_map_str = ""

        for _ in self.aig_index_to_name.keys():
            aig_index_to_name_map_str += "{}:\t\t{}\n".format(_, self.aig_index_to_name[_])
        
        with open(self.error_info_file_path, 'w+') as error_info_file:
            error_info_file.write(aig_index_to_name_map_str)

    def get_literal_index(self, aig_name_list, invert):
        if aig_name_list is None:
            print_warning_info("the provided aig name list is None")
            raise ValueError()
        if self.is_verbose:
            print_info(f"try to get literal index for name list {aig_name_list} and invert {invert}, in aig file {self.aig_file_path}")
        literal_index = None
        aig_name_list_before_filter= aig_name_list.copy()
        aig_name_list = [_ for _ in aig_name_list if ".___extnets_" not in _]
        for aig_name in aig_name_list:
            invert_tmp = invert
            aig_name:str
            if aig_name in self.name_to_aig_index:
                aig_index = self.name_to_aig_index[aig_name]
                literal_index_tmp = 2 * aig_index
                if invert_tmp:
                    literal_index_tmp += 1
                if literal_index is not None:
                    if literal_index != literal_index_tmp: # this is only for check
                        print_err_info("Find multiple literal for aig names in aig name list: {}".format(aig_name_list))
                        print_err_info("  literal index = {}, literal index tmp = {}".format(literal_index, literal_index_tmp))
                else:
                    literal_index = literal_index_tmp
            aig_name_inv = aig_name[1:] if aig_name.startswith("!") else f"!{aig_name}"
            invert_tmp = not invert_tmp
            if aig_name_inv in self.name_to_aig_index:
                aig_index = self.name_to_aig_index[aig_name]
                literal_index_tmp = 2 * aig_index
                if invert_tmp:
                    literal_index_tmp += 1
                if literal_index is not None:
                    if literal_index != literal_index_tmp: # this is only for check
                        print_err_info("Find multiple literal for aig names in aig name list: {}".format(aig_name_list))
                        print_err_info("  literal index = {}, literal index tmp = {}".format(literal_index, literal_index_tmp))
                else:
                    literal_index = literal_index_tmp
        if literal_index is None:
            print_warning_info(f"Can not find literal for aig name list: {aig_name_list}, before filter: {aig_name_list_before_filter}, current aig file is {self.aig_file_path}, will raise a ValueError exception")
            raise ValueError("")
        if self.is_verbose:
            print_info(f"get index {literal_index} for literal index for name list {aig_name_list} and invert {invert}")
        return literal_index
    
    def get_number_of_latch(self):
        return self.latch_count


    def get_variable_width(self, var_name):
        if len(self.name_to_width) == 0:
            print_err_info(f"the variable width table does not contain anything, please check whether have analyed aig map file ")
            print_err_info(f"  aig map file path is {self.aig_map_file_path}")
        if not var_name in self.name_to_width:
            return None
        return self.name_to_width[var_name]

    def get_aig_content(self):
        with open(self.aig_file_path, 'r') as source_aig_file:
            return source_aig_file.readlines()
        

    def get_aig_content_inputs(self):
        aig_content_inputs = []
        with open(self.aig_file_path, 'r') as source_aig_file: 
            line = source_aig_file.readline()
            while line:
                line = line.strip()
                if line.strip().startswith("aag"):
                    line = source_aig_file.readline()
                    continue
                line = line.strip()
                line_l = line.split(" ")
                if len(line_l) == 1:
                    aig_content_inputs.append(line)
                if len(line_l) == 2:
                    break
                line = source_aig_file.readline()
        return aig_content_inputs

    def get_aig_content_latches(self):
        aig_content_latches = []
        with open(self.aig_file_path, 'r') as source_aig_file: 
            line = source_aig_file.readline()
            while line:
                line = line.strip()
                if line.strip().startswith("aag"):
                    line = source_aig_file.readline()
                    continue
                line = line.strip()
                line_l = line.split(" ")
                if len(line_l) == 2:
                    aig_content_latches.append(line)
                # add the case to remove the outputs
                if len(line_l) == 3 or (len(aig_content_latches) > 0 and len(line_l) == 1):
                    break
                line = source_aig_file.readline()
        return aig_content_latches
    
    def get_aig_content_and_gates(self):
        get_aig_content_and_gates = []
        with open(self.aig_file_path, 'r') as source_aig_file: 
            line = source_aig_file.readline()
            while line:
                line = line.strip()
                if line.strip().startswith("aag"):
                    line = source_aig_file.readline()
                    continue
                line = line.strip()
                line_l = line.split(" ")
                if not line[0].isdigit():
                    break
                if len(line_l) == 3:
                    get_aig_content_and_gates.append(line)
                
                line = source_aig_file.readline()
        return get_aig_content_and_gates

    def get_aig_content_body(self):
        aig_content_body = []
        with open(self.aig_file_path, 'r') as source_aig_file: 
            line = source_aig_file.readline()
            while line:
                if line[0].isdigit():
                    aig_content_body.append(line)
                else:
                    if not line.strip().startswith("aag"):
                        break
                line = source_aig_file.readline()
        return aig_content_body
    
    def get_aig_content_symbol(self):
        aig_content_symbol = []
        with open(self.aig_file_path, 'r') as source_aig_file: 
            line = source_aig_file.readline()
            line = line.strip()
            while line:
                if line[0] == "l" and line[1].isdigit():
                    aig_content_symbol.append(line)
                if line[0] == "i" and line[1].isdigit():
                    aig_content_symbol.append(line)
                if line[0] == "o" and line[1].isdigit():
                    # aig_content_symbol.append(line)
                    pass
                line = source_aig_file.readline()
        return aig_content_symbol
    
    def get_input_name_and_index(self):
        input_name_to_index = dict()
        for i in range(self.input_count):
            input_name_list, invert = self.get_name_list(literal_index=(i+1)*2)
            if input_name_list is None:
                print_err_info(f"the input {i} cannot find any corresponding stuffs, aig file is {self.aig_file_path}")
                raise ValueError()
            for input_name in input_name_list:
                input_name_to_index[input_name] = (i+1)*2
        return input_name_to_index
    
    def get_wire_index(self, wire_name):
        if wire_name in self.wire_name_to_aig_index:
            return self.wire_name_to_aig_index[wire_name]
        else:
            return None

    
    def get_M(self):

        if self.input_count is None:
            raise ValueError()
        if self.latch_count is None:
            raise ValueError()
        if self.and_gate_count is None:
            raise ValueError()

        return self.input_count + self.latch_count + self.and_gate_count
    
    def get_I(self):
        return self.input_count
    
    def get_L(self):
        return self.latch_count
    
    def get_A(self):
        return self.and_gate_count
    
    def sanity_check_compiled(self):
        '''
        sanity check for a aig dumped from incremental candidate compilation
        '''
        with open(self.aig_file_path, 'r') as aig_file:
            aig_file_content = aig_file.readlines()
        is_first_line = True
        sanity_check_I_count = None
        sanity_check_L_count = None
        sanity_check_M = None
        sanity_check_A_count = None
        sanity_check_O_count = None
        sanity_check_P_count = None

        start_input_lines = False
        input_lines_count = 0
        already_started_input_lines = False

        start_latch_lines = False
        latch_lines_count = 0
        already_started_latch_lines = False

        start_and_lines = False
        and_line_count = 0


        for line in aig_file_content:
            line = line.strip()
            line_l = line.split(" ")
            if is_first_line:
                if not line.startswith("aag"):
                    raise ValueError()
                sanity_check_M = int(line_l[1])
                sanity_check_I_count = int(line_l[2])
                sanity_check_L_count = int(line_l[3])
                sanity_check_O_count = int(line_l[4])
                sanity_check_A_count = int(line_l[5])
                if len(line_l) >= 7:
                    sanity_check_P_count = int(line_l[6])
                is_first_line = False

                assert(sanity_check_M == sanity_check_I_count + sanity_check_L_count + sanity_check_A_count)
                assert(sanity_check_O_count == 0)
                assert(sanity_check_P_count == 1)
            else:
                if line.startswith("i"):
                    continue
                if line.startswith("l"):
                    continue
                if line.startswith("o"):
                    continue
                if line.startswith("c"):
                    continue
                if line.startswith("Generated"):
                    continue
                for _ in line_l:
                    assert(_.isdigit())
                if len(line_l) == 1:
                    input_lines_count += 1
                elif len(line_l) == 2:
                    latch_lines_count += 1
                elif len(line_l) == 3:
                    and_line_count += 1
                else:
                    assert(False)
        assert(input_lines_count == sanity_check_I_count + 1)
        assert(and_line_count == sanity_check_A_count)
        assert(latch_lines_count == sanity_check_L_count)

    def get_is_latch(self, name):
        '''
        whether a verilog node is a latch
        for graph constructor to use in pyverilog
        '''
        name = str(name)
        return name in self.latch_name_set
    
    
def extract_different_from_aiger(aag, aag_constant):
    aag_parser = aig(aag)
    # print(len(aag_parser.latch_name_set))
    # for name in aag_parser.latch_name_set:
    #     print(name + '\n')
    aag_constant_parser = aig(aag_constant)
    extract_result = aag_parser.latch_name_set - aag_constant_parser.latch_name_set
    list_extract_result = list(extract_result)
    print(list_extract_result)
    return list_extract_result


# extract_different_from_aiger("/data/zhiyuany/LLM4Abstraction/riscv_formal/riscv_formal_add/picorv32.aag", "/data/zhiyuany/LLM4Abstraction/riscv_formal/riscv_formal_add/picorv32_const.aag")