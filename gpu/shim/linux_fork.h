// SPDX-License-Identifier: GPL-2.0-or-later
// Linux fork: switches shared by the shader recompiler and the shader cache.
#pragma once

#include <cstdlib>

namespace LinuxFork {

/// Colour outputs to float render targets: NaN becomes 0, so one bad pixel cannot grow into a
/// black 16x16 block through the games' tiled post-processing (Uncharted 2 on the Steam Deck).
/// BB_NAN_GUARD: 1 (default) NaN only, 2 also clamps +-Inf to the half-float range (that broke
/// Uncharted 1's lighting and fog: blue trees), 0 off.
inline int NanGuardMode() {
    static const int mode = [] {
        const char* env = std::getenv("BB_NAN_GUARD");
        return env && (env[0] == '0' || env[0] == '2') ? env[0] - '0' : 1;
    }();
    return mode;
}

inline bool ExportNanGuard() {
    return NanGuardMode() != 0;
}

/// VK_EXT_vertex_input_dynamic_state: BB_VERTEX_INPUT_DS=0 turns it off, =1 forces it on; by
/// default it is off only where it is known to break (`broken_driver`).
inline bool VertexInputDynamicStateAllowed(bool broken_driver) {
    const char* env = std::getenv("BB_VERTEX_INPUT_DS");
    if (env && (env[0] == '0' || env[0] == '1')) {
        return env[0] == '1';
    }
    return !broken_driver;
}

/// Shaders compiled in each mode are cached apart.
inline const char* ShaderCacheSuffix() {
    return NanGuardMode() == 1 ? "-nan1" : NanGuardMode() == 2 ? "-nan2" : "";
}

} // namespace LinuxFork
