#!/usr/bin/env bash
# Linux fork: builds dist/uncharted-linux.tar.gz after `bash build.sh`. Uncharted is the
# launcher (frozen with PyInstaller, so no Python is needed), bin/ holds bb-probe, its GPU library
# and the libraries a Steam Deck or another distribution may lack (bin/lib), the preparation
# scripts and run.py. Graphics-driver, glibc and libstdc++ libraries come from the system.
# LINUX_BUILD (e.g. 0.3.1-linux.4) is written into the package for the launcher's update check.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
[[ -f out/bb-probe && -f out/gpu/libbbgpu.so && -f out/bb-gpu-capabilities ]] || { echo 'Build first: bash build.sh' >&2; exit 1; }

python=${PYTHON:-python3}
if [[ ! -x out/pyenv/bin/python ]]; then
    "$python" -m venv out/pyenv
fi
out/pyenv/bin/python -m pip install -q --disable-pip-version-check pyinstaller pillow
[[ -f launcher/uncharted.png ]] || out/pyenv/bin/python - <<'EOF'
from PIL import Image
icon = Image.open('launcher/uncharted.ico')
icon.size = max(icon.ico.sizes())
icon.convert('RGBA').save('launcher/uncharted.png')
EOF
hidden=()
for module in argparse base64 collections hashlib json re shlex shutil struct tempfile zlib \
              uncharted_art uncharted_fonts uncharted_widgets uncharted_linux bbport_steam PIL.ImageTk PIL._tkinter_finder; do
    hidden+=(--hidden-import "$module")
done
out/pyenv/bin/python -m PyInstaller --noconfirm --clean --log-level WARN --windowed \
    --name Uncharted --distpath out/pyi-dist --workpath out/pyi-work --specpath out/pyi-work \
    --paths "$PWD/scripts" --paths "$PWD/launcher" \
    --add-data "$PWD/launcher/fonts:fonts" --add-data "$PWD/launcher/covers:covers" \
    --add-data "$PWD/launcher/uncharted.png:." \
    "${hidden[@]}" launcher/uncharted_launcher.py

dest=out/stage/uncharted-linux
rm -rf -- out/stage
mkdir -p "$dest/bin/gpu" "$dest/bin/lib" "$dest/launcher" "$dest/scripts" "$dest/licenses"
cp -r out/pyi-dist/Uncharted/. "$dest/"
strip --strip-debug -o "$dest/bin/bb-probe" out/bb-probe
strip --strip-debug -o "$dest/bin/bb-gpu-capabilities" out/bb-gpu-capabilities
strip --strip-debug -o "$dest/bin/gpu/libbbgpu.so" out/gpu/libbbgpu.so
# Libraries every desktop and SteamOS have (or that must match the graphics driver) stay out.
system='^(ld-linux|libc|libm|libdl|libpthread|librt|libresolv|libutil|libgcc_s|libstdc\+\+|libvulkan|libX|libxcb|libxkb|libwayland|libdrm|libGL|libEGL|libgbm|libasound|libpulse|libpipewire|libdbus|libudev|libsystemd|libz|libzstd|libexpat|libelf|libLLVM|libffi|libcap|libgcrypt|libgpg-error|liblzma|libmount|libblkid|libglib|libgobject|libgio|libgmodule|libpcre2|libdecor|libxshmfence|libsensors)[.-]'
ldd out/bb-probe out/gpu/libbbgpu.so out/bb-gpu-capabilities | awk '/=> \// {print $1, $3}' | sort -u |
    while read -r name path; do
        [[ $name =~ $system ]] || cp -L "$path" "$dest/bin/lib/$name"
    done
cp scripts/prepare.py scripts/link_modules.py scripts/link_libc.py scripts/content_profile.py "$dest/scripts/"
cp run.py LICENSE "$dest/"
cp launcher/uncharted.png "$dest/launcher/"
cp README.md "$dest/README.md"
echo "${LINUX_BUILD:-}" > "$dest/LINUX_BUILD"
for license in gpu/third_party/httplib/LICENSE:cpp-httplib launcher/fonts/OFL.txt:Cinzel; do
    if [[ -f ${license%%:*} ]]; then cp "${license%%:*}" "$dest/licenses/${license##*:}-LICENSE.txt"; fi
done
# The bundled libraries' own copyright files (Debian keeps them per package).
for library in "$dest"/bin/lib/*; do
    package=$(dpkg -S "$(readlink -f "/usr/lib/x86_64-linux-gnu/$(basename "$library")" 2>/dev/null || echo none)" 2>/dev/null | cut -d: -f1 | head -1 || true)
    if [[ -n $package && -f /usr/share/doc/$package/copyright ]]; then
        cp "/usr/share/doc/$package/copyright" "$dest/licenses/$package-copyright.txt"
    fi
done
find "$dest" -name __pycache__ -prune -exec rm -r {} +
mkdir -p dist
tar -C out/stage -czf dist/uncharted-linux.tar.gz uncharted-linux

# The AppImage: the same files in one executable. Saves, settings and generated files go to
# ~/.local/share/uncharted-linux, since the AppImage itself is read-only.
appdir=out/stage/Uncharted.AppDir
cp -a "$dest" "$appdir"
cp packaging/linux/AppRun "$appdir/AppRun"
chmod +x "$appdir/AppRun"
cp packaging/linux/uncharted-linux.desktop "$appdir/"
cp launcher/uncharted.png "$appdir/uncharted-linux.png"
cp launcher/uncharted.png "$appdir/.DirIcon"
tool=out/appimagetool-1.9.1
if [[ ! -x $tool ]]; then
    curl -fsSL -o "$tool" https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage
    chmod +x "$tool"
fi
# Extract-and-run: works without FUSE (containers, CI).
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$tool" --no-appstream "$appdir" dist/Uncharted-x86_64.AppImage >/dev/null
ls -lh dist/uncharted-linux.tar.gz dist/Uncharted-x86_64.AppImage
