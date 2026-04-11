"""
v9b_model.py
Torch MLP architecture for v9b safety model.
Matches the exact architecture used during training (block2_mixed_feature_sets,
hidden=(256,256), batchnorm=True, dropout=0.3, activation=relu).
"""
from __future__ import annotations

import torch
import torch.nn as nn


class TorchMLP(nn.Module):
    """
    Fully connected MLP regressor matching the v9b training architecture.

    Architecture:
        Linear -> BN -> ReLU -> Dropout -> Linear -> BN -> ReLU -> Dropout -> Linear(1)

    Args:
        in_dim:       Number of input features (from v9b feature list).
        hidden_sizes: Tuple of hidden layer sizes. Default: (256, 256).
        dropout:      Dropout rate applied after each hidden activation. Default: 0.3.
        activation:   Activation function name ('relu' or 'gelu'). Default: 'relu'.
        use_batchnorm: Whether to apply BatchNorm1d after each linear layer. Default: True.
    """

    def __init__(
        self,
        in_dim: int,
        hidden_sizes: tuple[int, ...] = (256, 256),
        dropout: float = 0.3,
        activation: str = "relu",
        use_batchnorm: bool = True,
    ) -> None:
        super().__init__()

        act_fn = nn.ReLU() if activation == "relu" else nn.GELU()

        layers: list[nn.Module] = []
        prev = in_dim
        for h in hidden_sizes:
            layers.append(nn.Linear(prev, h))
            if use_batchnorm:
                layers.append(nn.BatchNorm1d(h))
            layers.append(act_fn)
            if dropout > 0:
                layers.append(nn.Dropout(dropout))
            prev = h

        layers.append(nn.Linear(prev, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)
