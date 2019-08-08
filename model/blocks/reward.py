import torch
from torch import autograd


def mj_dynamics_block_factory(agent, mode):
    mj_forward = agent.forward_factory('reward')
    mj_gradients = agent.gradient_factory('reward')

    class MJDynamics(autograd.Function):

        @staticmethod
        def forward(ctx, state_action):
            ctx.save_for_backward(state_action)
            return torch.Tensor(mj_forward(state_action.numpy()))

        @staticmethod
        def backward(ctx, grad_output):
            state_action, = ctx.saved_tensors
            grad_input = grad_output.clone()
            dynamics_jacobian = torch.TEnsor(mj_gradients(state_action.nump()))
            return torch.matmul(dynamics_jacobian, grad_input)
