# Uncharted: The Nathan Drake Collection for Linux/Steam Deck

**Uncharted 1, 2 and 3 from the PS4 collection running natively on Linux, forked by spacepepperoni from [SuperMedo](https://github.com/Supermedo).** Mohammed Albarghouthi

Same idea as my [Bloodborne port](https://github.com/Supermedo/bloodborne_pc): the original PS4 game
code runs directly on your PC and the graphics are translated to Vulkan. Install it with one
command, pick your game folder and press **Play** next to the game you want.

This fork builds SuperMedo's Windows port for Linux and the Steam Deck. It picks up new upstream
versions automatically (see [Staying up to date](#staying-up-to-date)). Status: early, so expect
problems.

## Install

Run this in a terminal. It's the same command on every Linux distribution and on the Steam Deck
(in Desktop Mode, using **Konsole**):

```sh
curl -fsSL https://raw.githubusercontent.com/spacepepperoni/uncharted_Linux/main/install.sh | sh
```

It puts `Uncharted-x86_64.AppImage` in `~/Applications` and adds **Uncharted** to the
application menu and the desktop. Run it again to update. To remove it, run
`curl -fsSL https://raw.githubusercontent.com/spacepepperoni/uncharted_Linux/main/install.sh | sh -s -- --uninstall`.
Saves and settings live in `~/.local/share/uncharted-linux` and are kept either way.

**Prefer not to use a terminal?**
1. Download **[Uncharted-x86_64.AppImage](https://github.com/spacepepperoni/uncharted_Linux/releases/latest/download/Uncharted-x86_64.AppImage)**.
2. Right-click it, open **Properties → Permissions** and tick **Is executable** (or
   **Allow executing file as program**).
3. Double-click it.

**First start:** choose your game folder on the **Game** page, then press **Play** next to a game.

**Steam Deck:** press **Add to Steam** instead. Steam restarts, and Uncharted 1, 2 and 3 appear
in your library as separate Non-Steam games. Go back to Gaming Mode and play them from there.
They use the settings saved in the launcher.

**Your game files:** copy the dump folder to the Deck or PC, for example `~/Games/CUSA02343`.
A microSD card works too (`/run/media/deck/<card>/...`).

Suggested Steam Deck settings: Frame rate **60**, Anti-aliasing **Off** or **AMD FSR 3.1**,
Frame generation **Off**.

> **No game files are included.** You need your own decrypted dump of the collection
> (CUSA02343, CUSA02320, ...: the folder with eboot.bin, big2-ps4_Shipping.elf,
> big3-ps4_Shipping.elf, sce_sys, u1data, u2data and u3data).
> This project is not affiliated with Sony Interactive Entertainment or Naughty Dog.

## Features

- All three games from one launcher: Drake's Fortune, Among Thieves and Drake's Deception.
- 60 FPS like on PS4, or 120 FPS (higher rates are experimental).
- Anti-aliasing with TAA or AMD FSR 3.1. (NVIDIA DLSS and AMD FSR 4 are in the Windows version only.)
- Frame generation: AMD FSR 3 (any GPU).
- Keyboard, mouse and controller together, all remappable. Mouse look in U3.
- Add to Steam (one entry per game) and desktop shortcuts from the launcher, and an update notice.

## Requirements

- 64-bit x86 Linux with glibc 2.41 or newer: SteamOS 3.7+, Debian 13, Ubuntu 25.04, Fedora 42,
  Arch, or anything newer.
- A graphics card with Vulkan 1.3 and a current driver.
- About 8 GB of free memory (RAM + page file).

## Known problems

- **Uncharted 3, Cartagena square (chapter 2):** at high frame rates (240 Hz setting, ~80 FPS)
  the game could freeze and close with "GPU crash: the graphics device was lost". It came from
  the speed fix for that area and is fixed in 0.3. If it still happens to you, set Frame rate to
  60 on the Display page and open an issue with your `user/last_run.log`.
- **Uncharted 3:** green or black shapes flash for a single frame on some characters (Sully's
  shirt in Cartagena). It happens in shadPS4 too, so it's a shader translation problem. Not fixed yet.
- **Crash with "ASSERTION: GetRenderFrameParams(frameToFreeInstancesFor)->m_gfxEopTick":** the
  game got too many frames ahead of the GPU side while it was busy (building shaders on a first
  run). 0.3.1 holds the game at most one frame ahead, like on PS4. If you still see it, open an
  issue with your log.
- Frame rates above 120 are experimental.

## Building from source

On Debian 13 or Ubuntu 25.04 (other distributions need the same packages under their own names):

```sh
sudo apt install build-essential cmake ninja-build pkgconf curl python3 python3-venv python3-tk \
  libsdl3-dev libvulkan-dev libfmt-dev libboost-dev robin-map-dev libvulkan-memory-allocator-dev \
  libxxhash-dev libx11-dev libzydis-dev libavformat-dev libavcodec-dev libavutil-dev \
  libswscale-dev libswresample-dev libprotobuf-dev protobuf-compiler nlohmann-json3-dev \
  libssl-dev zlib1g-dev libminiupnpc-dev glslang-tools spirv-headers
git clone --recursive https://github.com/spacepepperoni/uncharted_Linux
cd uncharted_Linux
bash build.sh                      # BB_JOBS=4 limits parallel jobs; BB_LTO=OFF builds faster
python3 launcher/uncharted_launcher.py
bash packaging/linux/package.sh    # optional: the AppImage and the tarball in dist/
```

## Staying up to date

- [`sync-upstream.yml`](.github/workflows/sync-upstream.yml) runs every six hours. You can also
  start it from the Actions tab. It merges
  [Supermedo/uncharted_pc](https://github.com/Supermedo/uncharted_pc) into `main`, and
  [`build.yml`](.github/workflows/build.yml) then publishes a new release.
- The branch `upstream` is an exact copy of SuperMedo's `main`.
- This README is the fork's own: when upstream changes theirs, this one is kept.
- If any other file conflicts, the workflow opens a pull request from `upstream` instead.
  Resolve the conflicts there and merge it.
- The Linux changes to upstream files are small and marked `Linux fork`. Most of the Linux code
  is in its own files (`launcher/uncharted_linux.py`, `packaging/linux/`, `install.sh`,
  `.github/`), so conflicts should be rare.

## Credits

Built on [bbport](https://github.com/deadinside28/bloodborne_pc), the native Linux port of
Bloodborne by deadinside28, and on the [shadPS4](https://github.com/shadps4-emu/shadPS4)
renderer. Video decoding (Videodec2) and the DLSS bridge come from
[IFreemz/shadPS4-Bloodborne-DLSS-FSR](https://github.com/IFreemz/shadPS4-Bloodborne-DLSS-FSR).
Thanks to Mindro for the shadPS4 Uncharted build that showed which problems to look for.

Also used: [FSR-Vulkan](https://github.com/FireBurn/FSR-Vulkan) and the AMD FidelityFX SDK (FSR),
FSR 4 assets from [FireBurn/Q2RTX](https://github.com/FireBurn/Q2RTX), the
[NVIDIA DLSS SDK](https://github.com/NVIDIA/DLSS) (`nvngx_dlss.dll` under NVIDIA's license),
[LibAtrac9](https://github.com/Thealexbarney/LibAtrac9), [SDL3](https://github.com/libsdl-org/SDL),
[FFmpeg](https://ffmpeg.org), [Dear ImGui](https://github.com/ocornut/imgui),
[sirit](https://github.com/shadps4-emu/sirit), [magic_enum](https://github.com/Neargye/magic_enum),
[xbyak](https://github.com/herumi/xbyak),
[Vulkan Memory Allocator](https://github.com/GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator),
[MSYS2](https://www.msys2.org) / [LLVM](https://llvm.org), [PyInstaller](https://pyinstaller.org),
[Pillow](https://python-pillow.org) and the Cinzel font (SIL Open Font License).

NVIDIA, GeForce RTX and DLSS are trademarks of NVIDIA Corporation.

## License

GNU GPL v2 or later ([LICENSE](LICENSE)). Third-party components keep their own licenses
(see `licenses/` in the download).
