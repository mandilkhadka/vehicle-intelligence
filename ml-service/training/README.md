# Damage model training (CarDD)

Workflow for training, benchmarking, and deploying the dedicated automotive
damage detection model used by the ML service (`ML_DAMAGE_MODEL_PATH`).

CLIP is **not** part of damage detection — it is used upstream for frame
quality ranking, key-frame selection, and vehicle identification only. The
detector trained here is the primary damage source; the VLM remains a
complementary second opinion for categories outside the training taxonomy.

## 1. Dataset: CarDD

[CarDD](https://cardd-ustc.github.io/) (Car Damage Detection) is ~4,000 images
/ ~9,000 instances of real car damage with COCO-format detection +
segmentation annotations. Request/download it from the project page, then
unpack so you have:

```
CarDD_release/
  CarDD_COCO/
    annotations/
      instances_train2017.json
      instances_val2017.json
      instances_test2017.json
    train2017/   # images
    val2017/
    test2017/
```

Classes (6): `dent`, `scratch`, `crack`, `glass shatter`, `lamp broken`,
`tire flat`. The service maps these to the pipeline taxonomy in
`src/services/damage_model.py` (`glass shatter → crack`,
`lamp broken → broken_light`, `tire flat → wheel_damage`); extend with
`ML_DAMAGE_CLASS_MAP` if you train extra classes (e.g. `rust`).

## 2. Convert to YOLO format

```bash
python training/prepare_cardd.py \
  --cardd-root /path/to/CarDD_release/CarDD_COCO \
  --out ./datasets/cardd \
  --task segment        # or "detect" for boxes only
```

Writes `images/{train,val,test}`, `labels/{train,val,test}`, and
`cardd.yaml`. Segmentation labels are preferred — masks let the frontend
outline the exact damage shape, and seg models still report box mAP.

## 3. Train

```bash
python training/train_damage_model.py \
  --model yolo11s-seg.pt \
  --data ./datasets/cardd/cardd.yaml \
  --epochs 150 --imgsz 1024 --batch 16 --device 0
```

Any ultralytics-loadable architecture works: `yolo11{n,s,m}-seg.pt`,
`yolo12{n,s,m}.pt` (detect), `rtdetr-l.pt`, or a previous fine-tune to resume
from. Defaults bake in augmentation tuned for the hard cases — small/thin/
low-contrast scratches, reflective surfaces, poor lighting, motion blur:
mosaic, copy-paste (seg), HSV jitter, slight rotation/scale, and a high
`imgsz` (1024) so thin scratches survive downscaling. Override any
hyperparameter via CLI flags.

## 4. Benchmark and pick the best model

```bash
python training/benchmark_damage_models.py \
  --weights runs/segment/yolo11s/weights/best.pt runs/detect/yolo12s/weights/best.pt rtdetr-cardd.pt \
  --data ./datasets/cardd/cardd.yaml \
  --imgsz 1024 --device 0 \
  --rank-by f1 \
  --out ./benchmark-results
```

Reports per-class precision / recall / F1 / mAP50 / mAP50-95 (so scratch,
dent, and crack accuracy are visible individually), small-instance recall
(area < 1% of image — thin scratches), and inference latency. Ranks all
candidates by `--rank-by` (`f1` | `map50` | `map` | `recall` | `speed`) and
writes `benchmark.json` + `benchmark.md`.

## 5. Deploy

Point the service at the winning weights — no code change required:

```bash
# ml-service/.env
ML_DAMAGE_MODEL_PATH=/abs/path/to/best.pt
ML_DAMAGE_MODEL_ARCH=auto          # auto | yolo | rtdetr
ML_DAMAGE_MODEL_CONFIDENCE=0.35    # inference confidence gate
ML_DAMAGE_MODEL_IOU=0.5
ML_DAMAGE_MODEL_IMGSZ=1024
```

Restart the ML service; `ModelRegistry` loads the model at startup and
`DamageDetector` uses it as the primary damage source.

## Retraining from reviewer feedback

`backend/scripts/export-training-set.ts` exports confirmed/corrected reviewer
feedback as a YOLO training set. Merge it with CarDD (append to the train
split, keep CarDD val/test untouched for comparable metrics) and re-run steps
3–4 to improve real-world generalization over time.
