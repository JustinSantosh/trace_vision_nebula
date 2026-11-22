# TRACEVISION AI

Hack-A-Sol 5.0, Track 02, AIML-01: vehicle identification and traceability from CCTV footage.

## Status: Phase 0A (dataset audit) is complete. Several items are blocked; see [PROBLEMS.md](PROBLEMS.md).

- `TRACEVISION_DATA/reports/`: audit, coverage matrix and licence report
- `TRACEVISION_DATA/models/model_dependencies.md`: pretrained models used (UVH-26, Awiros ANPR OCR, YOLOv8n)
- `TRACEVISION_DATA/scripts/`: Phase 0 scripts

Raw data, video frames, plate crops and model weights are deliberately **not** committed. This is because of their size, their licences and the real number plates they contain.

### Run the audit
```
python TRACEVISION_DATA/scripts/inspect_datasets.py --root TRACEVISION_DATA/raw --out TRACEVISION_DATA/reports/dataset_audit.json
```
Requires Pillow, opencv-python and PyYAML.

Licence note: the Ultralytics-based models (YOLOv8, UVH-26 YOLOv11) are AGPL-3.0.
