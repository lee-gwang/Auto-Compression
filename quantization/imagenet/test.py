import numpy as np
import torch
from torch import nn
from tensorboardX import SummaryWriter
from scipy.special import softmax
import argparse
import time
from general_functions.dataloaders import get_loaders, get_test_loader
from general_functions.utils import get_logger, weights_init, load, create_directories_from_list, \
                                    check_tensor_in_list, writh_new_ARCH_to_fbnet_modeldef
from supernet_functions.lookup_table_builder import LookUpTable, LookUpTable_HIGH
from supernet_functions.model_supernet import FBNet_Stochastic_SuperNet, SupernetLoss
from supernet_functions.training_functions_supernet import TrainerSupernet
from supernet_functions.config_for_supernet import CONFIG_SUPERNET
from fbnet_building_blocks.fbnet_modeldef import MODEL_ARCH
import copy
from mobile import mobilenet_v2

parser = argparse.ArgumentParser("action")
parser.add_argument('--train_or_sample', type=str, default='', \
                    help='train means training of the SuperNet, sample means sample from SuperNet\'s results')
parser.add_argument('--architecture_name', type=str, default='', \
                    help='Name of an architecture to be sampled')
parser.add_argument('--hardsampling_bool_value', type=str, default='True', \
                    help='If not False or 0 -> do hardsampling, else - softmax sampling')
parser.add_argument('--high_or_low', type=str, default='high')
args = parser.parse_args()

def train_supernet():
    test_input = torch.rand(1, 3, 224, 224).cuda()
    manual_seed = 1
    np.random.seed(manual_seed)
    torch.manual_seed(manual_seed)
    torch.cuda.manual_seed_all(manual_seed)
    torch.backends.cudnn.benchmark = True

    create_directories_from_list([CONFIG_SUPERNET['logging']['path_to_tensorboard_logs']])
    
    logger = get_logger(CONFIG_SUPERNET['logging']['path_to_log_file'])
    writer = SummaryWriter(log_dir=CONFIG_SUPERNET['logging']['path_to_tensorboard_logs'])
    #### DataLoading
    train_w_loader, train_thetas_loader = get_loaders(CONFIG_SUPERNET['dataloading']['w_share_in_train'],
                                                      CONFIG_SUPERNET['dataloading']['batch_size'],
                                                      CONFIG_SUPERNET['dataloading']['path_to_save_data'],
                                                      logger)
    test_loader = get_test_loader(CONFIG_SUPERNET['dataloading']['batch_size'],
                                  CONFIG_SUPERNET['dataloading']['path_to_save_data'])
    ###TRAIN HIGH_LEVEL
    lookup_table = LookUpTable_HIGH(calulate_latency=CONFIG_SUPERNET['lookup_table']['create_from_scratch'])
    ###MODEL
    model = FBNet_Stochastic_SuperNet(lookup_table, cnt_classes=1000)
    model = model.apply(weights_init)
    model = nn.DataParallel(model).cuda()
    model.load_state_dict(torch.load('/home/khs/data/sup_logs/imagenet/pretrained_high.pth'))
    '''
    #### Loss, Optimizer and Scheduler
    criterion = SupernetLoss().cuda()

    for layer in model.module.stages_to_search:
        layer.thetas = nn.Parameter(torch.Tensor([1.0 / 6 for i in range(6)]).cuda())

    thetas_params = [param for name, param in model.named_parameters() if 'thetas' in name]
    params_except_thetas = [param for param in model.parameters() if not check_tensor_in_list(param, thetas_params)]

    w_optimizer = torch.optim.SGD(params=params_except_thetas,
                                  lr=CONFIG_SUPERNET['optimizer']['w_lr'], 
                                  momentum=CONFIG_SUPERNET['optimizer']['w_momentum'],
                                  weight_decay=CONFIG_SUPERNET['optimizer']['w_weight_decay'])
    
    theta_optimizer = torch.optim.Adam(params=thetas_params,
                                       lr=CONFIG_SUPERNET['optimizer']['thetas_lr'],
                                       weight_decay=CONFIG_SUPERNET['optimizer']['thetas_weight_decay'])

    last_epoch = -1
    w_scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(w_optimizer,
                                                             T_max=CONFIG_SUPERNET['train_settings']['cnt_epochs'],
                                                             last_epoch=last_epoch)
    #### Training Loop
    trainer = TrainerSupernet(criterion, w_optimizer, theta_optimizer, w_scheduler, logger, writer, True)
    trainer.train_loop(train_w_loader, train_thetas_loader, test_loader, model)
    '''
    model = model.eval()
    model2 = mobilenet_v2().cuda()
    model2 = model2.eval()
    out = model(test_input, 5.0)
    out2 = model2(test_input)
    print(out[0].detach().cpu().numpy().shape)
    print(out2.detach().cpu().numpy().shape)
    '''
    out = out[0].detach().cpu().numpy()
    out2 = out2.detach().cpu().numpy()
    if not (out == out2).all():
        print(out-out2)
    '''
    '''
    model.eval()
    criterion = nn.CrossEntropyLoss()
    batch_time = AverageMeter('Time', ':6.3f')
    losses = AverageMeter('Loss', ':.4e')
    top1 = AverageMeter('Acc@1', ':6.2f')
    top5 = AverageMeter('Acc@5', ':6.2f')
    progress = ProgressMeter(
            len(test_loader),
            [batch_time, losses, top1, top5],
            prefix='Test: ')
    with torch.no_grad():
        end = time.time()
        for step, (X, y) in enumerate(test_loader):
            X, y = X.cuda(), y.cuda()
            outs = model(X)
            loss = criterion(outs, y)
            acc1, acc5 = accuracy(outs, y, topk=(1,5))
            losses.update(loss.item(), X.size(0))
            top1.update(acc1[0], X.size(0))
            top5.update(acc5[0], X.size(0))

            batch_time.update(time.time() - end)
            end = time.time()

            if step % 10 == 0:
                progress.display(step)
            print(' * Acc@1 {top1.avg:.3f} Acc@5 {top5.avg:.3f}'.format(top1=top1, top5=top5))
    '''

class ProgressMeter(object):
    def __init__(self, num_batches, meters, prefix=""):
        self.batch_fmtstr = self._get_batch_fmtstr(num_batches)
        self.meters = meters
        self.prefix = prefix

    def display(self, batch):
        entries = [self.prefix + self.batch_fmtstr.format(batch)]
        entries += [str(meter) for meter in self.meters]
        print('\t'.join(entries))

    def _get_batch_fmtstr(self, num_batches):
        num_digits = len(str(num_batches // 1))
        fmt = '{:' + str(num_digits) + 'd}'
        return '[' + fmt + '/' + fmt.format(num_batches) + ']'

class AverageMeter(object):
    """Computes and stores the average and current value"""
    def __init__(self, name, fmt=':f'):
        self.name = name
        self.fmt = fmt
        self.reset()

    def reset(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def update(self, val, n=1):
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count

    def __str__(self):
        fmtstr = '{name} {val' + self.fmt + '} ({avg' + self.fmt + '})'
        return fmtstr.format(**self.__dict__)

def accuracy(output, target, topk=(1,)):
    """Computes the accuracy over the k top predictions for the specified values of k"""
    with torch.no_grad():
        maxk = max(topk)
        batch_size = target.size(0)

        _, pred = output.topk(maxk, 1, True, True)
        pred = pred.t()
        correct = pred.eq(target.view(1, -1).expand_as(pred))

        res = []
        for k in topk:
            correct_k = correct[:k].view(-1).float().sum(0, keepdim=True)
            res.append(correct_k.mul_(100.0 / batch_size))
        return res

if __name__ == '__main__':
    train_supernet()
