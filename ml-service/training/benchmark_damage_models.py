#!/usr/bin/env python3
"""
Benchmark candidate damage detection models on the CarDD val/test split and
rank them so the best one can be deployed via ML_DAMAGE_MODEL_PATH.

Per model it reports:
  - per-class precision / recall / F1 / mAP50 / mAP50-95 (scratch, dent,
    crack, ... individually visible)
  - aggregate P / R / F1 / mAP50 / mAP50-95
  - small-instance recall (ground-truth boxes < --small-area of the image —
    a proxy for thin/low-contrast scratch performance)
  - inference latency (ms/image)

Usage:
  python training/benchmark_damage_models.py \
      --weights yolo11s-cardd.pt yolo12s-cardd.pt rtdetr-cardd.pt \
      --data ./datasets/cardd/cardd.yaml --imgsz 1024 --rank-by f1 \
      --out ./benchmark-results
"""

import argparse
import json
import sys
import time
from pathlib import Path

RANK_KEYS = ("f1", "map50", "map", "recall", "speed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--weights", nargs="+", required=True, help="Candidate .pt weight files")
    parser.add_argument("--data", required=True, help="Dataset yaml from prepare_cardd.py")
    parser.add_argument("--split", default="val", choices=("val", "test"))
    parser.add_argument("--imgsz", type=int, default=1024)
    parser.add_argument("--device", default=None)
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence for small-instance/latency passes")
    parser.add_argument("--small-area", type=float, default=0.01,
                        help="GT instances smaller than this fraction of the image count as 'small' (default 1%%)")
    parser.add_argument("--latency-images", type=int, default=50, help="Images used to measure latency")
    parser.add_argument("--rank-by", default="f1", choices=RANK_KEYS)
    parser.add_argument("--out", default="./benchmark-results", help="Output directory")
    return parser.parse_args()


def load_model(weights: str):
    if "rtdetr" in weights.lower():
        from ultralytics import RTDETR
        return RTDETR(weights)
    from ultralytics import YOLO
    return YOLO(weights)


def f1(p: float, r: float) -> float:
    return (2 * p * r / (p + r)) if (p + r) > 0 else 0.0


def evaluate(weights: str, args: argparse.Namespace) -> dict:
    model = load_model(weights)
    metrics = model.val(data=args.data, split=args.split, imgsz=args.imgsz, device=args.device, verbose=False)

    box = metrics.box
    names = metrics.names if isinstance(metrics.names, dict) else dict(enumerate(metrics.names))
    per_class = {}
    for i, class_index in enumerate(getattr(box, "ap_class_index", [])):
        p, r, ap50, ap = box.class_result(i)
        per_class[names.get(int(class_index), str(class_index))] = {
            "precision": round(float(p), 4),
            "recall": round(float(r), 4),
            "f1": round(f1(float(p), float(r)), 4),
            "map50": round(float(ap50), 4),
            "map50_95": round(float(ap), 4),
        }

    val_images, val_labels = dataset_split_paths(args.data, args.split)
    small = small_instance_recall(model, val_images, val_labels, args)
    latency = measure_latency(model, val_images, args)

    mean_f1 = (
        sum(c["f1"] for c in per_class.values()) / len(per_class)
        if per_class else f1(float(box.mp), float(box.mr))
    )
    return {
        "weights": weights,
        "split": args.split,
        "precision": round(float(box.mp), 4),
        "recall": round(float(box.mr), 4),
        "f1": round(mean_f1, 4),
        "map50": round(float(box.map50), 4),
        "map50_95": round(float(box.map), 4),
        "per_class": per_class,
        "small_instance_recall": small,
        "latency_ms": latency,
    }


def dataset_split_paths(data_yaml: str, split: str):
    import yaml

    with open(data_yaml, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    root = Path(data.get("path", Path(data_yaml).parent))
    images = root / data.get(split, f"images/{split}")
    labels = Path(str(images).replace("images", "labels", 1))
    return images, labels


def read_label_boxes(label_path: Path):
    """Parse YOLO det or seg label lines into (class, x1, y1, x2, y2) normalized."""
    boxes = []
    if not label_path.exists():
        return boxes
    for line in label_path.read_text().splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        cls = int(float(parts[0]))
        coords = [float(v) for v in parts[1:]]
        if len(coords) == 4:  # detect: cx cy w h
            cx, cy, w, h = coords
            boxes.append((cls, cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
        else:  # segment: x1 y1 x2 y2 ... — bbox from polygon extent
            xs, ys = coords[0::2], coords[1::2]
            boxes.append((cls, min(xs), min(ys), max(xs), max(ys)))
    return boxes


def iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def small_instance_recall(model, images_dir: Path, labels_dir: Path, args: argparse.Namespace):
    """Recall over GT instances with normalized area < --small-area (IoU>=0.5, class-aware)."""
    image_paths = sorted(p for p in images_dir.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if not image_paths:
        return None

    total_small = 0
    matched_small = 0
    for image_path in image_paths:
        gt = read_label_boxes(labels_dir / (image_path.stem + ".txt"))
        small_gt = [g for g in gt if (g[3] - g[1]) * (g[4] - g[2]) < args.small_area]
        if not small_gt:
            continue
        total_small += len(small_gt)
        result = model(str(image_path), conf=args.conf, imgsz=args.imgsz, device=args.device, verbose=False)[0]
        preds = []
        boxes = getattr(result, "boxes", None)
        if boxes is not None:
            for b in boxes:
                preds.append((int(b.cls[0]), *[float(v) for v in b.xyxyn[0]]))
        used = set()
        for g in small_gt:
            for j, p in enumerate(preds):
                if j in used or p[0] != g[0]:
                    continue
                if iou(g[1:], p[1:]) >= 0.5:
                    matched_small += 1
                    used.add(j)
                    break

    if total_small == 0:
        return None
    return {
        "recall": round(matched_small / total_small, 4),
        "matched": matched_small,
        "total": total_small,
        "area_threshold": args.small_area,
    }


def measure_latency(model, images_dir: Path, args: argparse.Namespace):
    image_paths = sorted(p for p in images_dir.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    image_paths = image_paths[: args.latency_images]
    if not image_paths:
        return None
    # Warm-up (model load, cudnn autotune) excluded from timing.
    model(str(image_paths[0]), conf=args.conf, imgsz=args.imgsz, device=args.device, verbose=False)
    start = time.perf_counter()
    for image_path in image_paths:
        model(str(image_path), conf=args.conf, imgsz=args.imgsz, device=args.device, verbose=False)
    elapsed = time.perf_counter() - start
    return round(elapsed / len(image_paths) * 1000, 2)


def rank_value(row: dict, key: str) -> float:
    if key == "speed":
        latency = row.get("latency_ms")
        return -latency if latency is not None else float("-inf")
    return row.get(key) or 0.0


def to_markdown(rows, rank_by: str) -> str:
    lines = [
        f"# Damage model benchmark (ranked by {rank_by})",
        "",
        "| rank | model | P | R | F1 | mAP50 | mAP50-95 | small-recall | ms/img |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, row in enumerate(rows, 1):
        small = row.get("small_instance_recall")
        lines.append(
            f"| {i} | {Path(row['weights']).name} | {row['precision']} | {row['recall']} | {row['f1']} "
            f"| {row['map50']} | {row['map50_95']} "
            f"| {small['recall'] if small else 'n/a'} | {row.get('latency_ms') or 'n/a'} |"
        )
    lines.append("")
    for row in rows:
        lines.append(f"## {Path(row['weights']).name} — per class")
        lines.append("")
        lines.append("| class | P | R | F1 | mAP50 | mAP50-95 |")
        lines.append("|---|---|---|---|---|---|")
        for name, c in row["per_class"].items():
            lines.append(f"| {name} | {c['precision']} | {c['recall']} | {c['f1']} | {c['map50']} | {c['map50_95']} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for weights in args.weights:
        print(f"\n=== Evaluating {weights} ===")
        try:
            rows.append(evaluate(weights, args))
        except Exception as exc:  # keep benchmarking the rest
            print(f"FAILED for {weights}: {exc}", file=sys.stderr)

    if not rows:
        print("No models evaluated successfully", file=sys.stderr)
        return 1

    rows.sort(key=lambda r: rank_value(r, args.rank_by), reverse=True)

    (out_dir / "benchmark.json").write_text(json.dumps({"rank_by": args.rank_by, "results": rows}, indent=2))
    markdown = to_markdown(rows, args.rank_by)
    (out_dir / "benchmark.md").write_text(markdown)
    print("\n" + markdown)
    best = rows[0]
    print(f"Best model by {args.rank_by}: {best['weights']}")
    print(f"Deploy with: ML_DAMAGE_MODEL_PATH={Path(best['weights']).resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
