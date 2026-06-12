#!/usr/bin/env python3
"""
Fine-tune a damage detection/segmentation model on CarDD (or CarDD + exported
reviewer feedback).

Any ultralytics-loadable architecture works — YOLO11/YOLO12 (n/s/m, -seg for
segmentation) or RT-DETR — so candidates can be trained and benchmarked
without code changes.

Augmentation defaults target the hard real-world cases: small / thin /
low-contrast scratches, reflective paint, poor lighting, motion blur, and
multiple simultaneous damages:
  - high imgsz (1024): thin scratches vanish at 640
  - mosaic 1.0 + copy_paste 0.3 (seg): more small instances per batch
  - hsv_v 0.5 / hsv_s 0.6: lighting + saturation robustness
  - degrees 5, scale 0.5, translate 0.1: walkaround viewpoint variation

Usage:
  python training/train_damage_model.py --model yolo11s-seg.pt \
      --data ./datasets/cardd/cardd.yaml --epochs 150 --device 0
"""

import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="yolo11s-seg.pt",
                        help="Base weights/architecture (yolo11s-seg.pt, yolo12s.pt, rtdetr-l.pt, or a prior best.pt)")
    parser.add_argument("--data", required=True, help="Dataset yaml from prepare_cardd.py")
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--imgsz", type=int, default=1024)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default=None, help="cuda device id, 'cpu', or 'mps'")
    parser.add_argument("--name", default=None, help="Run name (default: derived from model)")
    parser.add_argument("--patience", type=int, default=30, help="Early-stopping patience")
    # Augmentation overrides (defaults tuned for small/thin/low-contrast damage).
    parser.add_argument("--mosaic", type=float, default=1.0)
    parser.add_argument("--copy-paste", type=float, default=0.3, dest="copy_paste",
                        help="Copy-paste augmentation (segmentation datasets only)")
    parser.add_argument("--hsv-v", type=float, default=0.5, dest="hsv_v")
    parser.add_argument("--hsv-s", type=float, default=0.6, dest="hsv_s")
    parser.add_argument("--hsv-h", type=float, default=0.015, dest="hsv_h")
    parser.add_argument("--degrees", type=float, default=5.0)
    parser.add_argument("--translate", type=float, default=0.1)
    parser.add_argument("--scale", type=float, default=0.5)
    parser.add_argument("--fliplr", type=float, default=0.5)
    return parser.parse_args()


def load_model(weights: str):
    if "rtdetr" in weights.lower():
        from ultralytics import RTDETR
        return RTDETR(weights)
    from ultralytics import YOLO
    return YOLO(weights)


def main() -> None:
    args = parse_args()
    model = load_model(args.model)

    name = args.name or args.model.rsplit("/", 1)[-1].replace(".pt", "") + "-cardd"
    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        name=name,
        patience=args.patience,
        mosaic=args.mosaic,
        copy_paste=args.copy_paste,
        hsv_h=args.hsv_h,
        hsv_s=args.hsv_s,
        hsv_v=args.hsv_v,
        degrees=args.degrees,
        translate=args.translate,
        scale=args.scale,
        fliplr=args.fliplr,
    )
    save_dir = getattr(results, "save_dir", None) or getattr(model.trainer, "save_dir", "runs/")
    print(f"\nTraining complete. Best weights: {save_dir}/weights/best.pt")
    print("Benchmark it against other candidates with training/benchmark_damage_models.py,")
    print("then deploy via ML_DAMAGE_MODEL_PATH (see training/README.md).")


if __name__ == "__main__":
    main()
