"""Optional local furniture-asset generation boundary.

No model is bundled or invoked here. HouseLayout geometry is never an output of
this interface: a provider may only produce an individual GLB furniture asset.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from struct import unpack
from typing import Protocol


@dataclass(frozen=True)
class FurnitureAssetRequest:
    asset_id: str
    description: str | None = None
    reference_image: Path | None = None


@dataclass(frozen=True)
class GeneratedFurnitureAsset:
    asset_id: str
    glb_path: Path
    generator_id: str
    license: str


class LocalFurnitureAssetGenerator(Protocol):
    def generate(
        self, request: FurnitureAssetRequest, output_directory: Path
    ) -> GeneratedFurnitureAsset:
        """Generate one furniture/decor GLB; never alter architectural geometry."""


def verify_generated_glb(asset: GeneratedFurnitureAsset) -> None:
    """Minimal format gate before an asset can enter a reviewed asset library."""
    if not asset.asset_id or not asset.generator_id or not asset.license:
        raise ValueError("Asset ID, generator ID, and license are required.")
    if asset.glb_path.suffix.lower() != ".glb":
        raise ValueError("Generated assets must be GLB files.")
    with asset.glb_path.open("rb") as source:
        header = source.read(12)
        if len(header) != 12 or header[:4] != b"glTF":
            raise ValueError("The output is not a binary glTF file.")
        chunk_header = source.read(8)
        if len(chunk_header) != 8:
            raise ValueError("The GLB has no JSON scene chunk.")
        chunk_length, chunk_type = unpack("<I4s", chunk_header)
        if chunk_type != b"JSON" or chunk_length == 0:
            raise ValueError("The GLB has no JSON scene chunk.")
        chunk = source.read(chunk_length)
    version, declared_length = unpack("<II", header[4:])
    if version != 2 or declared_length != asset.glb_path.stat().st_size:
        raise ValueError("The GLB header is invalid or truncated.")
    if len(chunk) != chunk_length:
        raise ValueError("The GLB JSON chunk is truncated.")
    try:
        scene = json.loads(chunk)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("The GLB JSON chunk is invalid.") from exc
    if scene.get("asset", {}).get("version") != "2.0":
        raise ValueError("The GLB asset version must be 2.0.")
