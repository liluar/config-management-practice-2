"""Ручная загрузка и разбор метаданных NuGet-пакетов."""

from __future__ import annotations

import http.client
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
import zipfile
from io import BytesIO
from typing import Any

HTTP_TIMEOUT = 30
DOWNLOAD_ATTEMPTS = 3
RETRY_DELAY = 1
NUPKG_SUFFIX = ".nupkg"
NUSPEC_SUFFIX = ".nuspec"
PACKAGE_BASE_TYPE = "PackageBaseAddress/3.0.0"
VERSION_PART = re.compile(r"\d+(?:\.\d+){0,3}(?:-[A-Za-z0-9.-]+)?")
VERSION_RANGE = re.compile(
    r"^(\[|\()\s*([^,]*)\s*,\s*([^\]\)]*)\s*(\]|\))$"
)


def download_bytes(url: str) -> bytes:
    """Скачать данные обычным HTTP-клиентом Python."""
    request = urllib.request.Request(url)
    last_error = None
    for attempt in range(DOWNLOAD_ATTEMPTS):
        try:
            with urllib.request.urlopen(
                request, timeout=HTTP_TIMEOUT
            ) as response:
                return response.read()
        except (OSError, urllib.error.URLError,
                http.client.IncompleteRead) as error:
            last_error = error
            if attempt + 1 < DOWNLOAD_ATTEMPTS:
                time.sleep(RETRY_DELAY)
    raise ValueError(
        f"Не удалось скачать данные: {url} ({last_error})"
    ) from last_error


def resource_types(resource: dict[str, Any]) -> list[str]:
    """Нормализовать тип ресурса индекса NuGet."""
    value = resource.get("@type", [])
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def package_base_address(repository_url: str) -> str:
    """Найти базовый URL пакетов в индексе NuGet V3."""
    try:
        index = json.loads(download_bytes(repository_url))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("Некорректный индекс NuGet") from error
    for resource in index.get("resources", []):
        if PACKAGE_BASE_TYPE in resource_types(resource):
            return resource["@id"].rstrip("/")
    raise ValueError("В индексе NuGet не найдено хранилище пакетов")


def package_url(base_url: str, package_name: str, version: str) -> str:
    """Сформировать URL .nupkg для заданного пакета."""
    package_id = urllib.parse.quote(package_name.lower(), safe=".-")
    package_version = urllib.parse.quote(version.lower(), safe=".-")
    filename = f"{package_id}.{package_version}{NUPKG_SUFFIX}"
    return f"{base_url}/{package_id}/{package_version}/{filename}"


def local_name(tag: str) -> str:
    """Вернуть XML-имя без пространства имён."""
    return tag.rsplit("}", 1)[-1]


def dependency_entries(container: ElementTree.Element) \
        -> list[tuple[str, str]]:
    """Извлечь зависимости из элемента или целевых групп."""
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
    """Разобрать прямые зависимости XML-файла nuspec."""
    try:
        root = ElementTree.fromstring(contents)
    except ElementTree.ParseError as error:
        raise ValueError("Некорректный XML-файл nuspec") from error
    metadata = next((element for element in root.iter()
                     if local_name(element.tag) == "metadata"), None)
    if metadata is None:
        raise ValueError("В nuspec не найден элемент metadata")
    dependencies = next((element for element in metadata
                         if local_name(element.tag) == "dependencies"), None)
    return dependency_entries(dependencies) if dependencies is not None else []


def nuspec_contents(package_data: bytes) -> bytes:
    """Открыть ZIP-пакет и прочитать файл nuspec."""
    try:
        with zipfile.ZipFile(BytesIO(package_data)) as archive:
            nuspec_path = next((name for name in archive.namelist()
                                if name.lower().endswith(NUSPEC_SUFFIX)), None)
            if nuspec_path is None:
                raise ValueError("В .nupkg не найден файл .nuspec")
            return archive.read(nuspec_path)
    except zipfile.BadZipFile as error:
        raise ValueError("Скачанный пакет не является ZIP-архивом") from error


def exact_version(spec: str) -> str | None:
    """Вернуть версию из точного диапазона вида [1.2.3]."""
    if spec.startswith("[") and spec.endswith("]") and "," not in spec:
        version = spec[1:-1].strip()
        if VERSION_PART.fullmatch(version):
            return version
    return None


def ranged_version(spec: str) -> str:
    """Выбрать включённую границу NuGet version range."""
    match = VERSION_RANGE.fullmatch(spec)
    if match is None:
        raise ValueError(f"Некорректный диапазон версий: {spec}")
    left_mark, lower, upper, right_mark = match.groups()
    if lower and left_mark == "[" and VERSION_PART.fullmatch(lower):
        return lower
    if upper and right_mark == "]" and VERSION_PART.fullmatch(upper):
        return upper
    raise ValueError(f"Нет конкретной включённой границы: {spec}")


def select_version(version_spec: str) -> str:
    """Выбрать конкретную версию, входящую в заданный диапазон."""
    spec = version_spec.strip()
    if VERSION_PART.fullmatch(spec):
        return spec
    exact = exact_version(spec)
    if exact is not None:
        return exact
    return ranged_version(spec)


def get_direct_dependencies(
    package_name: str, version: str, repository_url: str,
) -> list[tuple[str, str]]:
    """Скачать пакет и вернуть зависимости из его nuspec."""
    base_url = package_base_address(repository_url)
    data = download_bytes(package_url(base_url, package_name, version))
    return parse_nuspec(nuspec_contents(data))


def get_transitive_dependencies(
    package_name: str, version: str, repository_url: str,
) -> list[tuple[str, str]]:
    """Получить зависимости и выбрать версии для рекурсивного обхода."""
    dependencies = get_direct_dependencies(
        package_name, version, repository_url)
    return [(name, select_version(spec)) for name, spec in dependencies]


def get_dependency_details(
    package_name: str, version: str, repository_url: str,
) -> list[tuple[str, str, str]]:
    """Вернуть имя, выбранную версию и исходное условие из nuspec."""
    dependencies = get_direct_dependencies(
        package_name, version, repository_url)
    return [
        (name, select_version(spec), spec)
        for name, spec in dependencies
    ]
