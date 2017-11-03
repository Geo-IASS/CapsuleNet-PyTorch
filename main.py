from __future__ import print_function
import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F  
import torch.optim as optim

from torchvision import datasets, transforms
from torch.autograd import Variable 
from CapsuleNet import CapsuleNet, CapsuleLoss

def parse_args():
    parser = argparse.ArgumentParser(description='CapsuelNet Pytorch MINIST Example')
    parser.add_argument('--batch-size', type=int, default=64, metavar='N',
                    help='input batch size for training (default: 64)')
    parser.add_argument('--test-batch-size', type=int, default=1000, metavar='N',
                    help='input batch size for testing (default: 1000)')
    parser.add_argument('--epochs', type=int, default=10, metavar='N',
                    help='number of epochs to train (default: 10)')
    parser.add_argument('--lr', type=float, default=0.01, metavar='LR',
                    help='learning rate (default: 0.01)')
    parser.add_argument('--momentum', type=float, default=0.5, metavar='M',
                    help='SGD momentum (default: 0.5)')
    parser.add_argument('--no-cuda', action='store_true', default=False,
                    help='disables CUDA training')
    parser.add_argument('--seed', type=int, default=1, metavar='S',
                    help='random seed (default: 1)')
    parser.add_argument('--log-interval', type=int, default=10, metavar='N',
                    help='how many batches to wait before logging training status')
    args = parser.parse_args()
    args.cuda = not args.no_cuda and torch.cuda.is_available()

    return args
def train(args, model, optimizer, epoch_index, train_loader, capsule_loss):
    model.train()

    for batch_idx, (X, y) in enumerate(train_loader):
        if args.cuda:
            X, y = X.cuda(), y.cuda()
        X, y = Variable(X), Variable(y)
        optimizer.zero_grad()
        prob, reconstructions = model(X, y)
        loss = capsule_loss(X, y, prob, reconstructions)
        loss.backward()
        optimizer.step()
        if batch_idx % args.log_interval == 0:
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                epoch_index, batch_idx * len(X), len(train_loader.dataset),
                100. * batch_idx / len(train_loader), loss.data[0]))
        
def test(args, model, test_loader,capsule_loss):
    model.eval()
    test_loss = 0
    num_correct = 0
    for X, y in test_loader:
        if args.cuda:
            X, y = X.cuda(), y.cuda()
        X, y = Variable(X, volatile=True), Variable(y)
        prob, reconstructions = model(X, y)
        loss = capsule_loss(X, y, prob, reconstructions)
        test_loss += loss

        pred_y = prob.data.max(1, keepdim=True)[1]
        num_correct += pred_y.eq(y.data.view_as(pred_y)).cpu().sum()

    test_loss /= len(test_loader.dataset)
    print('\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(test_loss, num_correct, len(test_loader.dataset),
    100. * num_correct / len(test_loader.dataset)))

def main():
    args = parse_args()
    if args.cuda:
        torch.cuda.manual_seed(args.seed)
    
    kwargs = {'num_workers': 1, 'pin_memory': True} if args.cuda else {}
    ##############################################################
    ##                  Load Data from torchvision              ##
    ##############################################################
    train_loader = torch.utils.data.DataLoader(
        datasets.MNIST('../data', train=True, download=True,
                        transform=transforms.Compose([
                            transforms.ToTensor(),
                            transforms.Normalize((0.1307,),(0.3081,))
                        ])),
                        batch_size=args.batch_size,
                        shuffle=True, **kwargs)
    test_loader = torch.utils.data.DataLoader(
        datasets.MNIST('../data', train=False, 
                        transform=transforms.Compose([
                            transforms.ToTensor(),
                            transforms.Normalize((0.1307,),(0.3081,))
                        ])),
                        batch_size=args.test_batch_size,
                        shuffle=True, **kwargs)

    ##############################################################
    ##                  Load model and set optimizer            ##
    ##############################################################
    capsule_model = CapsuleNet()
    if args.cuda:
        capsule_model.cuda()
    
    optimizer = optim.Adam(capsule_model.parameters())
    capsule_loss = CapsuleLoss()
    for epoch_index in range(1, args.epochs + 1):
        train(args, capsule_model, optimizer, epoch_index, train_loader, capsule_loss)
        test(args, capsule_model, test_loader, capsule_loss)
    
if __name__ == '__main__':
    main()