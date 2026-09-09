# Third-party notices

Mira's full classroom runtime integrates [THU-MAIC/OpenMAIC](https://github.com/THU-MAIC/OpenMAIC), pinned by `upstream.lock.json`.

OpenMAIC is licensed under the MIT License. The upstream source is fetched at build/deployment time and is not copied into this repository. Preserve the upstream `LICENSE` file in every built image and source distribution.

VoxCPM2 is an independently deployed TTS model. Review the model repository, model weights and serving-runtime licenses before production deployment; do not assume the OpenMAIC MIT license covers those separate artifacts.
