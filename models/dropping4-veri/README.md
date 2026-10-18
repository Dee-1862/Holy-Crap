# dropping4-veri

YOLO11n trained on Veri (job abe1b30a56c4): one A10G of a 4x A10G node, batch 32, 12 pipe-transport workers, 30-minute training cap. 20 epochs; best epoch 19.
Held-out test: mAP50 0.854, mAP50-95 0.573. This is the Veri-track model; its accuracy is near-identical to dropping4-laptop.

See [../README.md](../README.md) for input/output format, classes and caveats.
