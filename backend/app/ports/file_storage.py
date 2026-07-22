from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol


@dataclass(frozen=True, slots=True)
class StoredFile:
    key: str
    size: int
    sha256: str


class FileStoragePort(Protocol):
    async def save(self, key: str, content: BinaryIO) -> StoredFile: ...

    async def open(self, key: str) -> BinaryIO: ...

    async def delete(self, key: str) -> None: ...

    def resolve(self, key: str) -> Path: ...
