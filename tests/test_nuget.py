"""Проверить скачивание и ручной разбор NuGet-пакетов."""

import io
import json
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nuget import get_direct_dependencies, parse_nuspec


REPOSITORY_URL = "https://api.nuget.org/v3/index.json"
INDEX_CONTENT = json.dumps(
    {
        "resources": [
            {
                "@id": "https://api.nuget.org/v3-flatcontainer/",
                "@type": "PackageBaseAddress/3.0.0",
            }
        ]
    }
).encode("utf-8")
NUSPEC_CONTENT = b"""<?xml version="1.0"?>
<package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd">
  <metadata>
    <id>Example.Package</id>
    <version>1.2.3</version>
    <dependencies>
      <group targetFramework="net8.0">
        <dependency id="Direct.One" version="[2.0, )" />
      </group>
      <group targetFramework="netstandard2.0">
        <dependency id="Direct.Two" version="4.5.6" />
      </group>
    </dependencies>
  </metadata>
</package>
"""


def make_nupkg() -> bytes:
    """Создать минимальный ZIP-пакет с тестовым nuspec."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("Example.Package.nuspec", NUSPEC_CONTENT)
    return buffer.getvalue()


class NugetTests(unittest.TestCase):
    """Проверить прямые зависимости без обращения к интернету."""

    def test_parse_nuspec_reads_only_direct_dependencies(self) -> None:
        """Не извлекать транзитивные зависимости из nuspec."""
        dependencies = parse_nuspec(NUSPEC_CONTENT)
        self.assertEqual(
            dependencies,
            [("Direct.One", "[2.0, )"), ("Direct.Two", "4.5.6")],
        )

    def test_downloads_requested_version_from_nuget_feed(self) -> None:
        """Получить заданную версию через индекс и URL NuGet."""
        responses = [io.BytesIO(INDEX_CONTENT), io.BytesIO(make_nupkg())]
        with patch(
            "nuget.urllib.request.urlopen", side_effect=responses
        ) as open_url:
            dependencies = get_direct_dependencies(
                "Example.Package", "1.2.3", REPOSITORY_URL
            )
        self.assertEqual(len(dependencies), 2)
        request = open_url.call_args_list[1].args[0]
        self.assertEqual(
            request.full_url,
            "https://api.nuget.org/v3-flatcontainer/"
            "example.package/1.2.3/example.package.1.2.3.nupkg",
        )

    def test_rejects_package_without_nuspec(self) -> None:
        """Сообщить об архиве без файла метаданных."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as package:
            package.writestr("readme.txt", "no nuspec")
        responses = [io.BytesIO(INDEX_CONTENT), io.BytesIO(buffer.getvalue())]
        with patch("nuget.urllib.request.urlopen", side_effect=responses):
            with self.assertRaisesRegex(ValueError, "не найден файл .nuspec"):
                get_direct_dependencies(
                    "Example.Package", "1.2.3", REPOSITORY_URL
                )


if __name__ == "__main__":
    unittest.main()
