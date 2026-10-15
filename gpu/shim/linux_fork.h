// SPDX-License-Identifier: GPL-2.0-or-later
// Linux fork: switches shared by the shader recompiler and the shader cache.
#pragma once

#include <cstdlib>

namespace LinuxFork {

/// Colour outputs to float render targets: NaN becomes 0 and +-Inf the largest half-float value,
/// so one bad pixel cannot grow into a black 16x16 block through the games' tiled post-processing
/// (Uncharted 2 on the Steam Deck). On by default; BB_NAN_GUARD=0 turns it off.
inline bool ExportNanGuard() {
    static const bool enabled = [] {
        const char* env = std::getenv("BB_NAN_GUARD");
        return !(env && env[0] == '0');
    }();
    return enabled;
}

/// Shaders compiled with and without the guard are cached apart.
inline const char* ShaderCacheSuffix() {
    return ExportNanGuard() ? "-nanguard" : "";
}

} // namespace LinuxFork
