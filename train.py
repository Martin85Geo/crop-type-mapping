import torch
from models.DualOutputRNN import DualOutputRNN
from models.AttentionRNN import AttentionRNN
from models.conv_shapelets import ConvShapeletModel
from utils.UCR_Dataset import UCRDataset
from utils.Synthetic_Dataset import SyntheticDataset
import argparse
import numpy as np
import os
from utils.trainer import Trainer

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-d','--dataset', type=str, default="Trace", help='UCR Dataset. Will also name the experiment')
    parser.add_argument(
        '-b', '--batchsize', type=int, default=32, help='Batch Size')
    parser.add_argument(
        '-m', '--model', type=str, default="DualOutputRNN", help='Model variant')
    parser.add_argument(
        '-e', '--epochs', type=int, default=100, help='number of epochs')
    parser.add_argument(
        '-w', '--workers', type=int, default=4, help='number of CPU workers to load the next batch')
    parser.add_argument(
        '-l', '--learning_rate', type=float, default=1e-2, help='learning rate')
    parser.add_argument(
        '--dropout', type=float, default=.2, help='dropout probability of the rnn layer')
    parser.add_argument(
        '-n', '--num_layers', type=int, default=1, help='number of stacked layers. will be interpreted as stacked '
                                                        'RNN layers for recurrent models and as number of convolutions'
                                                        'for convolutional models...')
    parser.add_argument(
        '-r', '--hidden_dims', type=int, default=32, help='number of hidden dimensions per layer stacked hidden dimensions')
    parser.add_argument(
        '--augment_data_noise', type=float, default=0., help='augmentation data noise factor. defaults to 0.')
    parser.add_argument(
        '-a','--earliness_factor', type=float, default=1, help='earliness factor')
    parser.add_argument(
        '-x', '--experiment', type=str, default="test", help='experiment prefix')
    parser.add_argument(
        '--store', type=str, default="/tmp", help='store run logger results')
    parser.add_argument(
        '--run', type=str, default=None, help='run name')
    parser.add_argument(
        '-i', '--show-n-samples', type=int, default=2, help='show n samples in visdom')
    parser.add_argument(
        '--loss_mode', type=str, default="twophase_early_simple", help='which loss function to choose. '
                                                                       'valid options are early_reward,  '
                                                                       'twophase_early_reward, '
                                                                       'twophase_linear_loss, or twophase_early_simple')
    parser.add_argument(
        '-s', '--switch_epoch', type=int, default=None, help='epoch at which to switch the loss function '
                                                             'from classification training to early training')

    parser.add_argument(
        '--smoke-test', action='store_true', help='Finish quickly for testing')
    args, _ = parser.parse_known_args()
    return args

def build_n_shapelet_dict(num_layers, hidden_dims):
    """
    Builds a dictionary of format {<kernel_length_in_percentage_of_T>:<num_hidden_dimensions> , ...}
    returns n shapelets per size
    e.g., {10: 100, 20: 100, 30: 100, 40: 100}
    """
    n_shapelets_per_size = dict()
    for layer in range(num_layers):
        shapelet_width = (layer + 1) * 10  # in 10% increments of sequencelength percantage: 10% 20% 30% etc.
        n_shapelets_per_size[shapelet_width] = hidden_dims
    return n_shapelets_per_size

if __name__=="__main__":

    args = parse_args()

    if args.dataset == "synthetic":
        traindataset = SyntheticDataset(num_samples=2000, T=100)
        validdataset = SyntheticDataset(num_samples=1000, T=100)
    else:
        traindataset = UCRDataset(args.dataset, partition="train", ratio=.75, randomstate=0,
                                  augment_data_noise=args.augment_data_noise)
        validdataset = UCRDataset(args.dataset, partition="valid", ratio=.75, randomstate=0)

    nclasses = traindataset.nclasses

    np.random.seed(0)
    torch.random.manual_seed(0)
    traindataloader = torch.utils.data.DataLoader(traindataset, batch_size=args.batchsize, shuffle=True,
                                                  num_workers=args.workers, pin_memory=True)

    np.random.seed(1)
    torch.random.manual_seed(1)
    validdataloader = torch.utils.data.DataLoader(validdataset, batch_size=args.batchsize, shuffle=False,
                                                  num_workers=args.workers, pin_memory=True)
    if args.model == "DualOutputRNN":
        model = DualOutputRNN(input_dim=1, nclasses=nclasses, hidden_dim=args.hidden_dims,
                              num_rnn_layers=args.num_layers, dropout=args.dropout)
    elif args.model == "AttentionRNN":
        model = AttentionRNN(input_dim=1, nclasses=nclasses, hidden_dim=args.hidden_dims, num_rnn_layers=args.num_layers,
                             dropout=args.dropout)
    elif args.model == "Conv1D":
        n_shapelets_per_size = build_n_shapelet_dict(args.num_layers, args.hidden_dims)
        model = ConvShapeletModel(n_shapelets_per_size=n_shapelets_per_size,
                          ts_dim=1,
                          n_classes=nclasses)
    else:
        raise ValueError("Invalid Model, Please insert either 'DualOutputRNN' or 'AttentionRNN'")

    if torch.cuda.is_available():
        model = model.cuda()

    if args.run is None:
        visdomenv = "{}_{}_{}".format(args.experiment, args.dataset,args.loss_mode.replace("_","-"))
        storepath = args.store
    else:
        visdomenv = args.run
        storepath = os.path.join(args.store, args.run)

    if args.switch_epoch is None:
        args.switch_epoch = int(args.epochs/2)

    config = dict(
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        earliness_factor=args.earliness_factor,
        visdomenv=visdomenv,
        switch_epoch=args.switch_epoch,
        loss_mode=args.loss_mode,
        show_n_samples=args.show_n_samples,
        store=storepath
    )

    trainer = Trainer(model,traindataloader,validdataloader,config=config)
    trainer.fit()
