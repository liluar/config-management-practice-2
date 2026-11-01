"""Ручная загрузка и разбор прямых зависимостей пакета NuGet."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
import zipfile
from io import BytesIO
from typing import Any


HTTP_TIMEOUT = 30
NUPKG_SUFFIX = ".nupkg"
NUSPEC_SUFFIX = ".nuspec"
PACKAGE_BASE_TYPE = "PackageBaseAddress/3.0.0"


def download_bytes(url: str) -> bytes:
    """Скачать содержимое URL стандартным HTTP-клиентом."""
    request = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return response.read()
    except (OSError, urllib.error.URLError) as error:
        raise ValueError(f"Не удалось скачать данные: {url}") from error


def resource_types(resource: dict[str, Any]) -> list[str]:
    """Нормализовать поле типа ресурса из индекса NuGet."""
    value = resource.get("@type", [])
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def package_base_address(repository_url: str) -> str:
    """Найти адрес хранилища пакетов в индексе NuGet V3."""
    try:
        index = json.loads(download_bytes(repository_url))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("Некорректный индекс NuGet") from error
    resources = index.get("resources", [])
    for resource in resources:
        if PACKAGE_BASE_TYPE in resource_types(resource):
            return resource["@id"].rstrip("/")
    raise ValueError("В индексе NuGet не найдено хранилище пакетов")


def package_url(base_url: str, package_name: str, version: str) -> str:
    """Сформировать URL .nupkg для заданных имени и версии."""
    package_id = urllib.parse.quote(package_name.lower(), safe=".-")
    package_version = urllib.parse.quote(version.lower(), safe=".-")
    filename = f"{package_id}.{package_version}{NUPKG_SUFFIX}"
    return f"{base_url}/{package_id}/{package_version}/{filename}"


def local_name(tag: str) -> str:
    """Вернуть имя XML-элемента без пространства имён."""
    return tag.rsplit("}", 1)[-1]


def dependency_entries(container: ElementTree.Element) -> list[tuple[str, str]]:
    """Извлечь зависимости из элемента или его целевых групп."""
    entries = []
    for child in container:
        elements = child if local_name(child.tag) == "group" else [child]
        for element in elements:
            if local_name(element.tag) != "dependency":
                continue
            package_id = element.attrib.get("id", "").strip()
            version = element.attrib.get("version", "").strip()
            if package_id:
                entries.append((package_id, version))
    return entries


def parse_nuspec(contents: bytes) -> list[tuple[str, str]]:
    """Прочитать прямые зависимости из XML nuspec."""
    try:
        root = ElementTree.fromstring(contents)
    except ElementTree.ParseError as error:
        raise ValueError("Некорректный XML-файл nuspec") from error
    metadata = next(
        (element for element in root.iter()
         if local_name(element.tag) == "metadata"),
        None,
    )
    if metadata is None:
        raise ValueError("В nuspec не найден элемент metadata")
    dependencies = next(
        (element for element in metadata
         if local_name(element.tag) == "dependencies"),
        None,
    )
    if dependencies is None:
        return []
    return dependency_entries(dependencies)


def nuspec_contents(package_data: bytes) -> bytes:
    """Открыть ZIP-пакет и прочитать содержащийся в нём nuspec."""
    try:
        with zipfile.ZipFile(BytesIO(package_data)) as archive:
            nuspec_path = next(
                (name for name in archive.namelist()
                 if name.lower().endswith(NUSPEC_SUFFIX)),
                None,
            )
            if nuspec_path is None:
                raise ValueError("В .nupkg не найден файл .nuspec")
            return archive.read(nuspec_path)
    except zipfile.BadZipFile as error:
        raise ValueError("Скачанный пакет не является ZIP-архивом") from error


def get_direct_dependencies(
    package_name: str,
    version: str,
    repository_url: str,
) -> list[tuple[str, str]]:
    """Скачать пакет заданной версии и вернуть его прямые зависимости."""
    base_url = package_base_address(repository_url)
    package_data = download_bytes(package_url(base_url, package_name, version))
    return parse_nuspec(nuspec_contents(package_data))
