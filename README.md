# A Unified Invariant Learning Framework for Graph Classification
PyTorch implementation for "A Unified Invariant Learning Framework for Graph Classification"

Yongduo Sui, Jie Sun, Shuyao Wang, Zemin Liu, Qing Cui, Longfei Li, Xiang Wang

In KDD 2025

## Installations
Main packages: PyTorch, Pytorch Geometric, OGB.
```
pytorch==1.10.1
torch-cluster==1.5.9
torch-geometric==2.0.3
torch-scatter==2.0.9
torch-sparse==0.6.12
torch-spline-conv==1.2.1
ogb==1.3.5
typed-argument-parser==1.7.2
gdown==4.6.0
tensorboard==2.10.1
ruamel-yaml==0.17.21
cilog==1.2.3
munch==2.5.0
rdkit==2020.09.1.0
```

## Preparations
Please download the graph OOD datasets (https://github.com/divelab/GOOD) and OGB datasets as described in the original paper. 
Create a folder ```dataset```, and then put the datasets into ```dataset```. Then modify the path by specifying ```--data_dir your/path/dataset```.


## Commands
 We use the NVIDIA GeForce RTX 3090 (24GB GPU) to conduct all our experiments.
 To run the code on CMNIST, please use the following command:
 ```
CUDA_VISIBLE_DEVICES=$GPU python -u main.py --dataset cmnist

```

