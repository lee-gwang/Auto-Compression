import timeit
import torch
from collections import OrderedDict
import gc
from fbnet_building_blocks.fbnet_builder import PRIMITIVES
from general_functions.utils import add_text_to_file, clear_files_in_the_list
from supernet_functions.config_for_supernet import CONFIG_SUPERNET
import numpy as np
import sys
import math
import copy

np.set_printoptions(threshold=sys.maxsize)
# the settings from the page 4 of https://arxiv.org/pdf/1812.03443.pdf
#### table 2
#CANDIDATE_BLOCKS = ["ir_k3_e1", "ir_k3_s2", "ir_k3_e3",
#                    "ir_k3_e6", "ir_k5_e1", "ir_k5_s2",
#                    "ir_k5_e3", "ir_k5_e6", "skip"]
CANDIDATE_HIGH = ["A4_W4", "A4_W5", "A4_W6", "A6_W4", "A6_W5", "A6_W6"]

CANDIDATE_BLOCKS = ["quant_a1_w1", "quant_a2_w2", "quant_a3_w3"]
SEARCH_SPACE = OrderedDict([
    #### table 1. input shapes of 22 searched layers (considering with strides)
    # Note: the second and third dimentions are recommended (will not be used in training) and written just for debagging
    ("input_shape", [(3, 224, 224),
                     (32, 112, 112), (16, 112, 112),  (24, 56, 56),  (24, 56, 56),
                     (32, 28, 28), (32, 28, 28), (32, 14, 14), (64, 14, 14), (64, 14, 14), (64, 14, 14), (64, 14, 14),
                     (96, 14, 14), (96, 7, 7), (96, 7, 7), (160, 7, 7), (160, 7, 7), (160, 7, 7), (320, 7, 7)]),
    # table 1. filter numbers over the 22 layers
    ("channel_size", [32, 16, 24, 24, 32, 32, 32, 64, 64, 64, 64,
                      96, 96, 96, 160, 160, 160, 320, 1280]),
    # table 1. strides over the 22 layers
    ("strides", [2, 1, 2, 1, 2, 1, 1, 2, 1, 1, 1, 1, 1, 1,
                 2, 1, 1, 1, 1]),
    ("expansion", [-1, 1, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, -1]),
    ("Activation", [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3]),
    ("Weight", [7, 4, 3, 4, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 3, 3, 3, 3, 3])
])

class LookUpTable_HIGH:
    def __init__(self, candidate_blocks=CANDIDATE_HIGH, search_space=SEARCH_SPACE,
                 calulate_latency=False):
        self.cnt_layers = len(search_space["input_shape"])
        self.search_space=SEARCH_SPACE
        self.candidate=CANDIDATE_HIGH
        # constructors for each operation
        self.lookup_table_operations = {op_name : PRIMITIVES[op_name] for op_name in candidate_blocks}
        # arguments for the ops constructors. one set of arguments for all 9 constructors at each layer
        # input_shapes just for convinience
        self.layers_parameters, self.layers_input_shapes = self._generate_layers_parameters(search_space)
        
        # lookup_table
        self.lookup_table_latency = None
        if calulate_latency:
            self._create_from_operations(cnt_of_runs=CONFIG_SUPERNET['lookup_table']['number_of_runs'],
                                         write_to_file=CONFIG_SUPERNET['lookup_table']['path_to_lookup_table_high'])
        else:
            self._create_from_file(path_to_file=CONFIG_SUPERNET['lookup_table']['path_to_lookup_table_high'])
    
    def _generate_layers_parameters(self, search_space):
        # layers_parameters are : C_in, C_out, expansion, stride
        layers_parameters = [((search_space["input_shape"][layer_id][0],
                              search_space["channel_size"][layer_id],
                              search_space["Activation"][layer_id],
                              search_space["Weight"][layer_id],
                              search_space["strides"][layer_id],
                              search_space["expansion"][layer_id],
                              None),
                              (search_space["input_shape"][layer_id][0],
                              search_space["channel_size"][layer_id],
                              search_space["Activation"][layer_id],
                              search_space["Weight"][layer_id],
                              search_space["strides"][layer_id],
                              search_space["expansion"][layer_id],
                              None),
                              (search_space["input_shape"][layer_id][0],
                              search_space["channel_size"][layer_id],
                              search_space["Activation"][layer_id],
                              search_space["Weight"][layer_id],
                              search_space["strides"][layer_id],
                              search_space["expansion"][layer_id],
                              None),
                              (search_space["input_shape"][layer_id][0],
                              search_space["channel_size"][layer_id],
                              search_space["Activation"][layer_id],
                              search_space["Weight"][layer_id],
                              search_space["strides"][layer_id],
                              search_space["expansion"][layer_id],
                              None),
                              (search_space["input_shape"][layer_id][0],
                              search_space["channel_size"][layer_id],
                              search_space["Activation"][layer_id],
                              search_space["Weight"][layer_id],
                              search_space["strides"][layer_id],
                              search_space["expansion"][layer_id],
                              None),
                              (search_space["input_shape"][layer_id][0],
                              search_space["channel_size"][layer_id],
                              search_space["Activation"][layer_id],
                              search_space["Weight"][layer_id],
                              search_space["strides"][layer_id],
                              search_space["expansion"][layer_id],
                              None),

                            ) for layer_id in range(self.cnt_layers)]

        # layers_input_shapes are (C_in, input_w, input_h)
        layers_input_shapes = search_space["input_shape"]
        
        return layers_parameters, layers_input_shapes
    
    # CNT_OP_RUNS us number of times to check latency (we will take average)
    def _create_from_operations(self, cnt_of_runs, write_to_file=None):
        self.lookup_table_latency = self._calculate_latency(self.lookup_table_operations,
                                                            self.layers_parameters,
                                                            self.layers_input_shapes,
                                                            cnt_of_runs)
        if write_to_file is not None:
            self._write_lookup_table_to_file(write_to_file)
    
    def _calculate_latency(self, operations, layers_parameters, layers_input_shapes, cnt_of_runs):
        LATENCY_BATCH_SIZE = 1
        latency_table_layer_by_ops = [{} for i in range(self.cnt_layers)]
        
        for layer_id in range(self.cnt_layers):
            for op_name in operations:
                op = operations[op_name](*layers_parameters[layer_id])
                input_sample = torch.randn((LATENCY_BATCH_SIZE, *layers_input_shapes[layer_id]))
                globals()['op'], globals()['input_sample'] = op, input_sample
                total_time = timeit.timeit('output = op(input_sample)', setup="gc.enable()", \
                                           globals=globals(), number=cnt_of_runs)
                # measured in micro-second
                latency_table_layer_by_ops[layer_id][op_name] = total_time / cnt_of_runs / LATENCY_BATCH_SIZE * 1e6
        return latency_table_layer_by_ops
    
    def _write_lookup_table_to_file(self, path_to_file):
        clear_files_in_the_list([path_to_file])
        ops = [op_name for op_name in self.lookup_table_operations]
        text = [op_name + " " for op_name in ops[:-1]]
        text.append(ops[-1] + "\n")
        
        for layer_id in range(self.cnt_layers):
            for op_name in ops:
                text.append(str(self.lookup_table_latency[layer_id][op_name]))
                text.append(" ")
            text[-1] = "\n"
        text = text[:-1]
        
        text = ''.join(text)
        add_text_to_file(text, path_to_file)
    
    def _create_from_file(self, path_to_file):
        self.lookup_table_latency = self._read_lookup_table_from_file(path_to_file)
    
    def _read_lookup_table_from_file(self, path_to_file):
        latences = [line.strip('\n') for line in open(path_to_file)]
        ops_names = latences[0].split(" ")
        latences = [list(map(float, layer.split(" "))) for layer in latences[1:]]
        
        lookup_table_latency = [{op_name : latences[i][op_id] 
                                      for op_id, op_name in enumerate(ops_names)
                                     } for i in range(self.cnt_layers)]
        return lookup_table_latency
# **** to recalculate latency use command:
# l_table = LookUpTable(calulate_latency=True, path_to_file='lookup_table.txt', cnt_of_runs=50)
# results will be written to './supernet_functions/lookup_table.txt''
# **** to read latency from the another file use command:
# l_table = LookUpTable(calulate_latency=False, path_to_file='lookup_table.txt')
class LookUpTable:
    def __init__(self, candidate_blocks=CANDIDATE_BLOCKS, search_space=SEARCH_SPACE,
                 calulate_latency=False, count=0, act_update=[], weight_update=[]):
        self.cnt_layers = len(search_space["input_shape"])
        '''
        global SEARCH_SPACE
        SEARCH_SPACE["Activation"] = act_update
        for i in range(len(search_space["Weight"])):
            SEARCH_SPACE["Weight"][i] += weight_update[i]
        print(SEARCH_SPACE["Activation"])
        print(SEARCH_SPACE["Weight"])
        '''
        # constructors for each operation
        self.lookup_table_operations = {op_name : PRIMITIVES[op_name] for op_name in candidate_blocks}
        # arguments for the ops constructors. one set of arguments for all 9 constructors at each layer
        # input_shapes just for convinience
        self.count = count
        self.index = []
        for i in range(3):
            self.index.append(self._generate_index(search_space["Weight"]))

        self.layers_parameters, self.layers_input_shapes = self._generate_layers_parameters(search_space)
        
        # lookup_table
        self.lookup_table_latency = None
        if calulate_latency:
            self._create_from_operations(cnt_of_runs=CONFIG_SUPERNET['lookup_table']['number_of_runs'],
                                         write_to_file=CONFIG_SUPERNET['lookup_table']['path_to_lookup_table'])
        else:
            self._create_from_file(path_to_file=CONFIG_SUPERNET['lookup_table']['path_to_lookup_table'])
    

    def _generate_layers_parameters(self, search_space):
        # layers_parameters are : C_in, C_out, expansion, stride
        layers_parameters = [((search_space["input_shape"][layer_id][0],
                              search_space["channel_size"][layer_id],
                              search_space["Activation"][layer_id],
                              search_space["Weight"][layer_id],
                              search_space["strides"][layer_id],
                              search_space["expansion"][layer_id],
                              self.index[0], layer_id),
                              (search_space["input_shape"][layer_id][0],
                              search_space["channel_size"][layer_id],
                              search_space["Activation"][layer_id],
                              search_space["Weight"][layer_id],
                              search_space["strides"][layer_id],
                              search_space["expansion"][layer_id],
                              self.index[1], layer_id),
                              (search_space["input_shape"][layer_id][0],
                              search_space["channel_size"][layer_id],
                              search_space["Activation"][layer_id],
                              search_space["Weight"][layer_id],
                              search_space["strides"][layer_id],
                              search_space["expansion"][layer_id],
                              self.index[2], layer_id),
                            ) for layer_id in range(self.cnt_layers)]
        # layers_input_shapes are (C_in, input_w, input_h)
        layers_input_shapes = search_space["input_shape"]
        
        return layers_parameters, layers_input_shapes
    
    def _generate_index(self, bit):
        '''
        if self.count==5:
            m = torch.load('/home/khs/data/sup_logs/imagenet/mobilenet_v2.pth.tar')
            count = 0
            index = []
            for i in m.keys():
                if 'weight' in i:
                    if count ==7:
                        break
                    index.append([])
                    w = m[i]
                    w_numpy = w.cpu().numpy()
                    w_numpy = w_numpy.reshape(w_numpy.shape[0], -1)
                    budget = bit[count] * w_numpy.shape[0]
                    max_val = np.max(w_numpy, axis=1)
                    min_val = np.min(w_numpy, axis=1)
                    noise = np.random.normal(0, 0.01, w_numpy.shape[0])
                    inter = (max_val - min_val)**2
                    inter = inter + noise
                    b = np.ones(w_numpy.shape[0])
                    I = inter / (3**b)
                    while np.sum(b) < budget:
                        idx = I.argmax()
                        b[idx] += 1
                        I = inter / (3**b)
                    for i in range(8):
                        index[count].append(list(np.where(b==i+1)[0]))
                    count+=1
        '''
        if True:
            m = torch.load('/home/khs/data/sup_logs/imagenet/best_model.pth')
            index = []
            count = 0
            tmp = []
            for i in m.keys():
                if 'thetas' in i and str(count) in i:
                    tmp.append(np.argmax(m[i].cpu().numpy()))
                    count+=1
            count = 0
            for i in m.keys():
                if count==19:
                    break
                if str(count) + '.ops.' + str(tmp[count]) in i and 'weight' in i:
                    index.append([])
                    w = m[i]
                    w_numpy = w.cpu().numpy()
                    w_numpy = w_numpy.reshape(w_numpy.shape[0], -1)
                    budget = bit[count] * w_numpy.shape[0]
                    max_val = np.max(w_numpy, axis=1)
                    min_val = np.min(w_numpy, axis=1)
                    sigma = 0.01 * ((0.5)**self.count)
                    noise = np.random.normal(0, sigma, w_numpy.shape[0])
                    inter = (max_val - min_val)**2
                    inter = inter + noise
                    b = np.ones(w_numpy.shape[0])
                    I = inter / (3**b)
                    while np.sum(b) < budget:
                        idx = I.argmax()
                        b[idx] += 1
                        I = inter / (3**b)
                    for i in range(8):
                        index[count].append(list(np.where(b==i+1)[0]))
                    count+=1
        return index

    # CNT_OP_RUNS us number of times to check latency (we will take average)
    def _create_from_operations(self, cnt_of_runs, write_to_file=None):
        self.lookup_table_latency = self._calculate_latency(self.lookup_table_operations,
                                                            self.layers_parameters,
                                                            self.layers_input_shapes,
                                                            cnt_of_runs)
        if write_to_file is not None:
            self._write_lookup_table_to_file(write_to_file)
    
    def _calculate_latency(self, operations, layers_parameters, layers_input_shapes, cnt_of_runs):
        LATENCY_BATCH_SIZE = 1
        latency_table_layer_by_ops = [{} for i in range(self.cnt_layers)]
        
        for layer_id in range(self.cnt_layers):
            for op_name in operations:
                op = operations[op_name](*layers_parameters[layer_id])
                input_sample = torch.randn((LATENCY_BATCH_SIZE, *layers_input_shapes[layer_id]))
                globals()['op'], globals()['input_sample'] = op, input_sample
                total_time = timeit.timeit('output = op(input_sample)', setup="gc.enable()", \
                                           globals=globals(), number=cnt_of_runs)
                # measured in micro-second
                latency_table_layer_by_ops[layer_id][op_name] = total_time / cnt_of_runs / LATENCY_BATCH_SIZE * 1e6
                
        return latency_table_layer_by_ops
    
    def _write_lookup_table_to_file(self, path_to_file):
        clear_files_in_the_list([path_to_file])
        ops = [op_name for op_name in self.lookup_table_operations]
        text = [op_name + " " for op_name in ops[:-1]]
        text.append(ops[-1] + "\n")
        
        for layer_id in range(self.cnt_layers):
            for op_name in ops:
                text.append(str(self.lookup_table_latency[layer_id][op_name]))
                text.append(" ")
            text[-1] = "\n"
        text = text[:-1]
        
        text = ''.join(text)
        add_text_to_file(text, path_to_file)
    
    def _create_from_file(self, path_to_file):
        self.lookup_table_latency = self._read_lookup_table_from_file(path_to_file)
    
    def _read_lookup_table_from_file(self, path_to_file):
        latences = [line.strip('\n') for line in open(path_to_file)]
        ops_names = latences[0].split(" ")
        latences = [list(map(float, layer.split(" "))) for layer in latences[1:]]
        latency = []
        for layer in range(self.cnt_layers):
            latency.append([])
            for op in range(3):
                latency[layer].append([])
        for op in range(3):
            for layer in range(self.cnt_layers):
                latency[layer][op] = 0
                for bit in range(8):
                    latency[layer][op] += math.ceil(len(self.index[op][layer][bit])/8)*8 * latences[bit][op]
        lookup_table_latency = [{op_name : latency[i][op_id] 
                                      for op_id, op_name in enumerate(ops_names)
                                     } for i in range(self.cnt_layers)]
        return lookup_table_latency
