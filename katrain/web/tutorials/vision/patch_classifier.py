"""EfficientNet-B0 based Go intersection patch classifier.

Singleton inference wrapper that loads a trained model and classifies
grayscale patches into 8 classes: black, white, black_numbered,
white_numbered, marked_black, marked_white, letter, empty.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)

INPUT_SIZE = 224
IMAGENET_MEAN = [0.485]
IMAGENET_STD = [0.229]

# Resolve project root relative to this file
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MODEL_DIR = _PROJECT_ROOT / "data" / "models" / "patch_classifier"


class PatchClassifier:
    """EfficientNet-B0 based Go intersection patch classifier."""

    _instance: Optional["PatchClassifier"] = None

    @classmethod
    def get_instance(cls, model_dir: str | Path | None = None) -> "PatchClassifier":
        """Lazy singleton — loads model on first call."""
        if cls._instance is None:
            cls._instance = cls(model_dir or DEFAULT_MODEL_DIR)
        return cls._instance

    @classmethod
    def reset(cls):
        """Reset singleton (for testing)."""
        cls._instance = None

    def __init__(self, model_dir: str | Path):
        import torch
        import torch.nn as nn
        from torchvision.models import efficientnet_b0

        self.model_dir = Path(model_dir)
        model_path = self.model_dir / "model.pt"
        class_map_path = self.model_dir / "class_map.json"

        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")
        if not class_map_path.exists():
            raise FileNotFoundError(f"Class map not found: {class_map_path}")

        with open(class_map_path) as f:
            self.class_map = json.load(f)  # {"0": "black", "1": "white", ...}
        self.num_classes = len(self.class_map)
        self.class_names = [self.class_map[str(i)] for i in range(self.num_classes)]

        # Auto-detect device
        if torch.backends.mps.is_available():
            self.device = torch.device("mps")
        elif torch.cuda.is_available():
            self.device = torch.device("cuda")
        else:
            self.device = torch.device("cpu")

        # Build model architecture (must match training)
        model = efficientnet_b0(weights=None)
        old_conv = model.features[0][0]
        new_conv = nn.Conv2d(
            1,
            old_conv.out_channels,
            kernel_size=old_conv.kernel_size,
            stride=old_conv.stride,
            padding=old_conv.padding,
            bias=old_conv.bias is not None,
        )
        model.features[0][0] = new_conv
        in_features = model.classifier[1].in_features
        model.classifier = nn.Sequential(nn.Dropout(p=0.3), nn.Linear(in_features, self.num_classes))

        # Load weights
        state_dict = torch.load(model_path, map_location=self.device, weights_only=True)
        model.load_state_dict(state_dict)
        model.to(self.device)
        model.train(False)
        self.model = model
        self._torch = torch

        log.info("PatchClassifier loaded: %d classes, device=%s", self.num_classes, self.device)

    def _preprocess(self, patch: np.ndarray) -> "torch.Tensor":
        """Preprocess a single grayscale patch to model input tensor."""
        # Ensure grayscale
        if patch.ndim == 3:
            patch = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)

        # Resize to INPUT_SIZE
        resized = cv2.resize(patch, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_LINEAR)

        # To float tensor [1, H, W] normalized to [0, 1]
        tensor = self._torch.from_numpy(resized).float().unsqueeze(0) / 255.0

        # ImageNet normalization
        tensor = (tensor - IMAGENET_MEAN[0]) / IMAGENET_STD[0]

        return tensor

    def classify_batch(self, patches: list[np.ndarray]) -> list[tuple[str, float]]:
        """Classify a batch of grayscale patches.

        Args:
            patches: list of grayscale numpy arrays (variable size)

        Returns:
            list of (class_label, confidence) tuples
        """
        if not patches:
            return []

        # Preprocess all patches and stack
        tensors = [self._preprocess(p) for p in patches]
        batch = self._torch.stack(tensors).to(self.device)

        # Single forward pass
        with self._torch.no_grad():
            logits = self.model(batch)
            probs = self._torch.softmax(logits, dim=1)
            confidences, indices = probs.max(dim=1)

        # Map to class names
        results = []
        for i in range(len(patches)):
            cls_idx = indices[i].item()
            conf = confidences[i].item()
            cls_name = self.class_names[cls_idx]
            results.append((cls_name, round(conf, 4)))

        return results

    def classify_single(self, patch: np.ndarray) -> tuple[str, float]:
        """Classify a single patch. Convenience wrapper."""
        return self.classify_batch([patch])[0]
