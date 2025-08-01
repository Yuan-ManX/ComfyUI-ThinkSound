import torch
import os
from torch import nn, Tensor, einsum, IntTensor, FloatTensor, BoolTensor
import random 



def get_rank():
    """Get rank of current process."""
    
    print(os.environ.keys())

    if "SLURM_PROCID" in os.environ:
        return int(os.environ["SLURM_PROCID"])

    if not torch.distributed.is_available() or not torch.distributed.is_initialized():
        return 0
    
    return torch.distributed.get_rank()

class InverseLR(torch.optim.lr_scheduler._LRScheduler):
    """Implements an inverse decay learning rate schedule with an optional exponential
    warmup. When last_epoch=-1, sets initial lr as lr.
    inv_gamma is the number of steps/epochs required for the learning rate to decay to
    (1 / 2)**power of its original value.
    Args:
        optimizer (Optimizer): Wrapped optimizer.
        inv_gamma (float): Inverse multiplicative factor of learning rate decay. Default: 1.
        power (float): Exponential factor of learning rate decay. Default: 1.
        warmup (float): Exponential warmup factor (0 <= warmup < 1, 0 to disable)
            Default: 0.
        final_lr (float): The final learning rate. Default: 0.
        last_epoch (int): The index of last epoch. Default: -1.
        verbose (bool): If ``True``, prints a message to stdout for
            each update. Default: ``False``.
    """

    def __init__(self, optimizer, inv_gamma=1., power=1., warmup=0., final_lr=0.,
                 last_epoch=-1, verbose=False):
        self.inv_gamma = inv_gamma
        self.power = power
        if not 0. <= warmup < 1:
            raise ValueError('Invalid value for warmup')
        self.warmup = warmup
        self.final_lr = final_lr
        super().__init__(optimizer, last_epoch, verbose)

    def get_lr(self):
        if not self._get_lr_called_within_step:
            import warnings
            warnings.warn("To get the last learning rate computed by the scheduler, "
                          "please use `get_last_lr()`.")

        return self._get_closed_form_lr()

    def _get_closed_form_lr(self):
        warmup = 1 - self.warmup ** (self.last_epoch + 1)
        lr_mult = (1 + self.last_epoch / self.inv_gamma) ** -self.power
        return [warmup * max(self.final_lr, base_lr * lr_mult)
                for base_lr in self.base_lrs]

def copy_state_dict(model, state_dict):
    """Load state_dict to model, but only for keys that match exactly.

    Args:
        model (nn.Module): model to load state_dict.
        state_dict (OrderedDict): state_dict to load.
    """
    model_state_dict = model.state_dict()

    # 创建一个列表存储不匹配的参数
    missing_keys = []
    unexpected_keys = []
    # 手动加载并检查不匹配的参数
    for key in state_dict:
        if key not in model_state_dict:
            unexpected_keys.append(key)
        elif state_dict[key].shape != model_state_dict[key].shape:
            unexpected_keys.append(key)

    for key in model_state_dict:
        if key not in state_dict:
            missing_keys.append(key)

    # 打印不匹配的参数
    print("Missing keys in state_dict:", missing_keys)
    print("Unexpected keys in state_dict:", unexpected_keys)
    for key in state_dict:
        if key in model_state_dict and state_dict[key].shape == model_state_dict[key].shape:
            if isinstance(state_dict[key], torch.nn.Parameter):
                # backwards compatibility for serialized parameters
                state_dict[key] = state_dict[key].data
            model_state_dict[key] = state_dict[key]
        
    model.load_state_dict(model_state_dict, strict=False)

def create_optimizer_from_config(optimizer_config, parameters):
    """Create optimizer from config.

    Args:
        parameters (iterable): parameters to optimize.
        optimizer_config (dict): optimizer config.

    Returns:
        torch.optim.Optimizer: optimizer.
    """

    optimizer_type = optimizer_config["type"]

    if optimizer_type == "FusedAdam":
        from deepspeed.ops.adam import FusedAdam
        optimizer = FusedAdam(parameters, **optimizer_config["config"])
    else:
        optimizer_fn = getattr(torch.optim, optimizer_type)
        optimizer = optimizer_fn(parameters, **optimizer_config["config"])
    return optimizer

def create_scheduler_from_config(scheduler_config, optimizer):
    """Create scheduler from config.

    Args:
        scheduler_config (dict): scheduler config.
        optimizer (torch.optim.Optimizer): optimizer.

    Returns:
        torch.optim.lr_scheduler._LRScheduler: scheduler.
    """
    if scheduler_config["type"] == "InverseLR":
        scheduler_fn = InverseLR
    else:
        scheduler_fn = getattr(torch.optim.lr_scheduler, scheduler_config["type"])
    scheduler = scheduler_fn(optimizer, **scheduler_config["config"])
    return scheduler

# mask construction helpers

def mask_from_start_end_indices(
    seq_len: int,
    start: Tensor,
    end: Tensor
):
    assert start.shape == end.shape
    device = start.device

    seq = torch.arange(seq_len, device = device, dtype = torch.long)
    seq = seq.reshape(*((-1,) * start.ndim), seq_len)
    seq = seq.expand(*start.shape, seq_len)

    mask = seq >= start[..., None].long()
    mask &= seq < end[..., None].long()
    return mask

def mask_from_frac_lengths(
    seq_len: int,
    frac_lengths: Tensor
):
    device = frac_lengths.device

    lengths = (frac_lengths * seq_len).long()
    max_start = seq_len - lengths

    rand = torch.zeros_like(frac_lengths, device = device).float().uniform_(0, 1)
    start = (max_start * rand).clamp(min = 0)
    end = start + lengths

    return mask_from_start_end_indices(seq_len, start, end)

def generate_mask(batch_size, seq_len, frac_lengths, min_span_len):
    # 计算需要掩盖的起始数量
    n_mask = (frac_lengths * seq_len // min_span_len).long()  # 每个 span 为 10
    # 初始化掩码张量，初始为全 0（未掩盖）
    mask_tensor = torch.zeros((batch_size, seq_len), device=frac_lengths.device, dtype=torch.bool)
    
    for b in range(batch_size):
        # 随机挑选起始帧
        start_frames = random.sample(range(0, seq_len - min_span_len + 1), n_mask[b])  # 0 到 seq_len-10 的范围
        
        for start in start_frames:
            # 将 span 为 10 的区域标记为 1（掩盖）
            mask_tensor[b, start:start + 10] = 1.0
    
    return mask_tensor

def generate_channel_mask(diffusion_input):    

    # 如果 r_drop 小于 threshold，则对每个样本选择一个随机声道进行完全 mask
    batchsize, num_channels, dim = diffusion_input.shape
    for i in range(batchsize):
        channel_means = torch.mean(torch.abs(diffusion_input[i]), dim=1)  # Mean of the absolute values for each channel
        # Determine if any channel is 'small enough'
        if torch.all(channel_means > 0.01):
            # If all channels are not 'small enough', apply the mask
            channel = torch.randint(num_channels, (1,)).item()
            diffusion_input[i, channel, :] = 1e-8  # Mask the channel by setting its values
        else:
            # Optionally log that at least one channel is 'small enough' and no mask is applied
            print(f"Sample {i}: At least one channel is 'small enough', skipping masking.")

    return diffusion_input
