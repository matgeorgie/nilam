from io import BytesIO
from pathlib import Path
from struct import pack
from unittest.mock import patch

import pytest

from app.asset_generation import GeneratedFurnitureAsset, verify_generated_glb


def test_generated_asset_boundary_accepts_a_glb_header():
    path = Path("chair.glb")
    scene = b'{"asset":{"version":"2.0"}}   '
    data = b"glTF" + pack("<II", 2, 20 + len(scene)) + pack("<I4s", len(scene), b"JSON") + scene
    with patch.object(Path, "open", return_value=BytesIO(data)), patch.object(Path, "stat") as stat:
        stat.return_value.st_size = len(data)
        verify_generated_glb(GeneratedFurnitureAsset("chair", path, "test-adapter", "test-only"))


def test_generated_asset_boundary_rejects_non_glb_and_missing_license():
    path = Path("chair.glb")
    with patch.object(Path, "open", return_value=BytesIO(b"not-a-glb")):
        with pytest.raises(ValueError, match="binary glTF"):
            verify_generated_glb(GeneratedFurnitureAsset("chair", path, "test-adapter", "test-only"))
    with pytest.raises(ValueError, match="license"):
        verify_generated_glb(GeneratedFurnitureAsset("chair", path, "test-adapter", ""))
