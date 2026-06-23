# Camera Discovery Architecture

This document describes the add-camera discovery boundary for the current
kindergarten V1 parent app.

## Current State

- The visible add-camera flow is implemented in Flutter and uses the shared
  bottom sheet components.
- The UI consumes `CameraDiscoveryRepository`; it should not run Bluetooth
  scanning, timers, or binding logic directly.
- `CameraDiscoveryRepository` delegates to a `CameraDiscoveryAdapter`.
- The default adapter is currently development-backed and returns nearby camera
  candidates that match the backend device binding contract.
- User-visible copy must use neutral product wording such as `AI 看护摄像头` and
  must not expose engineering terms.

## Adapter Boundary

The discovery contract is:

```text
AddCameraSheet
  -> CameraDiscoveryRepository
  -> CameraDiscoveryAdapter
    -> MockCameraDiscoveryAdapter
    -> BleCameraDiscoveryAdapter
```

`CameraDiscoveryAdapter` owns:

- Permission status probing.
- Bluetooth availability checks.
- Starting and stopping discovery.
- Connecting a selected candidate.
- Checking whether live preview is ready after binding.

The widget tree only renders `CameraDiscoveryPhase`,
`CameraDiscoveryPermissionStatus`, `CameraDiscoveryResult`, and
`DiscoveredCameraCandidate`.

## Feature Flag

Discovery backend selection is centralized through:

```text
CAMERA_DISCOVERY_BACKEND=mock|ble
```

Default behavior:

- Development/test default: `mock`.
- `ble` in development/test can safely fall back to the current development
  adapter while the hardware protocol is not ready.
- `ble` in production must not silently use development discovery. Until the
  self-owned camera BLE protocol is implemented, the BLE adapter returns an
  unavailable/unsupported result.

## BLE Adapter Status

`BleCameraDiscoveryAdapter` is a contract-only boundary in this stage. It does
not use a BLE SDK and does not perform real hardware discovery yet.

The future real implementation should fill in:

- BLE scan filters and service UUIDs.
- Advertisement payload parsing.
- Stable device identity.
- Pairing and ownership checks.
- Wi-Fi provisioning or local-network handoff.
- Device readiness checks.

## Permissions

Current platform preparation:

- iOS: Bluetooth permission usage text and local-network usage text are present.
- Android: Bluetooth scan/connect, legacy location, nearby Wi-Fi, and network
  state permissions are present.

`permission_handler` is already used for permission probing. The real BLE stage
should decide whether to add a BLE package such as `flutter_blue_plus` after the
hardware advertisement format and pairing protocol are available.

## Device Identity

The current development flow can still use a binding code compatible with the
backend contract. Real hardware must replace that with a stable global device
identity such as:

- `deviceUniqueId`
- `serialNumber`

The app should not continue relying on binding code for real multi-family
ownership checks.

## Guardrails

- Do not show adapter/backend/debug terms in parent-facing UI.
- Do not put scan timers or candidate generation back inside the sheet.
- Do not enable a real BLE backend in production until the adapter can discover
  and verify self-owned camera hardware.
- Do not let the Flutter UI directly access RTSP, device private protocols, or
  camera runtime provider keys.
