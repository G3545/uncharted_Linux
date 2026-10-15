# Uncharted: The Nathan Drake Collection for Linux/Steam Deck
**WORK IN PROGRESS: GAMES HAVE NOT BEEN CONFIRMED TO BE FULLY PLAYABLE. DISTRIBUTIONS TESTED: SteamOS 3.7, Fedora 44**


Join the Discord: https://discord.gg/X2YhSJg6R2

**Uncharted 1, 2 and 3 from the PS4 collection running natively on Linux, forked by spacepepperoni from [SuperMedo](https://github.com/Supermedo).**

Status: Early, expect minor graphical issues and some crashes. Steam Deck running at stable 28-30fps by using Steam Deck mode. 

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/spacepepperoni/uncharted_Linux/main/install.sh | sh
```

## Uninstall

```sh
curl -fsSL https://raw.githubusercontent.com/spacepepperoni/uncharted_Linux/main/install.sh | sh -s -- --uninstall
```

## Appimage
1. Download **[Uncharted-x86_64.AppImage](https://github.com/spacepepperoni/uncharted_Linux/releases/latest/download/Uncharted-x86_64.AppImage)**.
2. Right-click it, open **Properties → Permissions** and tick **Is executable** (or
   **Allow executing file as program**).
3. Double-click it.

## How to Play 

You must have an unencrypted extracted dump of the Uncharted: The Nathan Drake Collection (CUSA02320) v1.00.

Point the launcher to this folder in the Game tab. By default, a new Saves folder will appear.

Once your game folder has been specified, you're ready to play either by clicking Play, Add to Steam (recommended for Steam Deck) or create a Desktop shortcut.

> **No game files are included.** You need your own decrypted dump of the collection
> (CUSA02343, CUSA02320, ...: the folder with eboot.bin, big2-ps4_Shipping.elf,
> big3-ps4_Shipping.elf, sce_sys, u1data, u2data and u3data).
> This project is not affiliated with Sony Interactive Entertainment or Naughty Dog.

## Steam Deck

- In the Display tab, a Steam Deck mode is auto-selected if you are on SteamOS. With this enabled, expect an average of 25-30fps with occasional dips during demanding segments.
- It is recommended to set your FPS cap to 30fps on the Steam Deck power menu.


## Requirements

- 64-bit x86 Linux with glibc 2.41 or newer: SteamOS 3.7+, Debian 13, Ubuntu 25.04, Fedora 42,
  Arch, or anything newer.
- A graphics card with Vulkan 1.3 and a current driver, with **6 GB of video memory or more**.
  4 GB cards (GTX 1650, RX 570) run out of video memory and crash after a while; on those, keep
  Anti-aliasing and Frame generation off. (The Steam Deck shares its memory and is fine.)
- About 8 GB of free memory (RAM + page file).

## Known problems

- **Uncharted 3, Cartagena square (chapter 2):** at high frame rates (240 Hz setting, ~80 FPS)
  the game could freeze and close with "GPU crash: the graphics device was lost". It came from
  the speed fix for that area and is fixed in 0.3. If it still happens to you, set Frame rate to
  60 on the Display page and open an issue with your `user/last_run.log`.
- **Uncharted 3:** green or black shapes flash for a single frame on some characters (Sully's
  shirt in Cartagena). It happens in shadPS4 too, so it's a shader translation problem. Not fixed yet.
- **Crash with "ASSERTION: GetRenderFrameParams(frameToFreeInstancesFor)->m_gfxEopTick"**
  (mostly U1 after the first cutscene): the game expected the GPU side to be done with a frame it
  wanted to reuse, and stopped when it wasn't yet (shaders building on a first run). Fixed in
  0.3.2: the game now waits for it. If you still see it, open an issue with your log.
- **Intel HD / UHD graphics:** a black screen on the HD 630 is fixed in 0.3.3. Older Intel chips
  (HD 520) can still crash inside Intel's own driver.
- **Uncharted 2 streaming crash** (`iSubMesh < m_numSubMeshInstances`, white textures first) and the
  **Uncharted 3 London bar crash** (fault at `0xd9c59b`): both seen on the US version 1.02
  (CUSA02320). Being looked at.
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
