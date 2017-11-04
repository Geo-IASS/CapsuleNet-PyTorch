import torch
import torch.nn as nn
import torch.nn.functional as F 

from torch.autograd import Variable
class CapsuleConv(nn.Module):
    """
    Args:
        num_routing_iter: number of iterations for the routing algorithm (default: 3)

        num_routing_nodes:
                           when num_routings = -1, it means it's the first capsule layer

    """
    def __init__(self, dim_vector, in_channels, out_channels,
                    kernel_size, stride=1, padding=0, num_routing_nodes=0,  num_routing_iter=0):
        super(CapsuleConv, self).__init__()

        self.dim_vector = dim_vector # For PrimaryCapsule dim_vector = 8
        self.num_routing_nodes = num_routing_nodes
        self.num_routing_iter = num_routing_iter
       
        
        self.capsules_list = nn.ModuleList([nn.Conv2d(in_channels, out_channels, 
                                kernel_size=kernel_size, stride=stride, padding=padding) 
                                for item in range(dim_vector)])
       
        self.rout_weights = nn.Parameter(torch.randn(dim_vector, num_routing_nodes, in_channels, out_channels))

    def squash(self, tensor):
        """Batch Squashing Function
        
        Args:
            tensor : 5-D, (batch_size, dim_vector, num_channel, width, height)
            
        Return:
            tesnor_squached : 5-D, (batch_size, dim_vector, num_channel, width, height)
        """
        tensor_l2norm = (tensor**2).sum(1,keepdim=True) # batch_size x 1 x channel x w x h
        scale_factor = tensor_l2norm / (1 + tensor_l2norm) # size: batch_size
        tensor_squashed = torch.mul((scale_factor/ tensor_l2norm**0.5), tensor)
        return tensor_squashed


    def forward(self, X):
        outputs = [capsule(X).unsqueeze(1) for capsule in self.capsules_list]
        outputs = torch.cat(outputs, dim=1) # batch_size x dim_vector x channel x w x h
        outputs = self.squash(outputs)

        return outputs

class CapsuleLinear(nn.Module):
    """
    Args:
        dim_vector: 

        dim_input_vector: dim_vector of last capsule layer

        num_routing_iter: number of iterations for the routing algorithm (default: 3)

        num_routing_nodes:
                           when num_routings = -1, it means it's the first capsule layer

    """
    def __init__(self, dim_vector, dim_input_vector, out_channels, num_routing_iter=1):
        super(CapsuleLinear, self).__init__()

        self.dim_vector = dim_vector # For DigitCapusle dim_vector = 16
        self.dim_input_vector = dim_input_vector # last layer unit dim, PrimaryCapsule=8
        self.out_channels = out_channels
        self.num_routing_iter = num_routing_iter

    def squash(self, tensor):
        """Batch Squashing Function
        
        Args:
            tensor : 5-D, (batch_size, dim_vector, num_channel, width, height)
            
        Return:
            tesnor_squached : 5-D, (batch_size, dim_vector, num_channel, width, height)
        """
        tensor_l2norm = (tensor**2).sum(1,keepdim=True) # batch_size x 1 x channel x w x h
        scale_factor = tensor_l2norm / (1 + tensor_l2norm) # size: batch_size
        tensor_squashed = torch.mul((scale_factor/ tensor_l2norm**0.5), tensor)
        return tensor_squashed

    def forward(self, X):
        #(batch_size, dim_vector, num_channel, w,h)-->(batch_size,num_capsule,1,1,dim_vector)
        X = X.view(X.size()[0],-1, 1, 1, X.size()[1])
        # num_capsule, for CapsuelNet, 1152=32*6*6
        self.num_capsules_prev = X.size()[1]
        self.batch_size = X.size()[0]
        # repeat (batch_size,num_capsule,out_channels,1,dim_vector) 
        # ---> (batch_size,1152,10,1,8)
        X_tile = X.expand(self.batch_size, self.num_capsules_prev,
                    self.out_channels, 1, self.dim_input_vector)

        self.routing_weight = nn.Parameter(torch.randn(1, self.num_capsules_prev,
                                self.out_channels,self.dim_input_vector,self.dim_vector))

        self.routing_weight = self.routing_weight.expand(self.batch_size, 
                                self.num_capsules_prev,self.out_channels,
                                self.dim_input_vector,self.dim_vector)
        # (batch_size,1152,10,1,16)
        linear_combination = torch.matmul(X_tile, self.routing_weight) # X_hat = X * W
        # (1,1152,10,1,1)
        priors = Variable(torch.zeros(1, self.num_capsules_prev, self.out_channels,1, 1))
        ############################################################################
        ##                                Rounting                                ##
        ############################################################################
        for iter_index in range(self.num_routing_iter):
            # NOTE: RoutingAlgorithm-line 4
            softmax_prior = softmax(priors,dim=2)
            s_size = softmax_prior.size()
            # tile on first dimension for the batch_size
            # (64, 1152, 10, 1,1)
            softmax_prior = softmax_prior.expand(self.batch_size, s_size[1],
                                                s_size[2],s_size[3],s_size[4])
            # NOTE: RoutingAlgorithm-line 5
            # (64, 1152, 10, 1,16)
            output = torch.mul(softmax_prior, linear_combination)
            # (64, 1, 10, 1, 16)
            output_sum = output.sum(dim=1, keepdim=True) # s_J

            # NOTE: RoutingAlgorithm-line 6
            output_squashed = self.squash(output_sum) # v_J

            # NOTE: RoutingAlgorithm-line 7
            # (64, 1152, 10, 1, 16)
            output_tiled = output_squashed.expand_as(output) 
            # (64, 1152, 10, 1, 16) x (64, 1152, 10, 16, 1)
            # ==> (64, 1152, 10, 1, 1)
            U_times_v = torch.matmul(linear_combination, output_tiled.transpose(-2,-1))
            priors += U_times_v.sum(dim=0,keepdim=True)
    
        
        return output_squashed # v_J

def softmax(input, dim=1):
    # This softmax allow you to specify do softmax on which dimension, 
    # similar to tf.nn.softmax
    input_size = input.size()
    
    trans_input = input.transpose(dim, len(input_size)-1)
    trans_size = trans_input.size()

    input_2d = trans_input.contiguous().view(-1, trans_size[-1])
    
    soft_max_2d = F.softmax(input_2d)
    
    soft_max_nd = soft_max_2d.view(*trans_size)
    return soft_max_nd.transpose(axis, len(input_size)-1