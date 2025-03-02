import torch
import torch.nn as nn
from torch_geometric.nn import MessagePassing
from torch_geometric.nn import global_mean_pool
import torch.nn.functional as F
import pdb


class GINConv(MessagePassing):
    def __init__(self, in_dim, emb_dim):
        
        super(GINConv, self).__init__(aggr = "add")
        self.mlp = torch.nn.Sequential(torch.nn.Linear(in_dim, 2*emb_dim),
                                       torch.nn.BatchNorm1d(2*emb_dim), 
                                       torch.nn.ReLU(), 
                                       torch.nn.Linear(2*emb_dim, emb_dim))
        self.eps = torch.nn.Parameter(torch.Tensor([0]))

    def forward(self, x, edge_index, edge_weight=None):
        out = self.mlp((1 + self.eps) *x + self.propagate(edge_index, x=x, edge_weight=edge_weight))
        return out
    def message(self, x_j, edge_weight=None):
        if edge_weight is not None:
            mess = F.relu(x_j * edge_weight)
        else:
            mess = F.relu(x_j)
        return mess

    def update(self, aggr_out):
        return aggr_out




class GNNSynEncoder(torch.nn.Module):
    def __init__(self, num_layer, in_dim, emb_dim, dropout_rate=0.5):
       
        super(GNNSynEncoder, self).__init__()
        self.num_layer = num_layer
        self.in_dim = in_dim
        self.emb_dim = emb_dim
        self.dropout_rate = dropout_rate
        self.relu1 = nn.ReLU()
        self.relus = nn.ModuleList([nn.ReLU() for _ in range(num_layer - 1)])
        self.batch_norm1 = nn.BatchNorm1d(emb_dim)
        self.batch_norms = nn.ModuleList([nn.BatchNorm1d(emb_dim) for _ in range(num_layer - 1)])
        self.dropout1 = nn.Dropout(self.dropout_rate)
        self.dropouts = nn.ModuleList([nn.Dropout(self.dropout_rate) for _ in range(num_layer - 1)])
        self.conv1 = GINConv(in_dim, emb_dim)
        self.convs = nn.ModuleList([GINConv(emb_dim, emb_dim) for _ in range(num_layer - 1)])

    def forward(self, x, edge_index, node_adv=None, edge_adv=None):
        if node_adv is not None:
            x = x * node_adv
        post_conv = self.batch_norm1(self.conv1(x, edge_index, edge_adv))
        if self.num_layer > 1:
            post_conv = self.relu1(post_conv)
            post_conv = self.dropout1(post_conv)
        
        for i, (conv, batch_norm, relu, dropout) in enumerate(zip(self.convs, self.batch_norms, self.relus, self.dropouts)):
            post_conv = batch_norm(conv(post_conv, edge_index, edge_adv))
            if i != len(self.convs) - 1:            # not for final layer
                post_conv = relu(post_conv)
            post_conv = dropout(post_conv)
        return post_conv
