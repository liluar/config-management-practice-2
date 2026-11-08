"""Проверить ручной разбор NuGet-пакетов без сетевого доступа."""

import io
import json
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nuget import (get_direct_dependencies, get_transitive_dependencies,
                   parse_nuspec, select_version)

REPOSITORY_URL = "https://api.nuget.org/v3/index.json"
INDEX_CONTENT = json.dumps({"resources": [{
    "@id": "https://api.nuget.org/v3-flatcontainer/",
    "@type": "PackageBaseAddress/3.0.0"}]}).encode("utf-8")
NUSPEC_CONTENT = b'''<?xml version="1.0"?>
<package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd">
  <metadata><id>Example.Package</id><version>1.2.3</version>
    <dependencies><group targetFramework="net8.0">
      <dependency id="Direct.One" version="[2.0, )" />
    </group><group targetFramework="netstandard2.0">
      <dependency id="Direct.Two" version="4.5.6" />
    </group></dependencies>
  </metadata>
</package>
'''


def make_nupkg() -> bytes:
    """Создать ZIP-пакет с тестовым nuspec."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("Example.Package.nuspec", NUSPEC_CONTENT)
    return buffer.getvalue()


class NugetTests(unittest.TestCase):
    """Проверить парсинг и мокнутую загрузку NuGet."""

    def test_parse_direct_dependencies(self) -> None:
        """Прочитать прямые зависимости из всех групп."""
        self.assertEqual(parse_nuspec(NUSPEC_CONTENT), [
            ("Direct.One", "[2.0, )"), ("Direct.Two", "4.5.6")])

    def test_downloads_requested_version(self) -> None:
        """Скачать версию по URL, полученному из индекса."""
        responses = [io.BytesIO(INDEX_CONTENT), io.BytesIO(make_nupkg())]
        with patch(
            "nuget.urllib.request.urlopen", side_effect=responses
        ) as opened:
            deps = get_direct_dependencies(
                "Example.Package", "1.2.3", REPOSITORY_URL)
        self.assertEqual(len(deps), 2)
        request = opened.call_args_list[1].args[0]
        self.assertTrue(request.full_url.endswith(
            "example.package/1.2.3/example.package.1.2.3.nupkg"))

    def test_rejects_missing_nuspec(self) -> None:
        """Отклонить ZIP без nuspec."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as package:
            package.writestr("readme.txt", "no nuspec")
        responses = [io.BytesIO(INDEX_CONTENT), io.BytesIO(buffer.getvalue())]
        with patch("nuget.urllib.request.urlopen", side_effect=responses):
            with self.assertRaisesRegex(ValueError, "не найден файл .nuspec"):
                get_direct_dependencies("Example.Package", "1.2.3",
                                        REPOSITORY_URL)

    def test_version_range(self) -> None:
        """Выбрать первую конкретную версию из диапазона."""
        self.assertEqual(select_version("[2.4.0, 3.0.0)"), "2.4.0")
        self.assertEqual(select_version("4.5.6"), "4.5.6")

    def test_transitive_provider_selects_concrete_versions(self) -> None:
        """Передать обходу конкретную версию вместо диапазона."""
        with patch("nuget.get_direct_dependencies", return_value=[
            ("Child", "[2.4.0, 3.0.0)")
        ]):
            result = get_transitive_dependencies("Root", "1.0.0", "feed")
        self.assertEqual(result, [("Child", "2.4.0")])

    def test_unresolvable_version(self) -> None:
        """Отклонить диапазон без конкретной версии."""
        with self.assertRaisesRegex(ValueError, "Не удалось выбрать"):
            select_version("*")


if __name__ == "__main__":
    unittest.main()
