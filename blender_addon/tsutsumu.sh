#!/bin/bash
# Blender を起動せず、アドオンだけを zip にまとめる。
set -euo pipefail
cd "$(dirname "$0")"
python3 - <<'PY'
from pathlib import Path
import zipfile

root = Path.cwd()
output = root / 'kernel_ai.zip'
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in sorted((root / 'kernel_ai').glob('*.py')):
        archive.write(path, path.relative_to(root))
print(f'作成: {output.name}')
PY
