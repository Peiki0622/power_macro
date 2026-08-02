# Fixed-Point Weight Memory Format

Each `.mem` file contains one fixed-width hexadecimal two's-complement word per data line. Lines beginning with `//` are metadata comments.

All tensors flatten in C order. Convolution weights use `[out_channel][in_channel][kernel]`; classifier weights use `[output_class][summary_feature]`. The summary order is average features 0-17, maximum features 18-35, and endpoint features 36-53.

The first convolution bias is `[18][32]`, not `[18]`: its four edge columns preserve zero padding after the train-only input standardizer was folded into raw sensor-code arithmetic.

| File | Tensor | Shape | Signed bits | Entries | SHA256 |
| --- | --- | --- | ---: | ---: | --- |
| `conv1_weights.mem` | `conv1.weights` | `[18, 1, 5]` | 8 | 90 | `d91d56b86a79c1069461aaa595ac5ee58f0baa70f1763708e1b88fb3884739e5` |
| `conv1_bias.mem` | `conv1.bias` | `[18, 32]` | 14 | 576 | `d58d56b90e6759f372879d05fd17b68fdfb6109311487b69eb03f0d4dba6f045` |
| `conv2_weights.mem` | `conv2.weights` | `[18, 18, 5]` | 8 | 1620 | `847d8dfd05e55ca172098cbb740b5efc8c0e138d8dc4b9428334a53c98f49d06` |
| `conv2_bias.mem` | `conv2.bias` | `[18]` | 20 | 18 | `1eea172da479fa03c7f69201aeaa9b6de4c6a8b476c4c6f9dc6b4041b332d341` |
| `conv3_weights.mem` | `conv3.weights` | `[18, 18, 5]` | 8 | 1620 | `73d7c4c304cf5109002264b3c680eceb260b6c91f320ab61ed7c4b817e47e0e8` |
| `conv3_bias.mem` | `conv3.bias` | `[18]` | 20 | 18 | `8ecaaa42e3bff438167fb21394ea3562260f90cd899cdce79cb030d2a5973002` |
| `classifier_weights.mem` | `classifier.weights` | `[2, 54]` | 8 | 108 | `d17c5c9f16bfa1b236a80b8a1aac04c1ba3fd4042db8f7a44062b1160a288044` |
| `classifier_bias.mem` | `classifier.bias` | `[2]` | 20 | 2 | `eb797611795947dc6b65b3ba35904b55308285e736d0178f13d778ef8ae482d8` |
