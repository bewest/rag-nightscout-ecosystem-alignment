"""Device management utilities for cgmencode GPU support.

Provides auto-detection of CUDA GPUs and helpers to keep device handling
consistent across training, evaluation, and inference scripts.

Usage:
    from .device import resolve_device, add_device_arg, batch_to_device

    # In argparse setup:
    add_device_arg(parser)

    # After parsing:
    device = resolve_device(args.device)

    # In training/eval loops:
    batch = batch_to_device(batch, device)
"""

import torch


def resolve_device(device_arg: str = 'auto') -> torch.device:
    """Resolve a device string to a torch.device.

    Args:
        device_arg: 'auto' (CUDA if available, else CPU), 'cpu', 'cuda',
                    or 'cuda:N' for a specific GPU.

    Returns:
        torch.device instance.
    """
    if device_arg == 'auto':
        return torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    return torch.device(device_arg)


def add_device_arg(parser):
    """Add a --device argument to an argparse.ArgumentParser."""
    parser.add_argument(
        '--device', default='auto',
        help="Compute device: 'auto' (CUDA if available), 'cpu', 'cuda', "
             "or 'cuda:N' (default: auto)")


def batch_to_device(batch, device: torch.device):
    """Recursively move a batch of tensors (possibly nested tuples) to device.

    Handles common DataLoader output shapes:
        (x, y)                   — standard
        ((hist, actions), target) — conditioned models
    """
    if isinstance(batch, torch.Tensor):
        return batch.to(device, non_blocking=True)
    if isinstance(batch, (tuple, list)):
        moved = [batch_to_device(b, device) for b in batch]
        return type(batch)(moved)
    return batch
