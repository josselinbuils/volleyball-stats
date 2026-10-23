#!/usr/bin/env bash
# Downloads the candidate weights and the third-party model code into .cache/bench.
set -euo pipefail

cd "$(dirname "$0")/../.."
C=.cache/bench
mkdir -p "$C"

clone() { # repo commit dir
  if [ ! -d "$C/$3" ]; then
    git clone -q "https://github.com/$1.git" "$C/$3"
    git -C "$C/$3" checkout -q "$2"
  fi
}
clone nttcom/WASB-SBDT 923462cacdeb3353b84ddebdedb3f4b7a8553b0f wasb
clone qaz812345/TrackNetV3 6eda442ada1740573f200f836d93edc9a541ee86 tracknetv3

fetch() { # url file
  [ -f "$C/$2" ] || curl -sSfL -o "$C/$2" "$1"
}
VB=https://raw.githubusercontent.com/asigatchov/vball-net-pytorch/7d295c53fa733782a58dd85f772685044414f8d3/models
fetch "$VB/VballNetGridV1b_seq9_grayscale_20260319_193937.onnx" vballnet_grid_v1b.onnx
fetch "$VB/VballNetGridV1c_seq9_grayscale_20260317.onnx" vballnet_grid_v1c.onnx
fetch https://huggingface.co/deadfast/beach-volley-vision-models/resolve/main/tracknet_best.pt tracknetv3_beach.pt
fetch https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt yolo11n.pt
fetch https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11x.pt yolo11x.pt

gdrive() { # id file
  [ -f "$C/$2" ] || uvx gdown -q -O "$C/$2" "$1"
}
gdrive 1M9y4wPJqLc0K-z-Bo5DP8Ft5XwJuLqIS wasb_volleyball.pth.tar
gdrive 103jOdYp4k20avid4uyB9USCuwiphI4Kz tracknetv2_volleyball.pth.tar
if [ ! -f "$C/vballnet_v1.onnx" ]; then
  gdrive 1ItIxekyN47Rn2gBtq4tF-Tfe-74ez33j vballnet_tf.tgz
  tar -xzf "$C/vballnet_tf.tgz" -C "$C"
  mv "$C/vb-models/VballNetV1_150_h288_w512.onnx" "$C/vballnet_v1.onnx"
  mv "$C/vb-models/VballNetFastV1_155_h288_w512.onnx" "$C/vballnet_fast_v1.onnx"
  rm -r "$C/vb-models" "$C/vballnet_tf.tgz"
fi
