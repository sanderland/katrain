"""Train EfficientNet-B0 patch classifier for Go board intersections.

8-class classifier: black, white, black_numbered, white_numbered,
marked_black, marked_white, letter, empty.

Transfer learning from ImageNet pretrained weights with:
- Grayscale input adaptation (sum RGB conv weights)
- Heavy data augmentation for small dataset
- Class-weighted cross-entropy loss
- Two-phase training: frozen backbone then full fine-tune
- Early stopping on validation loss

Usage:
    python scripts/train_patch_classifier.py
    python scripts/train_patch_classifier.py --data-dir data/training_patches/prepared --epochs 50
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader, Dataset
from torchvision.models import EfficientNet_B0_Weights, efficientnet_b0
from torchvision.transforms import v2 as T


INPUT_SIZE = 224
IMAGENET_MEAN = [0.485]  # grayscale approximation (avg of RGB means)
IMAGENET_STD = [0.229]  # grayscale approximation (avg of RGB stds)


class PatchDataset(Dataset):
    """Dataset that loads grayscale patches with class labels from splits.json."""

    def __init__(self, data_dir: Path, file_list: list[str], class_names: list[str], transform=None):
        self.data_dir = data_dir
        self.file_list = file_list
        self.class_names = class_names
        self.class_to_idx = {name: i for i, name in enumerate(class_names)}
        self.transform = transform

    def __len__(self):
        return len(self.file_list)

    def __getitem__(self, idx):
        rel_path = self.file_list[idx]
        cls_name = rel_path.split("/")[0]
        label = self.class_to_idx[cls_name]

        img_path = self.data_dir / rel_path
        img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            img = np.zeros((INPUT_SIZE, INPUT_SIZE), dtype=np.uint8)

        # Resize to INPUT_SIZE x INPUT_SIZE
        img = cv2.resize(img, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_LINEAR)

        # Convert to float tensor [1, H, W], range [0, 1]
        tensor = torch.from_numpy(img).float().unsqueeze(0) / 255.0

        if self.transform is not None:
            tensor = self.transform(tensor)

        # Normalize with ImageNet-like stats
        tensor = T.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD)(tensor)

        return tensor, label


def build_transforms(training: bool):
    """Build augmentation pipeline."""
    if training:
        return T.Compose(
            [
                T.RandomRotation(10),
                T.RandomAffine(degrees=0, translate=(0.05, 0.05), scale=(0.9, 1.1)),
                T.RandomHorizontalFlip(p=0.5),
                T.GaussianBlur(kernel_size=3, sigma=(0.1, 1.0)),
                T.RandomErasing(p=0.1, scale=(0.02, 0.15)),
            ]
        )
    return None


def build_model(num_classes: int, device: torch.device) -> nn.Module:
    """Build EfficientNet-B0 adapted for 1-channel grayscale input."""
    model = efficientnet_b0(weights=EfficientNet_B0_Weights.IMAGENET1K_V1)

    # Adapt first conv from 3-channel to 1-channel by summing RGB weights
    old_conv = model.features[0][0]
    new_conv = nn.Conv2d(
        1,
        old_conv.out_channels,
        kernel_size=old_conv.kernel_size,
        stride=old_conv.stride,
        padding=old_conv.padding,
        bias=old_conv.bias is not None,
    )
    with torch.no_grad():
        new_conv.weight.copy_(old_conv.weight.sum(dim=1, keepdim=True))
        if old_conv.bias is not None:
            new_conv.bias.copy_(old_conv.bias)
    model.features[0][0] = new_conv

    # Replace classifier head
    in_features = model.classifier[1].in_features
    model.classifier = nn.Sequential(nn.Dropout(p=0.3), nn.Linear(in_features, num_classes))

    return model.to(device)


def get_device() -> torch.device:
    """Auto-detect best device: MPS > CUDA > CPU."""
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def train_one_epoch(model, loader, criterion, optimizer, device):
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0

    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

        total_loss += loss.item() * images.size(0)
        _, predicted = outputs.max(1)
        total += labels.size(0)
        correct += predicted.eq(labels).sum().item()

    return total_loss / total, correct / total


@torch.no_grad()
def run_validation(model, loader, criterion, device, class_names):
    model.train(False)
    total_loss = 0.0
    correct = 0
    total = 0

    n_classes = len(class_names)
    tp = [0] * n_classes
    fp = [0] * n_classes
    fn = [0] * n_classes
    class_total = [0] * n_classes

    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        outputs = model(images)
        loss = criterion(outputs, labels)

        total_loss += loss.item() * images.size(0)
        _, predicted = outputs.max(1)
        total += labels.size(0)
        correct += predicted.eq(labels).sum().item()

        for i in range(labels.size(0)):
            true_cls = labels[i].item()
            pred_cls = predicted[i].item()
            class_total[true_cls] += 1
            if pred_cls == true_cls:
                tp[true_cls] += 1
            else:
                fp[pred_cls] += 1
                fn[true_cls] += 1

    per_class = {}
    for i, name in enumerate(class_names):
        if class_total[i] == 0:
            continue
        precision = tp[i] / (tp[i] + fp[i]) if (tp[i] + fp[i]) > 0 else 0.0
        recall = tp[i] / (tp[i] + fn[i]) if (tp[i] + fn[i]) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        per_class[name] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": class_total[i],
        }

    return total_loss / total, correct / total, per_class


def main():
    parser = argparse.ArgumentParser(description="Train EfficientNet-B0 patch classifier")
    parser.add_argument("--data-dir", type=Path, default=Path("data/training_patches/prepared"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/models/patch_classifier"))
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--freeze-epochs", type=int, default=5)
    parser.add_argument("--lr-head", type=float, default=1e-3)
    parser.add_argument("--lr-backbone", type=float, default=1e-5)
    args = parser.parse_args()

    # Load splits
    splits_path = args.data_dir / "splits.json"
    with open(splits_path) as f:
        splits = json.load(f)

    class_names = splits["class_names"]
    class_counts = splits["class_counts"]
    class_weights_dict = splits["class_weights"]
    num_classes = len(class_names)

    device = get_device()
    print(f"Device: {device}")
    print(f"Classes: {num_classes} — {class_names}")

    # Build class weight tensor
    weights = torch.tensor([class_weights_dict[c] for c in class_names], dtype=torch.float32).to(device)

    # Build datasets
    train_dataset = PatchDataset(args.data_dir, splits["train"], class_names, transform=build_transforms(training=True))
    val_dataset = PatchDataset(args.data_dir, splits["val"], class_names, transform=None)

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=0, drop_last=False)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)

    print(f"Train: {len(train_dataset)}, Val: {len(val_dataset)}")

    # Build model
    model = build_model(num_classes, device)
    criterion = nn.CrossEntropyLoss(weight=weights)

    # Phase 1: Freeze backbone, train head only
    for param in model.features.parameters():
        param.requires_grad = False

    optimizer = AdamW(model.classifier.parameters(), lr=args.lr_head, weight_decay=1e-4)
    scheduler = CosineAnnealingLR(optimizer, T_max=args.freeze_epochs)

    best_val_loss = float("inf")
    patience_counter = 0
    best_epoch = 0
    final_epoch = 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    model_path = args.output_dir / "model.pt"

    print(f"\n--- Phase 1: Frozen backbone ({args.freeze_epochs} epochs) ---")
    start_time = time.time()

    for epoch in range(1, args.freeze_epochs + 1):
        train_loss, train_acc = train_one_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_acc, per_class = run_validation(model, val_loader, criterion, device, class_names)
        scheduler.step()
        final_epoch = epoch

        print(
            f"  Epoch {epoch:3d}  "
            f"train_loss={train_loss:.4f}  train_acc={train_acc:.4f}  "
            f"val_loss={val_loss:.4f}  val_acc={val_acc:.4f}"
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_epoch = epoch
            patience_counter = 0
            torch.save(model.state_dict(), model_path)
        else:
            patience_counter += 1

    # Phase 2: Unfreeze backbone, differential LR
    remaining_epochs = args.epochs - args.freeze_epochs
    print(f"\n--- Phase 2: Full fine-tune (up to {remaining_epochs} epochs) ---")

    for param in model.features.parameters():
        param.requires_grad = True

    optimizer = AdamW(
        [
            {"params": model.features.parameters(), "lr": args.lr_backbone},
            {"params": model.classifier.parameters(), "lr": args.lr_head * 0.1},
        ],
        weight_decay=1e-4,
    )
    scheduler = CosineAnnealingLR(optimizer, T_max=remaining_epochs)
    patience_counter = 0

    for epoch in range(args.freeze_epochs + 1, args.epochs + 1):
        train_loss, train_acc = train_one_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_acc, per_class = run_validation(model, val_loader, criterion, device, class_names)
        scheduler.step()
        final_epoch = epoch

        print(
            f"  Epoch {epoch:3d}  "
            f"train_loss={train_loss:.4f}  train_acc={train_acc:.4f}  "
            f"val_loss={val_loss:.4f}  val_acc={val_acc:.4f}"
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_epoch = epoch
            patience_counter = 0
            torch.save(model.state_dict(), model_path)
        else:
            patience_counter += 1
            if patience_counter >= args.patience:
                print(f"  Early stopping at epoch {epoch} (patience={args.patience})")
                break

    elapsed = time.time() - start_time

    # Load best model and do final validation
    model.load_state_dict(torch.load(model_path, map_location=device, weights_only=True))
    val_loss, val_acc, per_class = run_validation(model, val_loader, criterion, device, class_names)

    print(f"\n=== Best model (epoch {best_epoch}) ===")
    print(f"Val loss: {val_loss:.4f}, Val accuracy: {val_acc:.4f}")
    print(f"\nPer-class metrics:")
    print(f"  {'Class':<20} {'Prec':>6} {'Rec':>6} {'F1':>6} {'Support':>8}")
    print(f"  {'-' * 48}")
    for name in class_names:
        if name in per_class:
            m = per_class[name]
            print(f"  {name:<20} {m['precision']:>6.2f} {m['recall']:>6.2f} {m['f1']:>6.2f} {m['support']:>8}")

    # Save class map
    class_map = {str(i): name for i, name in enumerate(class_names)}
    class_map_path = args.output_dir / "class_map.json"
    with open(class_map_path, "w") as f:
        json.dump(class_map, f, indent=2)

    # Save training report
    report = {
        "best_epoch": best_epoch,
        "best_val_loss": round(best_val_loss, 6),
        "best_val_accuracy": round(val_acc, 6),
        "per_class_metrics": per_class,
        "class_counts": class_counts,
        "training_time_seconds": round(elapsed, 1),
        "device": str(device),
        "hyperparams": {
            "epochs_run": final_epoch,
            "batch_size": args.batch_size,
            "lr_head": args.lr_head,
            "lr_backbone": args.lr_backbone,
            "freeze_epochs": args.freeze_epochs,
            "patience": args.patience,
            "input_size": INPUT_SIZE,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    report_path = args.output_dir / "training_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nTraining time: {elapsed:.1f}s")
    print(f"Model saved: {model_path}")
    print(f"Class map: {class_map_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
