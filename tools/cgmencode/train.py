#!/usr/bin/env python3
"""
train.py — Unified training CLI for all cgmencode architectures.

Usage:
    # Train on conformance vectors (default):
    python3 -m tools.cgmencode.train --model ae --epochs 30

    # Train on Nightscout real data:
    python3 -m tools.cgmencode.train --model ae --epochs 50 --source nightscout \
        --data-path ../t1pal-mobile-workspace/externals/logs/ns-fixtures/90-day-history

    # Transfer learning: pre-train on synthetic, fine-tune on real:
    python3 -m tools.cgmencode.train --model ae --epochs 50 --source nightscout \
        --data-path /path/to/ns-data --pretrained checkpoints/ae_best.pth

    # All models: ae, vae, conditioned, diffusion
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

from .model import CGMTransformerAE, CGMGroupedEncoder
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
    'grouped': {
        'class': CGMGroupedEncoder,
        'kwargs': {'input_dim': 8, 'd_model': 64, 'nhead': 4, 'num_layers': 2},
        'task': 'forecast',
        'conditioned': False,
    },
    'vae': {
        'class': CGMTransformerVAE,
        'kwargs': {'input_dim': 8, 'd_model': 64, 'latent_dim': 64},
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


def train_step(model, batch, optimizer, model_name, criterion, kl_beta=0.01):
    """Single training step, dispatched by model type."""
    optimizer.zero_grad()

    if model_name == 'vae':
        x, _ = batch
        recon, mu, logvar = model(x)
        loss = vae_loss_function(recon, x, mu, logvar, beta=kl_beta)
    elif model_name == 'conditioned':
        (hist, actions), target = batch
        pred = model(hist, actions)
        loss = criterion(pred, target)
    elif model_name == 'diffusion':
        x, _ = batch
        t = torch.randint(0, model.timesteps, (x.size(0),))
        noise = torch.randn_like(x)
        x_t = model.q_sample(x, t, noise=noise)
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


def load_data(args, reg):
    """Load training data from the specified source."""
    if args.source == 'nightscout':
        if not args.data_path:
            print("ERROR: --data-path required for Nightscout source")
            sys.exit(1)
        # Multi-patient: if multiple paths provided, use combined loader
        paths = args.data_path if isinstance(args.data_path, list) else [args.data_path]
        if len(paths) > 1:
            from .real_data_adapter import load_multipatient_nightscout
            return load_multipatient_nightscout(
                paths,
                task=reg['task'],
                window_size=args.window,
                conditioned=reg['conditioned'],
            )
        else:
            from .real_data_adapter import load_nightscout_to_dataset
            return load_nightscout_to_dataset(
                paths[0],
                task=reg['task'],
                window_size=args.window,
                conditioned=reg['conditioned'],
            )
    elif args.source == 'csv':
        from .real_data_adapter import load_csv_to_dataset
        if not args.data_path:
            print("ERROR: --data-path required for CSV source")
            sys.exit(1)
        csv_path = args.data_path[0] if isinstance(args.data_path, list) else args.data_path
        return load_csv_to_dataset(
            csv_path,
            task=reg['task'],
            window_size=args.window,
            conditioned=reg['conditioned'],
        )
    else:  # conformance (default)
        data_dirs = args.data if args.data else DEFAULT_DATA_DIRS
        return load_conformance_to_dataset(
            data_dirs,
            task=reg['task'],
            window_size=args.window,
            conditioned=reg['conditioned'],
        )


def run_training(args):
    print(f"=== cgmencode training: {args.model} ===")
    print(f"Source: {args.source}")

    reg = MODEL_REGISTRY[args.model]
    train_ds, val_ds = load_data(args, reg)

    if not train_ds:
        print("ERROR: No training data found.")
        sys.exit(1)

    print(f"Data: {len(train_ds)} train, {len(val_ds)} val samples")
    print(f"Window: {args.window} steps ({args.window * 5} min)")

    train_loader = DataLoader(train_ds, batch_size=args.batch, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch)

    # Build model
    model = reg['class'](**reg['kwargs'])
    param_count = sum(p.numel() for p in model.parameters())
    print(f"Model: {args.model} ({param_count:,} parameters)")

    # Transfer learning: load pretrained weights
    if args.pretrained:
        print(f"Loading pretrained weights from {args.pretrained}")
        checkpoint = torch.load(args.pretrained, map_location='cpu', weights_only=True)
        if 'model_state' in checkpoint:
            model.load_state_dict(checkpoint['model_state'])
        else:
            model.load_state_dict(checkpoint)
        print(f"  Loaded (epoch {checkpoint.get('epoch', '?')}, val_loss {checkpoint.get('val_loss', '?')})")

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    criterion = nn.MSELoss()

    # LR scheduling
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=args.lr_patience
    )

    # Training loop
    history = {
        'train_loss': [], 'val_loss': [], 'epoch_time': [], 'lr': [],
        'config': {
            'model': args.model, 'source': args.source,
            'epochs': args.epochs, 'batch': args.batch, 'lr': args.lr,
            'window': args.window, 'weight_decay': args.weight_decay,
            'pretrained': args.pretrained, 'patience': args.patience,
            'train_samples': len(train_ds), 'val_samples': len(val_ds),
        },
    }
    best_val = float('inf')
    patience_counter = 0

    for epoch in range(args.epochs):
        t0 = time.time()

        # KL annealing for VAE: ramp β from 0 to target over warmup period
        kl_beta = 0.01
        if args.model == 'vae':
            warmup_epochs = max(1, int(args.epochs * 0.3))
            kl_beta = min(1.0, epoch / warmup_epochs) * 0.1  # target β=0.1

        # Train
        model.train()
        epoch_loss = 0
        for batch in train_loader:
            epoch_loss += train_step(model, batch, optimizer, args.model, criterion, kl_beta=kl_beta)
        train_loss = epoch_loss / len(train_loader)

        # Validate
        model.eval()
        val_loss = 0
        with torch.no_grad():
            for batch in val_loader:
                if args.model == 'vae':
                    x, _ = batch
                    recon, mu, logvar = model(x)
                    val_loss += vae_loss_function(recon, x, mu, logvar, beta=kl_beta).item()
                elif args.model == 'conditioned':
                    (hist, actions), target = batch
                    pred = model(hist, actions)
                    val_loss += criterion(pred, target).item()
                elif args.model == 'diffusion':
                    x, _ = batch
                    t = torch.randint(0, model.timesteps, (x.size(0),))
                    noise = torch.randn_like(x)
                    x_t = model.q_sample(x, t, noise=noise)
                    val_loss += criterion(model(x_t, t), noise).item()
                else:
                    x, y = batch
                    val_loss += criterion(model(x), y).item()
        val_loss /= len(val_loader)

        elapsed = time.time() - t0
        current_lr = optimizer.param_groups[0]['lr']
        history['train_loss'].append(train_loss)
        history['val_loss'].append(val_loss)
        history['epoch_time'].append(elapsed)
        history['lr'].append(current_lr)

        # LR scheduling
        scheduler.step(val_loss)

        # Save best
        if val_loss < best_val:
            best_val = val_loss
            patience_counter = 0
            checkpoint_path = args.output or f"checkpoints/{args.model}_best.pth"
            os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
            torch.save({
                'epoch': epoch,
                'model_state': model.state_dict(),
                'optimizer_state': optimizer.state_dict(),
                'val_loss': val_loss,
                'config': reg['kwargs'],
            }, checkpoint_path)
        else:
            patience_counter += 1

        if epoch % max(1, args.epochs // 20) == 0 or epoch == args.epochs - 1:
            marker = ' *' if val_loss <= best_val else ''
            lr_str = f' lr={current_lr:.1e}' if current_lr != args.lr else ''
            print(f"  Epoch {epoch:3d}/{args.epochs} | "
                  f"train={train_loss:.6f} val={val_loss:.6f}"
                  f"{lr_str} ({elapsed:.1f}s){marker}")

        # Early stopping
        if args.patience > 0 and patience_counter >= args.patience:
            print(f"\n  Early stopping at epoch {epoch} (no improvement for {args.patience} epochs)")
            break

    # Summary
    print(f"\nTraining complete.")
    print(f"  Best val loss: {best_val:.6f}")
    print(f"  Final train:   {history['train_loss'][-1]:.6f}")
    print(f"  Total time:    {sum(history['epoch_time']):.1f}s")
    print(f"  Epochs run:    {len(history['train_loss'])}/{args.epochs}")
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
    parser.add_argument('--output', help='Checkpoint save path')

    # Data source
    parser.add_argument('--source', choices=['conformance', 'nightscout', 'csv'],
                        default='conformance', help='Data source type')
    parser.add_argument('--data-path', nargs='+',
                        help='Path(s) to data directory (for nightscout/csv sources). '
                             'Multiple paths for multi-patient training.')
    parser.add_argument('--patients-dir',
                        help='Auto-expand patient training dirs under this base '
                             '(e.g. externals/ns-data/patients). Uses */training/')
    parser.add_argument('--data', nargs='+', help='Conformance data directories')

    # Transfer learning
    parser.add_argument('--pretrained', help='Path to pretrained checkpoint for fine-tuning')

    # Regularization & scheduling
    parser.add_argument('--weight-decay', type=float, default=1e-5, help='AdamW weight decay')
    parser.add_argument('--patience', type=int, default=0,
                        help='Early stopping patience (0=disabled)')
    parser.add_argument('--lr-patience', type=int, default=5,
                        help='ReduceLROnPlateau patience')

    args = parser.parse_args()

    # Expand --patients-dir into --data-path list
    if args.patients_dir:
        from pathlib import Path
        base = Path(args.patients_dir)
        patient_paths = sorted([
            str(p / 'training')
            for p in base.iterdir()
            if p.is_dir() and (p / 'training' / 'entries.json').exists()
        ])
        if not patient_paths:
            print(f"ERROR: No patient training dirs found under {args.patients_dir}")
            sys.exit(1)
        args.data_path = patient_paths
        args.source = 'nightscout'
        print(f"Auto-detected {len(patient_paths)} patients from {args.patients_dir}")

    run_training(args)


if __name__ == '__main__':
    main()
