#!/usr/bin/env python3
"""
Convert the CarDD COCO dataset into ultralytics YOLO format (detect or segment).

Input layout (from https://cardd-ustc.github.io/):
  CarDD_COCO/
    annotations/instances_{train,val,test}2017.json
    {train,val,test}2017/*.jpg

Output layout:
  <out>/
    images/{train,val,test}/   (symlinks by default; --copy to copy)
    labels/{train,val,test}/   one .txt per image
    cardd.yaml                 ultralytics data config

Usage:
  python training/prepare_cardd.py --cardd-root /data/CarDD_release/CarDD_COCO \
      --out ./datasets/cardd --task segment
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

SPLITS = {"train": "train2017", "val": "val2017", "test": "test2017"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cardd-root", required=True, help="Path to CarDD_COCO directory")
    parser.add_argument("--out", required=True, help="Output dataset directory")
    parser.add_argument("--task", choices=("detect", "segment"), default="segment",
                        help="Label format: bounding boxes or segmentation polygons (default: segment)")
    parser.add_argument("--copy", action="store_true", help="Copy images instead of symlinking")
    return parser.parse_args()


def convert_split(coco_json: Path, images_dir: Path, out_images: Path, out_labels: Path,
                  task: str, copy_images: bool) -> dict:
    with open(coco_json, "r", encoding="utf-8") as fh:
        coco = json.load(fh)

    # Category ids are remapped to a contiguous 0-based index, ordered by id.
    categories = sorted(coco["categories"], key=lambda c: c["id"])
    cat_index = {c["id"]: i for i, c in enumerate(categories)}
    names = [c["name"] for c in categories]

    images_by_id = {img["id"]: img for img in coco["images"]}
    labels_by_image: dict = {img_id: [] for img_id in images_by_id}

    skipped_crowd = 0
    skipped_empty = 0
    for ann in coco["annotations"]:
        if ann.get("iscrowd"):
            skipped_crowd += 1
            continue
        img = images_by_id.get(ann["image_id"])
        if img is None:
            continue
        w, h = float(img["width"]), float(img["height"])
        cls = cat_index[ann["category_id"]]

        if task == "segment":
            segmentation = ann.get("segmentation") or []
            polygons = [poly for poly in segmentation if isinstance(poly, list) and len(poly) >= 6]
            if not polygons:
                skipped_empty += 1
                continue
            # One YOLO line per polygon (multi-part instances become multiple lines).
            for poly in polygons:
                coords = []
                for i in range(0, len(poly) - 1, 2):
                    coords.append(min(max(poly[i] / w, 0.0), 1.0))
                    coords.append(min(max(poly[i + 1] / h, 0.0), 1.0))
                labels_by_image[ann["image_id"]].append(
                    f"{cls} " + " ".join(f"{v:.6f}" for v in coords)
                )
        else:
            x, y, bw, bh = ann["bbox"]
            if bw <= 0 or bh <= 0:
                skipped_empty += 1
                continue
            cx = min(max((x + bw / 2) / w, 0.0), 1.0)
            cy = min(max((y + bh / 2) / h, 0.0), 1.0)
            nw = min(bw / w, 1.0)
            nh = min(bh / h, 1.0)
            labels_by_image[ann["image_id"]].append(f"{cls} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

    out_images.mkdir(parents=True, exist_ok=True)
    out_labels.mkdir(parents=True, exist_ok=True)

    written = 0
    missing_images = 0
    for img_id, img in images_by_id.items():
        src = images_dir / img["file_name"]
        if not src.exists():
            missing_images += 1
            continue
        dst = out_images / img["file_name"]
        if not dst.exists():
            if copy_images:
                shutil.copy2(src, dst)
            else:
                dst.symlink_to(src.resolve())
        label_path = out_labels / (Path(img["file_name"]).stem + ".txt")
        label_path.write_text("\n".join(labels_by_image[img_id]) + ("\n" if labels_by_image[img_id] else ""))
        written += 1

    return {
        "names": names,
        "images": written,
        "instances": sum(len(v) for v in labels_by_image.values()),
        "skipped_crowd": skipped_crowd,
        "skipped_empty": skipped_empty,
        "missing_images": missing_images,
    }


def main() -> int:
    args = parse_args()
    cardd_root = Path(args.cardd_root)
    out_root = Path(args.out)

    names = None
    for split, coco_name in SPLITS.items():
        coco_json = cardd_root / "annotations" / f"instances_{coco_name}.json"
        images_dir = cardd_root / coco_name
        if not coco_json.exists():
            print(f"[skip] {split}: {coco_json} not found")
            continue
        stats = convert_split(
            coco_json,
            images_dir,
            out_root / "images" / split,
            out_root / "labels" / split,
            args.task,
            args.copy,
        )
        if names is None:
            names = stats["names"]
        elif names != stats["names"]:
            print(f"ERROR: category mismatch between splits: {names} vs {stats['names']}", file=sys.stderr)
            return 1
        print(
            f"[{split}] images={stats['images']} instances={stats['instances']} "
            f"crowd_skipped={stats['skipped_crowd']} empty_skipped={stats['skipped_empty']} "
            f"missing_images={stats['missing_images']}"
        )

    if names is None:
        print("ERROR: no annotation files found — check --cardd-root", file=sys.stderr)
        return 1

    yaml_path = out_root / "cardd.yaml"
    lines = [
        "# CarDD in ultralytics YOLO format — generated by training/prepare_cardd.py",
        f"# task: {args.task}",
        f"path: {out_root.resolve()}",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        "names:",
    ]
    lines += [f"  {i}: {name}" for i, name in enumerate(names)]
    yaml_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {yaml_path}")
    print(f"Classes: {names}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
