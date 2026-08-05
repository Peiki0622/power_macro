# Fixed-Point Weight Memory Format

Each `.mem` file contains one fixed-width hexadecimal two's-complement word per data line. Lines beginning with `//` are metadata comments.

All tensors flatten in C order. Convolution weights use `[out_channel][in_channel][kernel]`; classifier weights use `[output_class][summary_feature]`. The summary order is average features 0-17, maximum features 18-35, and endpoint features 36-53.

The first convolution bias is `[18, 32]` and retains position-specific edge columns after the train-only input standardizer is folded into raw sensor-code arithmetic.

| File | Tensor | Shape | Signed bits | Entries | SHA256 |
| --- | --- | --- | ---: | ---: | --- |
| `conv1_weights.mem` | `conv1.weights` | `[18, 1, 5]` | 8 | 90 | `25a4c88b2a6ae47de2f07c055cd340d3f576a12f84e5270310b439a07140292e` |
| `conv1_bias.mem` | `conv1.bias` | `[18, 32]` | 14 | 576 | `60e565f4c1a75c2317ff1333e2e8d7ca25f7c80517c9c9f6a044f0e142d1d96c` |
| `conv2_weights.mem` | `conv2.weights` | `[8, 18, 5]` | 8 | 720 | `5d78e6a11f7a6871538e0fb6b48e17aa8adb54682e4697689bbb8cd4853bf109` |
| `conv2_bias.mem` | `conv2.bias` | `[8]` | 20 | 8 | `7f741fa92b668a33e63e677c3d6cf45d5f3afcde12381cb7d498c8d39a6e6457` |
| `conv3_weights.mem` | `conv3.weights` | `[18, 8, 5]` | 8 | 720 | `4f5c53d5fac21adfe8f6daa11852de3a20c0f76f081411948c1014206b824c29` |
| `conv3_bias.mem` | `conv3.bias` | `[18]` | 19 | 18 | `5c90d3cf24b30552f9751114b306f536b4bc1d9e455b96c96f5da258b29a5719` |
| `classifier_weights.mem` | `classifier.weights` | `[2, 54]` | 8 | 108 | `256ba85e1c2010c43817ed807d941bbb31df5bbecedc52bb5c7f73f96c2704ed` |
| `classifier_bias.mem` | `classifier.bias` | `[2]` | 19 | 2 | `d54420556b68abce00ba546a8342f78837c9adb85f4a830bbfbbbf58577ad099` |
