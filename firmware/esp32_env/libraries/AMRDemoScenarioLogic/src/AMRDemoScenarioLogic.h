#pragma once

#include <stdint.h>

constexpr int GAS_BASELINE_MIN_RAW = 1000;
constexpr int GAS_STRONG_RAW_THRESHOLD = 500;
constexpr uint8_t GAS_WEAK_BASELINE_PERCENT = 70;
constexpr uint16_t GAS_STRONG_REQUIRED_SAMPLES = 6;
constexpr uint16_t GAS_WEAK_REQUIRED_SAMPLES = 30;
constexpr uint16_t GAS_MIN_REQUIRED_SAMPLES = 480;
constexpr uint32_t GAS_INSPECTION_DURATION_MS = 3000;
constexpr uint32_t DEMO_GAS_EVENT_HOLD_MS = 5000;
constexpr uint8_t DEMO_FLAME_DETECT_SAMPLES = 3;
constexpr uint32_t DEMO_FLAME_HOLD_MS = 5000;

enum GasInspectionZone : uint8_t {
  GAS_ZONE_NONE,
  GAS_ZONE_P1,
  GAS_ZONE_P2
};

enum GasInspectionResult : uint8_t {
  GAS_RESULT_PENDING,
  GAS_RESULT_CLEAR,
  GAS_RESULT_DETECTED,
  GAS_RESULT_ERROR
};

struct GasInspectionState {
  int baseline = 0;
  bool baselineReady = false;
  bool sampling = false;
  GasInspectionZone activeZone = GAS_ZONE_NONE;
  uint32_t startMs = 0;
  int frozenBaseline = 0;
  int minimumRaw = 4095;
  uint16_t strongSamples = 0;
  uint16_t weakSamples = 0;
  uint16_t totalSamples = 0;
  bool resultReady = false;
  GasInspectionZone resultZone = GAS_ZONE_NONE;
  GasInspectionResult result = GAS_RESULT_PENDING;
  bool gasEventActive = false;
  uint32_t gasEventStartMs = 0;
};

struct FlameLatchState {
  uint8_t consecutiveDetected = 0;
  bool active = false;
  uint32_t lastDetectedMs = 0;
};

constexpr bool gasTextEquals(const char* left, const char* right) {
  while (*left != '\0' && *right != '\0') {
    if (*left != *right) {
      return false;
    }
    ++left;
    ++right;
  }
  return *left == *right;
}

constexpr GasInspectionZone gasInspectionZoneForPayload(const char* payload) {
  if (gasTextEquals(payload, "CMD,GAS_CHECK,P1")) {
    return GAS_ZONE_P1;
  }
  if (gasTextEquals(payload, "CMD,GAS_CHECK,P2")) {
    return GAS_ZONE_P2;
  }
  return GAS_ZONE_NONE;
}

constexpr GasInspectionState startGasInspection(
  GasInspectionState state,
  GasInspectionZone zone,
  uint32_t now
) {
  if (state.sampling || state.resultReady || zone == GAS_ZONE_NONE) {
    return state;
  }

  state.resultZone = zone;
  state.result = GAS_RESULT_PENDING;
  state.frozenBaseline = state.baseline;
  state.minimumRaw = 4095;
  state.strongSamples = 0;
  state.weakSamples = 0;
  state.totalSamples = 0;

  if (!state.baselineReady || state.baseline < GAS_BASELINE_MIN_RAW) {
    state.result = GAS_RESULT_ERROR;
    state.resultReady = true;
    return state;
  }

  state.sampling = true;
  state.activeZone = zone;
  state.startMs = now;
  return state;
}

constexpr GasInspectionState updateGasInspection(
  GasInspectionState state,
  int gasRaw,
  uint32_t now
) {
  if (
    state.gasEventActive &&
    (uint32_t)(now - state.gasEventStartMs) >= DEMO_GAS_EVENT_HOLD_MS
  ) {
    state.gasEventActive = false;
  }

  if (!state.sampling) {
    if (gasRaw >= GAS_BASELINE_MIN_RAW) {
      if (!state.baselineReady) {
        state.baseline = gasRaw;
        state.baselineReady = true;
      } else {
        state.baseline = (int)(((int32_t)state.baseline * 31 + gasRaw) / 32);
      }
    }
    return state;
  }

  if (state.totalSamples < UINT16_MAX) {
    state.totalSamples++;
  }
  if (gasRaw < state.minimumRaw) {
    state.minimumRaw = gasRaw;
  }
  if (
    gasRaw < GAS_STRONG_RAW_THRESHOLD &&
    state.strongSamples < UINT16_MAX
  ) {
    state.strongSamples++;
  }
  int weakThreshold = (
    (int32_t)state.frozenBaseline * GAS_WEAK_BASELINE_PERCENT / 100
  );
  if (gasRaw < weakThreshold && state.weakSamples < UINT16_MAX) {
    state.weakSamples++;
  }

  if ((uint32_t)(now - state.startMs) < GAS_INSPECTION_DURATION_MS) {
    return state;
  }

  state.sampling = false;
  state.activeZone = GAS_ZONE_NONE;
  state.resultReady = true;

  if (state.totalSamples < GAS_MIN_REQUIRED_SAMPLES) {
    state.result = GAS_RESULT_ERROR;
  } else if (
    state.strongSamples >= GAS_STRONG_REQUIRED_SAMPLES ||
    state.weakSamples >= GAS_WEAK_REQUIRED_SAMPLES
  ) {
    state.result = GAS_RESULT_DETECTED;
    state.gasEventActive = true;
    state.gasEventStartMs = now;
  } else {
    state.result = GAS_RESULT_CLEAR;
  }

  return state;
}

constexpr GasInspectionState clearGasInspectionResult(
  GasInspectionState state
) {
  state.resultReady = false;
  state.resultZone = GAS_ZONE_NONE;
  state.result = GAS_RESULT_PENDING;
  return state;
}

inline FlameLatchState updateFlameLatch(
  FlameLatchState state,
  bool rawDetected,
  uint32_t now
) {
  if (rawDetected) {
    if (state.consecutiveDetected < DEMO_FLAME_DETECT_SAMPLES) {
      state.consecutiveDetected++;
    }
    if (state.consecutiveDetected >= DEMO_FLAME_DETECT_SAMPLES) {
      state.active = true;
      state.lastDetectedMs = now;
    }
    return state;
  }

  state.consecutiveDetected = 0;
  if (state.active && (uint32_t)(now - state.lastDetectedMs) >= DEMO_FLAME_HOLD_MS) {
    state.active = false;
  }
  return state;
}

inline bool demoBuzzerShouldSound(bool flameDetected) {
  return flameDetected;
}
