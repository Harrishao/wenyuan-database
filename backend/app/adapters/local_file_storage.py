import asyncio
import hashlib
from pathlib import Path
from typing import BinaryIO

from app.ports.file_storage import StoredFile


class InvalidStorageKeyError(ValueError):
    pass


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if candidate == self.root or self.root not in candidate.parents:
            raise InvalidStorageKeyError("文件存储键超出允许目录")
        return candidate

    async def save(self, key: str, content: BinaryIO) -> StoredFile:
        target = self.resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)

        def write_file() -> StoredFile:
            digest = hashlib.sha256()
            size = 0
            with target.open("wb") as output:
                while block := content.read(1024 * 1024):
                    output.write(block)
                    digest.update(block)
                    size += len(block)
            return StoredFile(key=key, size=size, sha256=digest.hexdigest())

        return await asyncio.to_thread(write_file)

    async def open(self, key: str) -> BinaryIO:
        return await asyncio.to_thread(self.resolve(key).open, "rb")

    async def delete(self, key: str) -> None:
        target = self.resolve(key)
        if target.exists():
            await asyncio.to_thread(target.unlink)

    async def copy_from(self, source: Path, key: str) -> StoredFile:
        with source.open("rb") as content:
            return await self.save(key, content)
