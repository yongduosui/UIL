import torch
from torch_geometric.loader import DataLoader
from ogb.graphproppred import PygGraphPropPredDataset, Evaluator
import torch.optim as optim
import torch.nn.functional as F
import argparse
import time
import numpy as np
from torch.optim.lr_scheduler import StepLR, MultiStepLR, CosineAnnealingLR
import os
# from models import CausalAdvGNNMol
import pdb
import random
from utils import get_info_dataset, size_split_idx, print_args, set_seed, _init_fn, init_weights
# from model import EIGNN_Mol

from gnn2 import GINNet
from model import CausalGraphon
from graphon import stat_graph


def eval(model, evaluator, loader, device):
    model.eval()
    y_true = []
    y_pred = []
    for step, batch in enumerate(loader):
        batch = batch.to(device)
        if batch.x.shape[0] == 1:
            pass
        else:
            with torch.no_grad():
                pred = model(batch)['pred_cau']
            y_true.append(batch.y.view(pred.shape).detach().cpu())
            y_pred.append(pred.detach().cpu())
    y_true = torch.cat(y_true, dim = 0).numpy()
    y_pred = torch.cat(y_pred, dim = 0).numpy()
    input_dict = {"y_true": y_true, "y_pred": y_pred}
    output = evaluator.eval(input_dict)
    return output

def main(args, trail):
    
    device = torch.device("cuda:0")
    dataset = PygGraphPropPredDataset(name=args.dataset, root=args.data_dir)
    num_class = dataset.num_tasks
    eval_metric = "rocauc"
    in_dim = 9
    num_class = 1

    if args.domain == "scaffold":
        split_idx = dataset.get_idx_split()
    else:
        split_idx = size_split_idx(dataset, args.size)

    print("[!] split:{}, size:{}".format(args.domain, args.size))
    get_info_dataset(args, dataset, split_idx)
    evaluator = Evaluator(args.dataset)

    # train_loader     = DataLoader(dataset[split_idx["train"]],  batch_size=args.batch_size, shuffle=True,  num_workers=0, worker_init_fn=_init_fn)
    train_loader = DataLoader(dataset[split_idx["train"]],  batch_size=args.batch_size, shuffle=True,  num_workers=0, worker_init_fn=_init_fn, drop_last=True)
    valid_loader = DataLoader(dataset[split_idx["valid"]],  batch_size=args.batch_size, shuffle=False, num_workers=0, worker_init_fn=_init_fn)
    test_loader  = DataLoader(dataset[split_idx["test"]],   batch_size=args.batch_size, shuffle=False, num_workers=0, worker_init_fn=_init_fn)
    avg_num_nodes, avg_num_edges, avg_density, median_num_nodes, median_num_edges, median_density = stat_graph(dataset[split_idx["train"]])
    # model = EIGNN_Mol(args=args, 
    #                     num_class=num_class, 
    #                     in_dim=in_dim, 
    #                     emb_dim=args.emb_dim, 
    #                     cau_gamma=args.cau_gamma, 
    #                     single_linear=args.single_linear,
    #                     equ_rep=args.equ_rep).to(device)
    model = CausalGraphon(args=args, num_class=num_class, 
                            in_dim=in_dim,
                            emb_dim=args.emb_dim,
                            fro_layer=args.layer,
                            bac_layer=args.layer,
                            cau_layer=args.layer,
                            dropout_rate=args.dropout_rate,
                            cau_gamma=args.cau_gamma,
                            use_linear=args.use_linear,
                            graphon=args.graphon,
                            N=int(median_num_nodes)).to(device)

    init_weights(model, args.initw_name, init_gain=0.02)

    optimizer = optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.l2reg)

    if args.lr_scheduler == 'step':
        scheduler = StepLR(optimizer, step_size=args.lr_decay, gamma=args.lr_gamma)
    elif args.lr_scheduler == 'muti':
        scheduler = MultiStepLR(optimizer, milestones=args.milestones, gamma=args.lr_gamma)
    elif args.lr_scheduler == 'cos':
        scheduler = CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=args.eta_min)
    else:
        pass

    criterion = torch.nn.BCEWithLogitsLoss()
    results = {'highest_valid': 0, 'update_test': 0,  'update_epoch': 0}
    start_time = time.time()
    
    for epoch in range(1, args.epochs+1):
        start_time_local = time.time()
        total_loss = 0
        
        show  = int(float(len(train_loader)) / 2.0)
        correct = 0
        SufLo = 0
        InvLo = 0
        GraLo = 0
        for step, batch in enumerate(train_loader):

            batch = batch.to(device)
            model.train()
            out = model(batch, epoch=epoch)
            pred = out['pred_cau'].max(1)[1]
            correct += pred.eq(batch.y.view(-1)).sum().item()
            optimizer.zero_grad()
            if args.dataset == "motif" or args.dataset == "cmnist":
                one_hot_target = batch.y.view(-1)
                uniform_target = torch.ones_like(out['pred_cau']) / num_class
                cau_loss = criterion(out['pred_cau'], one_hot_target)
                if args.random_add == 'shuffle':
                    inv_loss = criterion(out['pred_add'], one_hot_target)
                else:
                    inv_loss = 0
                # env_loss = F.kl_div(F.log_softmax(out['pred_env'], dim=-1), uniform_target, reduction='batchmean')
                gra_loss = out['graphon_loss']
                reg_loss = out['cau_loss_reg']
                loss = args.cau * cau_loss + args.gra * gra_loss + args.reg * reg_loss + args.inv * inv_loss
            else:
                is_labeled = batch.y == batch.y
                uniform_target = torch.ones_like(out['pred_cau']) / num_class
                cau_loss = criterion(out['pred_cau'].to(torch.float32)[is_labeled], batch.y.to(torch.float32)[is_labeled])
                if args.random_add == 'shuffle':
                    inv_loss = criterion(out['pred_add'].to(torch.float32)[is_labeled], batch.y.to(torch.float32)[is_labeled])
                else:
                    inv_loss = 0
                # env_loss = F.kl_div(F.log_softmax(out['pred_env'], dim=-1), uniform_target, reduction='batchmean')
                gra_loss = out['graphon_loss']
                reg_loss = out['cau_loss_reg']
                loss = args.cau * cau_loss + args.gra * gra_loss + args.reg * reg_loss + args.inv * inv_loss
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            SufLo += cau_loss + reg_loss
            InvLo += inv_loss
            GraLo += gra_loss
            if step % show == 0:
                print("Ep:[{}/{}] TrIter:[{:<3}/{}] Lo:[{:.4f}]".format(epoch, args.epochs, step, len(train_loader), total_loss / (step + 1)))
        
        train_result = correct / len(train_loader.dataset)
        epoch_loss = total_loss / len(train_loader)
        SufLo = SufLo / len(train_loader)
        InvLo = InvLo / len(train_loader)
        GraLo = GraLo / len(train_loader)

        # if args.dataset == "motif" or args.dataset == "cmnist":
        #     valid_result = eval1(model, valid_loader, device)
        #     test_result = eval1(model, test_loader, device)
        # else:
        #     evaluator = Evaluator(args.dataset)
        #     valid_result = eval2(model, evaluator, valid_loader, device)[eval_metric]
        #     test_result  = eval2(model, evaluator, test_loader,  device)[eval_metric] 
        train_result = eval(model, evaluator, train_loader, device)[eval_metric]
        valid_result = eval(model, evaluator, valid_loader, device)[eval_metric]
        test_result  = eval(model, evaluator, test_loader,  device)[eval_metric] 
        if args.save_model and epoch%10==0 and trail<=3:
            torch.save(model.state_dict(), "./model_{}/{}-{}-tr{}-ep{}.pt".format(args.time, args.dataset, args.domain, trail, epoch))
        if epoch > args.graphon_pretrain and valid_result > results['highest_valid']:
            results['highest_valid'] = valid_result
            results['update_test'] = test_result
            results['update_epoch'] = epoch
            if args.save_model and trail<=3:
                torch.save(model.state_dict(), "./model_{}/{}-{}-tr{}-ep{}.pt".format(args.time, args.dataset, args.domain, trail, epoch))

        print("-" * 150)
        print("Tr:[{}/{}], Ep:[{}/{}] | Lo:[{:.4f}], SufLo:[{:.4f}], InvLo:[{:.4f}], GraLo:[{:.4f}] | tr:[{:.2f}], va:[{:.2f}], te:[{:.2f}] | Best va:[{:.2f}], te:[{:.2f}] at:[{}] | ep time:{:.2f} min"
                        .format(trail, args.trails, epoch, args.epochs, 
                                epoch_loss, SufLo, InvLo, GraLo,
                                train_result*100, valid_result*100, test_result*100,
                                results['highest_valid']*100, results['update_test']*100, results['update_epoch'],
                                (time.time()-start_time_local) / 60))
        print("-" * 150)
    total_time = time.time() - start_time
    print("Best va:[{:.2f}], te:[{:.2f}] at epoch:[{}] | Total time:{}"
            .format(results['highest_valid']*100, results['update_test']*100, results['update_epoch'],
                    time.strftime('%H:%M:%S', time.gmtime(total_time))))
    return results['update_test']


def config_and_run(args):
    
    print_args(args)
    set_seed(args.seed)
    final_test_acc_cau = []
    for trail in range(1, args.trails+1):
        args.seed += 10
        set_seed(args.seed)
        test_auc_cau = main(args, trail)
        final_test_acc_cau.append(test_auc_cau)
    print("wsy: finall: Test ACC CAU: [{:.2f}±{:.2f}]".format(np.mean(final_test_acc_cau)* 100, np.std(final_test_acc_cau)* 100))

if __name__ == "__main__":

    def arg_parse():
        str2bool = lambda x: x.lower() == "true"
        parser = argparse.ArgumentParser(description='GNN baselines on ogbgmol* data with Pytorch Geometrics')
        
        parser.add_argument('--seed', type=int,   default=666)
        parser.add_argument('--device', type=int, default=0, help='which gpu to use if any (default: 0)')
        parser.add_argument('--data_dir', type=str, default="dataset", help="dataset path")
        parser.add_argument('--dataset', type=str, default="hiv")
        parser.add_argument('--domain', type=str, default='size', help='basis, size, scaffold')
        parser.add_argument('--shift', type=str, default='concept', help='concept or covariate')
        parser.add_argument('--save_model', type=str2bool, default='False')
        parser.add_argument('--time', type=str, default='2301121840', help='current time')
        parser.add_argument('--initw_name', type=str, default='orthogonal',
                        choices=['default','orthogonal','normal','xavier','kaiming'],
                        help='method name to initialize neural weights')

        parser.add_argument('--emb_dim', type=int, default=300)
        parser.add_argument('--batch_size', type=int, default=32)
        parser.add_argument('--lr', type=float, default=0.001)
        parser.add_argument('--trails', type=int, default=10, help='number of runs (default: 0)')
        parser.add_argument('--epochs', type=int, default=100)
        parser.add_argument('--layer', type=int, default= -1)
        parser.add_argument('--use_linear',type=str2bool, default=False)
        parser.add_argument('--size', type=str, default='ls', help='GNN gin, gin-virtual, or gcn, or gcn-virtual (default: gin-virtual)')

        parser.add_argument('--virtual',type=str2bool, default=False)
        parser.add_argument('--lr_scheduler', type=str, default="cos")
        parser.add_argument('--l2reg', type=float, default=5e-6)
        parser.add_argument('--lr_decay', type=int, default=150)
        parser.add_argument('--lr_gamma', type=float, default=0.1)
        parser.add_argument('--milestones', nargs='+', type=int, default=[40,60,80])
        parser.add_argument('--dropout_rate', type=float, default=0.5)
        parser.add_argument('--cau_gamma', type=float, default=0.6)
        parser.add_argument('--random_add', type=str, default='shuffle')
        parser.add_argument('--with_random', type=str2bool, default=True)
        
        parser.add_argument('--graphon', type=str2bool, default=False, help='with gra loss')
        parser.add_argument('--graphon_pretrain', type=int, default=80)
        parser.add_argument('--graphon_frequency', type=int, default=10)
        parser.add_argument('--num_env', type=int, default=3, help='env number')
        
        parser.add_argument('--cau', type=float, default=1.0, help='cau loss coefficient')
        parser.add_argument('--env', type=float, default=0, help='env loss coefficient')
        parser.add_argument('--inv', type=float, default=0.1, help='invariance loss coefficient of add env to cau')
        parser.add_argument('--gra', type=float, default=1e-3, help='gra loss coefficient')
        parser.add_argument('--reg', type=float, default=1, help='regularization coefficient')
        parser.add_argument('--eta_min', type=float, default=1e-4)
        args = parser.parse_args()
        return args


    args = arg_parse()
    config_and_run(args)
