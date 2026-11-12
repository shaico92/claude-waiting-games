#!/usr/bin/env python3
"""Build waiting-games-vscode.vsix with the standard library (no node, no vsce).
  python3 vscode/build_vsix.py [out.vsix]
A .vsix is a zip: [Content_Types].xml + extension.vsixmanifest + extension/<files>."""
import json, os, sys, zipfile
from xml.sax.saxutils import escape, quoteattr

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ("package.json", "extension.js", "README.md")

CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension=".json" ContentType="application/json"/>
  <Default Extension=".js" ContentType="application/javascript"/>
  <Default Extension=".md" ContentType="text/markdown"/>
  <Default Extension=".vsixmanifest" ContentType="text/xml"/>
</Types>
"""

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id=%(id)s Version=%(version)s Publisher=%(publisher)s/>
    <DisplayName>%(display)s</DisplayName>
    <Description xml:space="preserve">%(description)s</Description>
    <Categories>Other</Categories>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value=%(engine)s/>
    </Properties>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/>
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true"/>
  </Assets>
</PackageManifest>
"""


def extension_id():
    with open(os.path.join(HERE, "package.json"), encoding="utf-8") as f:
        pkg = json.load(f)
    return "%s.%s" % (pkg["publisher"], pkg["name"])


def build(out):
    with open(os.path.join(HERE, "package.json"), encoding="utf-8") as f:
        pkg = json.load(f)
    manifest = MANIFEST % dict(
        id=quoteattr(pkg["name"]), version=quoteattr(pkg["version"]), publisher=quoteattr(pkg["publisher"]),
        display=escape(pkg["displayName"]), description=escape(pkg["description"]),
        engine=quoteattr(pkg["engines"]["vscode"]))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("extension.vsixmanifest", manifest)
        for name in FILES:
            z.write(os.path.join(HERE, name), "extension/" + name)
    return out


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "waiting-games-vscode.vsix")))
