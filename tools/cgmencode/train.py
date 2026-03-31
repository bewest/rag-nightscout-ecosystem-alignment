#!/usr/bin/env python3
"""
train.py — Unified training CLI for all cgmencode architectures.

Usage:
    python3 -m tools.cgmencode.train --model ae --epochs 30 --data conformance/in-silico/vectors
    python3 -m tools.cgmencode.train --model vae --epochs 50 --data conformance/in-silico/vectors conformance/t1pal/vectors/oref0-endtoend
    python3 -m tools.cgmencode.train --model conditioned --epochs 30
"""

import argparse
import json
import sys
import os
import time
import torch
import torch.nn as nn
import numpy as np
from pathlib import Path
from torch.utils.data import DataLoader

from .model import CGMTransformerAE, train_one_epoch, evaluate
from .toolbox import CGMTransformerVAE, ConditionedTransformer, CGMDenoisingDiffusion, vae_loss_function
from .sim_adapter import load_conformance_to_dataset


DEFAULT_DATA_DIRS = [
    'conformance/in-silico/vectors',
    'conformance/t1pal/vectors/oref0-endtoend',
]

MODEL_REGISTRY = {
    'ae': {
        'class': CGMTransformerAE,
        'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2},
        'task': 'forecast',
        'conditioned': False,
    },
    'vae': {
        'class': CGMTransformerVAE,
        'kwargs': {'input_dim': 8, 'd_model': 64, 'latent_dim': 32},
        'task': 'reconstruct',
        'conditioned': False,
    },
    'conditioned': {
        'class': ConditionedTransformer,
        'kwargs': {'history_dim': 8, 'action_dim': 3, 'd_model': 64},
        'task': 'forecast',
        'conditioned': True,
    },
    'diffusion': {
        'class': CGMDenoisingDiffusion,
        'kwargs': {'input_dim': 8, 'd_model': 64},
        'task': 'reconstruct',
        'conditioned': False,
    },
}


def train_step(model, batch, optimizer, model_name, criterion):
    """Single training step, dispatched by model type."""
    optimizer.zero_grad()

    if model_name == 'vae':
        x, _ = batch
        recon, mu, logvar = model(x)
        loss = vae_loss_function(recon, x, mu, logvar)
    elif model_name == 'conditioned':
        (hist, actions), target = batch
        pred = model(hist, actions)
        loss = criterion(pred, target)
    elif model_name == 'diffusion':
        x, _ = batch
        t = torch.randint(0, 1000, (x.size(0),))
        noise = torch.randn_like(x)
        x_t = x + noise
        predicted_noise = model(x_t, t)
        loss = criterion(predicted_noise, noise)
    else:  # ae
        x, y = batch
        output = model(x)
        loss = criterion(output, y)

    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
    optimizer.step()
    return loss.item()


def run_training(args):
    print(f"=== cgmencode training: {args.model} ===")

    # Load data
    data_dirs = args.data if args.data else DEFAULT_DATA_DIRS
    reg = MODEL_REGISTRY[args.model]

    train_ds, val_ds = load_conformance_to_dataset(
        data_dirs,
        task=reg['task'],
        window_size=args.window,
        conditioned=reg['conditioned'],
    )

    if not train_ds:
        print("ERROR: No training data found. Run generate_training_data.py first.")
        sys.exit(1)

    print(f"Data: {len(train_ds)} train, {len(val_ds)} val samples")
    print(f"Window: {args.window} steps ({args.window * 5} min)")

    train_loader = DataLoader(train_ds, batch_size=args.batch, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch)

    # Build model
    model = reg['class'](**reg['kwargs'])
    param_count = sum(p.numel() for p in model.parameters())
    print(f"Model: {args.model} ({param_count:,} parameters)")

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-5)
    criterion = nn.MSELoss()

    # Training loop
    history = {'train_loss': [], 'val_loss': [], 'epoch_time': []}
    best_val = float('inf')

    for epoch in range(args.epochs):
        t0 = time.time()

        # Train
        model.train()
        epoch_loss = 0
        for batch in train_loader:
            epoch_loss += train_step(model, batch, optimizer, args.model, criterion)
        train_loss = epoch_loss / len(train_loader)

        # Validate
        model.eval()
        val_loss = 0
        with torch.no_grad():
            for batch in val_loader:
                if args.model == 'vae':
                    x, _ = batch
                    recon, mu, logvar = model(x)
                    val_loss += vae_loss_function(recon, x, mu, logvar).item()
                elif args.model == 'conditioned':
                    (hist, actions), target = batch
                    pred = model(hist, actions)
                    val_loss += criterion(pred, target).item()
                elif args.model == 'diffusion':
                    x, _ = batch
                    t = torch.randint(0, 1000, (x.size(0),))
                    noise = torch.randn_like(x)
                    val_loss += criterion(model(x + noise, t), noise).item()
                else:
                    x, y = batch
                    val_loss += criterion(model(x), y).item()
        val_loss /= len(val_loader)

        elapsed = time.time() - t0
        history['train_loss'].append(train_loss)
        history['val_loss'].append(val_loss)
        history['epoch_time'].append(elapsed)

        # Save best
        if val_loss < best_val:
            best_val = val_loss
            checkpoint_path = args.output or f"checkpoints/{args.model}_best.pth"
            os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
            torch.save({
                'epoch': epoch,
                'model_state': model.state_dict(),
                'optimizer_state': optimizer.state_dict(),
                'val_loss': val_loss,
                'config': reg['kwargs'],
            }, checkpoint_path)

        if epoch % max(1, args.epochs // 20) == 0 or epoch == args.epochs - 1:
            marker = ' *' if val_loss <= best_val else ''
            print(f"  Epoch {epoch:3d}/{args.epochs} | "
                  f"train={train_loss:.6f} val={val_loss:.6f} "
                  f"({elapsed:.1f}s){marker}")

    # Summary
    print(f"\nTraining complete.")
    print(f"  Best val loss: {best_val:.6f}")
    print(f"  Final train:   {history['train_loss'][-1]:.6f}")
    print(f"  Total time:    {sum(history['epoch_time']):.1f}s")
    if args.output or True:
        cp = args.output or f"checkpoints/{args.model}_best.pth"
        print(f"  Checkpoint:    {cp}")

    # Save training history
    hist_path = f"checkpoints/{args.model}_history.json"
    os.makedirs("checkpoints", exist_ok=True)
    with open(hist_path, 'w') as f:
        json.dump(history, f, indent=2)
    print(f"  History:       {hist_path}")

    return history


def main():
    parser = argparse.ArgumentParser(description='Train cgmencode models')
    parser.add_argument('--model', required=True, choices=list(MODEL_REGISTRY.keys()),
                        help='Architecture to train')
    parser.add_argument('--epochs', type=int, default=30)
    parser.add_argument('--batch', type=int, default=32)
    parser.add_argument('--lr', type=float, default=1e-3)
    parser.add_argument('--window', type=int, default=12, help='Window size in 5-min steps')
    parser.add_argument('--data', nargs='+', help='Data directories (default: conformance dirs)')
    parser.add_argument('--output', help='Checkpoint save path')
    args = parser.parse_args()

    run_training(args)


if __name__ == '__main__':
    main()
