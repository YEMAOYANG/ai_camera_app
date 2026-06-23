import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/devices/application/camera_discovery_repository.dart';
import 'package:guardian_parent_app/src/features/devices/application/device_repository.dart';
import 'package:guardian_parent_app/src/features/devices/application/selected_device_controller.dart';
import 'package:guardian_parent_app/src/features/devices/domain/device_models.dart';
import 'package:guardian_parent_app/src/features/live_care/application/camera_repository.dart';
import 'package:guardian_parent_app/src/features/profile/application/profile_repository.dart';
import 'package:guardian_parent_app/src/features/setup/presentation/discovery_scene.dart';
import 'package:guardian_parent_app/src/features/setup/presentation/camera_discovery_animation.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_bottom_sheet.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_toast.dart';

const kSetupDefaultDeviceName = 'AI 看护摄像头';
const kSetupDefaultBindingCode = 'AI-CARE-NEARBY-KINDERGARTEN-V1';

const _fallbackNearbyCandidates = [
  DiscoveredCameraCandidate(
    id: 'nearby-default',
    displayName: kSetupDefaultDeviceName,
    bindingCode: kSetupDefaultBindingCode,
    signalStrength: 86,
    status: 'ready',
  ),
];

/// Opens the add-camera flow as a modal bottom sheet over the current page.
Future<bool?> showAddCameraSheet(
  BuildContext context, {
  CameraDiscoveryPhase? initialPhaseForTesting,
  AddCameraFailureReason? initialFailureReasonForTesting,
  List<DiscoveredCameraCandidate>? initialCandidatesForTesting,
}) {
  return showAppBottomSheet<bool>(
    context: context,
    maxHeightFactor: 0.50,
    child: AddCameraSheet(
      initialPhaseForTesting: initialPhaseForTesting,
      initialFailureReasonForTesting: initialFailureReasonForTesting,
      initialCandidatesForTesting: initialCandidatesForTesting,
    ),
  );
}

class AddCameraSheet extends ConsumerStatefulWidget {
  const AddCameraSheet({
    super.key,
    this.initialPhaseForTesting,
    this.initialFailureReasonForTesting,
    this.initialCandidatesForTesting,
  });

  @visibleForTesting
  final CameraDiscoveryPhase? initialPhaseForTesting;
  @visibleForTesting
  final AddCameraFailureReason? initialFailureReasonForTesting;
  @visibleForTesting
  final List<DiscoveredCameraCandidate>? initialCandidatesForTesting;

  @override
  ConsumerState<AddCameraSheet> createState() => _AddCameraSheetState();
}

class _AddCameraSheetState extends ConsumerState<AddCameraSheet>
    with SingleTickerProviderStateMixin {
  CameraDiscoveryPhase _phase = CameraDiscoveryPhase.preparing;
  StreamSubscription<CameraDiscoveryResult>? _scanSubscription;
  var _connecting = false;
  AddCameraFailureReason? _failureReason;
  CameraDiscoveryPermissionStatus? _permissionStatus;
  List<DiscoveredCameraCandidate> _candidates = const [];
  String? _selectedCandidateId;
  late final CameraDiscoveryRepository _discoveryRepository;
  late final AnimationController _foundEntryController;
  late final Animation<double> _foundFade;
  late final Animation<Offset> _foundSlide;

  @override
  void initState() {
    super.initState();
    _discoveryRepository = ref.read(cameraDiscoveryRepositoryProvider);
    _foundEntryController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 220),
    );
    _foundFade = CurvedAnimation(
      parent: _foundEntryController,
      curve: Curves.easeOutCubic,
    );
    _foundSlide = Tween<Offset>(begin: const Offset(0, 0.06), end: Offset.zero)
        .animate(
          CurvedAnimation(
            parent: _foundEntryController,
            curve: Curves.easeOutCubic,
          ),
        );

    final previewPhase = widget.initialPhaseForTesting;
    final previewCandidates = widget.initialCandidatesForTesting;
    if (previewCandidates != null) {
      _setCandidates(previewCandidates);
    }
    if (previewPhase == null) {
      unawaited(_prepareDiscovery());
    } else {
      _phase = previewPhase;
      _failureReason = widget.initialFailureReasonForTesting;
      if ((_phase == CameraDiscoveryPhase.found ||
              _phase == CameraDiscoveryPhase.connecting) &&
          _candidates.isEmpty) {
        _setCandidates(_fallbackNearbyCandidates);
      }
      _connecting = previewPhase == CameraDiscoveryPhase.connecting;
      if (_phase == CameraDiscoveryPhase.found ||
          _phase == CameraDiscoveryPhase.connecting) {
        _foundEntryController.value = 1;
      }
    }
  }

  @override
  void dispose() {
    unawaited(_stopScan());
    _foundEntryController.dispose();
    super.dispose();
  }

  void _goTo(
    CameraDiscoveryPhase phase, {
    AddCameraFailureReason? failureReason,
    CameraDiscoveryPermissionStatus? permissionStatus,
  }) {
    if (!mounted) return;
    setState(() {
      _phase = phase;
      _failureReason = failureReason;
      _permissionStatus = permissionStatus;
    });
    if (phase == CameraDiscoveryPhase.preparing) {
      _connecting = false;
      _failureReason = null;
      _foundEntryController.reset();
    } else if (phase == CameraDiscoveryPhase.searching) {
      _connecting = false;
      _failureReason = null;
      _foundEntryController.reset();
    } else if (phase == CameraDiscoveryPhase.found) {
      _foundEntryController.forward(from: 0);
    } else if (phase == CameraDiscoveryPhase.connecting) {
      _foundEntryController.value = 1;
    }
  }

  Future<void> _prepareDiscovery({bool requestPermissions = false}) async {
    await _stopScan();
    _goTo(CameraDiscoveryPhase.preparing);
    try {
      final status = requestPermissions
          ? await _discoveryRepository.requestRequiredPermissions()
          : await _discoveryRepository.getPermissionStatus();
      if (!mounted) return;
      _handlePermissionStatus(status);
    } catch (_) {
      if (!mounted) return;
      _goTo(
        CameraDiscoveryPhase.connectionFailed,
        failureReason: AddCameraFailureReason.unknown,
      );
    }
  }

  void _handlePermissionStatus(CameraDiscoveryPermissionStatus status) {
    if (status.canStartDiscovery) {
      _startSearch();
      return;
    }
    if (status == CameraDiscoveryPermissionStatus.bluetoothOff) {
      _goTo(
        CameraDiscoveryPhase.bluetoothOff,
        failureReason: AddCameraFailureReason.bluetoothUnavailable,
        permissionStatus: status,
      );
      return;
    }
    if (status.requiresUserPermission) {
      _goTo(
        CameraDiscoveryPhase.permissionRequired,
        failureReason: _failureReasonForPermissionStatus(status),
        permissionStatus: status,
      );
      return;
    }
    _goTo(
      CameraDiscoveryPhase.connectionFailed,
      failureReason: AddCameraFailureReason.unsupported,
      permissionStatus: status,
    );
  }

  AddCameraFailureReason _failureReasonForPermissionStatus(
    CameraDiscoveryPermissionStatus status,
  ) {
    return switch (status) {
      CameraDiscoveryPermissionStatus.bluetoothPermissionPermanentlyDenied =>
        AddCameraFailureReason.permissionPermanentlyDenied,
      CameraDiscoveryPermissionStatus.localNetworkPermissionDenied ||
      CameraDiscoveryPermissionStatus.localNetworkPermissionRequired =>
        AddCameraFailureReason.localNetworkPermissionDenied,
      CameraDiscoveryPermissionStatus.bluetoothOff =>
        AddCameraFailureReason.bluetoothUnavailable,
      CameraDiscoveryPermissionStatus.unsupported =>
        AddCameraFailureReason.unsupported,
      _ => AddCameraFailureReason.permissionDenied,
    };
  }

  void _startSearch() {
    unawaited(_beginSearch());
  }

  Future<void> _beginSearch() async {
    await _stopScan();
    if (!mounted) return;
    _goTo(CameraDiscoveryPhase.searching);
    final previewCandidates = widget.initialCandidatesForTesting;
    if (previewCandidates != null) {
      _setCandidates(previewCandidates);
      _goTo(
        previewCandidates.isEmpty
            ? CameraDiscoveryPhase.notFound
            : CameraDiscoveryPhase.found,
        failureReason: previewCandidates.isEmpty
            ? AddCameraFailureReason.timeout
            : null,
      );
      return;
    }
    _scanSubscription = _discoveryRepository.startScan().listen(
      (result) {
        if (!mounted || _phase != CameraDiscoveryPhase.searching) return;
        _setCandidates(result.candidates);
        _goTo(result.phase, failureReason: result.failureReason);
      },
      onError: (_) {
        if (!mounted) return;
        _goTo(
          CameraDiscoveryPhase.connectionFailed,
          failureReason: AddCameraFailureReason.unknown,
        );
      },
      onDone: () {
        if (!mounted || _phase != CameraDiscoveryPhase.searching) return;
        _goTo(
          CameraDiscoveryPhase.notFound,
          failureReason: AddCameraFailureReason.timeout,
        );
      },
    );
  }

  Future<void> _stopScan() async {
    final subscription = _scanSubscription;
    _scanSubscription = null;
    final stopFuture = _discoveryRepository.stopScan();
    if (subscription != null) {
      unawaited(subscription.cancel());
    }
    await stopFuture;
  }

  void _setCandidates(List<DiscoveredCameraCandidate> candidates) {
    final sorted = [...candidates]
      ..sort((a, b) {
        if (a.isConnectable != b.isConnectable) {
          return a.isConnectable ? -1 : 1;
        }
        return b.signalStrength.compareTo(a.signalStrength);
      });
    setState(() {
      _candidates = sorted;
      _selectedCandidateId = sorted.isEmpty ? null : sorted.first.id;
    });
  }

  DiscoveredCameraCandidate? get _selectedCandidate {
    for (final candidate in _candidates) {
      if (candidate.id == _selectedCandidateId) return candidate;
    }
    return _candidates.isEmpty ? null : _candidates.first;
  }

  Future<void> _connectCamera() async {
    if (_connecting) return;
    setState(() {
      _phase = CameraDiscoveryPhase.connecting;
      _connecting = true;
    });
    await _stopScan();
    try {
      final candidate = _selectedCandidate;
      if (candidate == null) {
        _goTo(
          CameraDiscoveryPhase.notFound,
          failureReason: AddCameraFailureReason.timeout,
        );
        setState(() => _connecting = false);
        return;
      }
      final device = await _discoveryRepository.connectDiscoveredCamera(
        candidate,
      );
      await selectDevice(ref, device.id);
      final readiness = await _discoveryRepository.checkCameraReadiness(
        device.id,
      );
      _refreshCameraAfterAdd(ref);
      if (!mounted) return;
      setState(() {
        _phase = readiness.livePreviewAvailable
            ? CameraDiscoveryPhase.connected
            : CameraDiscoveryPhase.connectedWithoutLivePreview;
        _connecting = false;
      });
      showAppToast(
        context,
        readiness.livePreviewAvailable ? '实时看护已准备好' : '摄像头已添加',
      );
    } on DeviceException catch (error) {
      if (!mounted) return;
      setState(() {
        _phase = _phaseForDeviceError(error);
        _failureReason = _failureReasonForDeviceError(error);
        _connecting = false;
      });
      showAppToast(context, error.message);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _phase = CameraDiscoveryPhase.connectionFailed;
        _failureReason = AddCameraFailureReason.unknown;
        _connecting = false;
      });
      showAppToast(context, '连接失败，请稍后重试');
    }
  }

  CameraDiscoveryPhase _phaseForDeviceError(DeviceException error) {
    return switch (error.code) {
      'already_bound' ||
      'device_already_bound' ||
      'binding_code_already_bound' ||
      'binding_code_in_use' => CameraDiscoveryPhase.alreadyBoundToAnotherFamily,
      'network_setup_failed' ||
      'wifi_setup_failed' => CameraDiscoveryPhase.networkSetupFailed,
      'bluetooth_unavailable' => CameraDiscoveryPhase.bluetoothOff,
      'permission_denied' => CameraDiscoveryPhase.permissionRequired,
      'ble_adapter_unavailable' => CameraDiscoveryPhase.connectionFailed,
      _ => CameraDiscoveryPhase.connectionFailed,
    };
  }

  AddCameraFailureReason _failureReasonForDeviceError(DeviceException error) {
    return switch (error.code) {
      'already_bound' ||
      'device_already_bound' ||
      'binding_code_already_bound' ||
      'binding_code_in_use' => AddCameraFailureReason.alreadyBound,
      'network_setup_failed' ||
      'wifi_setup_failed' => AddCameraFailureReason.networkSetupFailed,
      'bluetooth_unavailable' => AddCameraFailureReason.bluetoothUnavailable,
      'permission_denied' => AddCameraFailureReason.permissionDenied,
      'ble_adapter_unavailable' => AddCameraFailureReason.bleAdapterUnavailable,
      _ => AddCameraFailureReason.connectionLost,
    };
  }

  void _showConnectionHelp() {
    showAppToast(context, '请确认摄像头已开机，并靠近手机。');
  }

  void _close({bool success = false}) {
    unawaited(_stopScan());
    Navigator.of(context).pop(success);
  }

  Future<void> _openSystemSettings() async {
    await _discoveryRepository.openSystemSettings();
    if (!mounted) return;
    showAppToast(context, '请在系统设置中允许后再试。');
  }

  @override
  Widget build(BuildContext context) {
    final screenHeight = MediaQuery.sizeOf(context).height;
    final bodyHeight = (screenHeight < 740 ? 162.0 : 190.0).clamp(150.0, 220.0);

    return AppBottomSheetBody(
      title: _sheetTitle(_phase, _candidates, _permissionStatus),
      subtitle: _sheetSubtitle(_phase, _permissionStatus),
      scrollable: false,
      footer: _SheetActions(
        phase: _phase,
        permissionStatus: _permissionStatus,
        selectedCandidate: _selectedCandidate,
        onConnect: _connectCamera,
        onRetry: () => unawaited(_prepareDiscovery()),
        onRequestPermissions: () =>
            unawaited(_prepareDiscovery(requestPermissions: true)),
        onOpenSettings: () => unawaited(_openSystemSettings()),
        onFinish: () => _close(success: true),
        onCancel: () => _close(),
        onHelp: _showConnectionHelp,
      ),
      child: SizedBox(
        height: bodyHeight,
        child: AnimatedSwitcher(
          duration: AppMotion.duration(context, 220),
          switchInCurve: Curves.easeOutCubic,
          switchOutCurve: Curves.easeInCubic,
          child: _SheetBody(
            key: ValueKey(_phase),
            phase: _phase,
            candidates: _candidates,
            selectedCandidateId: _selectedCandidateId,
            onSelectCandidate: (candidate) {
              setState(() => _selectedCandidateId = candidate.id);
            },
            failureReason: _failureReason,
            permissionStatus: _permissionStatus,
            foundFade: _foundFade,
            foundSlide: _foundSlide,
          ),
        ),
      ),
    );
  }
}

String _sheetTitle(
  CameraDiscoveryPhase phase,
  List<DiscoveredCameraCandidate> candidates,
  CameraDiscoveryPermissionStatus? permissionStatus,
) {
  return switch (phase) {
    CameraDiscoveryPhase.preparing => '准备连接',
    CameraDiscoveryPhase.permissionRequired => _permissionTitle(
      permissionStatus,
    ),
    CameraDiscoveryPhase.bluetoothOff => '请打开蓝牙',
    CameraDiscoveryPhase.searching => '搜索附近摄像头',
    CameraDiscoveryPhase.found =>
      candidates.length <= 1 ? '发现 1 台附近摄像头' : '发现 ${candidates.length} 台附近摄像头',
    CameraDiscoveryPhase.connecting => '正在连接',
    CameraDiscoveryPhase.connected => '摄像头已连接',
    CameraDiscoveryPhase.connectedWithoutLivePreview => '摄像头已添加',
    CameraDiscoveryPhase.notFound => '没有找到附近摄像头',
    CameraDiscoveryPhase.connectionFailed => '连接失败',
    CameraDiscoveryPhase.alreadyBoundToAnotherFamily => '这台摄像头已被绑定',
    CameraDiscoveryPhase.networkSetupFailed => '网络连接失败',
    CameraDiscoveryPhase.cancelled => '已取消连接',
  };
}

String _permissionTitle(CameraDiscoveryPermissionStatus? status) {
  return switch (status) {
    CameraDiscoveryPermissionStatus.localNetworkPermissionRequired ||
    CameraDiscoveryPermissionStatus.localNetworkPermissionDenied => '需要本地网络权限',
    CameraDiscoveryPermissionStatus.bluetoothPermissionRequired ||
    CameraDiscoveryPermissionStatus.bluetoothPermissionDenied ||
    CameraDiscoveryPermissionStatus.bluetoothPermissionPermanentlyDenied =>
      '需要允许蓝牙',
    _ => '需要附近设备权限',
  };
}

String _sheetSubtitle(
  CameraDiscoveryPhase phase,
  CameraDiscoveryPermissionStatus? permissionStatus,
) {
  return switch (phase) {
    CameraDiscoveryPhase.permissionRequired => _permissionSubtitle(
      permissionStatus,
    ),
    CameraDiscoveryPhase.bluetoothOff => '打开蓝牙后，我们会继续搜索附近摄像头。',
    CameraDiscoveryPhase.searching => '请保持摄像头通电，并靠近手机。',
    CameraDiscoveryPhase.connected => '实时看护已准备好',
    CameraDiscoveryPhase.connectedWithoutLivePreview => '实时画面暂时不可用，可稍后在看护页重试。',
    CameraDiscoveryPhase.notFound => '请确认摄像头已开机，并靠近手机。',
    CameraDiscoveryPhase.connectionFailed => '请靠近摄像头后再试一次。',
    CameraDiscoveryPhase.alreadyBoundToAnotherFamily =>
      '请确认设备是否已被家人添加，或重置摄像头后再试。',
    CameraDiscoveryPhase.networkSetupFailed => '请确认家庭 Wi-Fi 可用，再重新连接。',
    _ => '',
  };
}

String _permissionSubtitle(CameraDiscoveryPermissionStatus? status) {
  return switch (status) {
    CameraDiscoveryPermissionStatus.localNetworkPermissionRequired ||
    CameraDiscoveryPermissionStatus.localNetworkPermissionDenied =>
      '需要允许本地网络，才能和家里的摄像头建立连接。',
    CameraDiscoveryPermissionStatus.bluetoothPermissionPermanentlyDenied =>
      '请在系统设置中允许蓝牙权限后继续。',
    _ => '需要允许蓝牙，才能发现附近摄像头。',
  };
}

String _permissionMessage(CameraDiscoveryPermissionStatus? status) {
  return switch (status) {
    CameraDiscoveryPermissionStatus.localNetworkPermissionRequired ||
    CameraDiscoveryPermissionStatus.localNetworkPermissionDenied =>
      '允许后会继续建立连接。',
    CameraDiscoveryPermissionStatus.bluetoothPermissionPermanentlyDenied =>
      '请在系统设置中允许蓝牙权限。',
    _ => '允许后会继续搜索附近摄像头。',
  };
}

class _SearchingDots extends StatefulWidget {
  const _SearchingDots();

  @override
  State<_SearchingDots> createState() => _SearchingDotsState();
}

class _SearchingDotsState extends State<_SearchingDots>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (MediaQuery.disableAnimationsOf(context)) {
      return const Text(
        '...',
        style: TextStyle(
          color: AppColors.muted,
          fontWeight: FontWeight.w800,
          fontSize: 18,
        ),
      );
    }
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: List.generate(3, (index) {
            final phase = ((_controller.value + index * 0.33) % 1);
            final alpha = (math.sin(phase * math.pi)).clamp(0.25, 1.0);
            return Padding(
              padding: const EdgeInsets.only(left: 3),
              child: Opacity(
                opacity: alpha,
                child: Container(
                  width: 5,
                  height: 5,
                  decoration: const BoxDecoration(
                    color: AppColors.brandSage,
                    shape: BoxShape.circle,
                  ),
                ),
              ),
            );
          }),
        );
      },
    );
  }
}

class _SheetBody extends StatelessWidget {
  const _SheetBody({
    required this.phase,
    required this.candidates,
    required this.selectedCandidateId,
    required this.onSelectCandidate,
    required this.failureReason,
    required this.permissionStatus,
    required this.foundFade,
    required this.foundSlide,
    super.key,
  });

  final CameraDiscoveryPhase phase;
  final List<DiscoveredCameraCandidate> candidates;
  final String? selectedCandidateId;
  final ValueChanged<DiscoveredCameraCandidate> onSelectCandidate;
  final AddCameraFailureReason? failureReason;
  final CameraDiscoveryPermissionStatus? permissionStatus;
  final Animation<double> foundFade;
  final Animation<Offset> foundSlide;

  @override
  Widget build(BuildContext context) {
    final animSize = MediaQuery.sizeOf(context).height < 740 ? 204.0 : 216.0;
    return switch (phase) {
      CameraDiscoveryPhase.preparing || CameraDiscoveryPhase.searching => Align(
        alignment: Alignment.topCenter,
        child: CameraDiscoveryAnimation(
          state: CameraDiscoveryVisualState.searching,
          size: animSize,
          showDevice: false,
        ),
      ),
      CameraDiscoveryPhase.permissionRequired => Align(
        alignment: Alignment.center,
        child: _SheetMessage(
          icon: Icons.nearby_error_outlined,
          title: _permissionMessage(permissionStatus),
          tone: _MessageTone.warning,
        ),
      ),
      CameraDiscoveryPhase.bluetoothOff => const Align(
        alignment: Alignment.center,
        child: _SheetMessage(
          icon: Icons.bluetooth_rounded,
          title: '打开蓝牙后会继续搜索附近摄像头。',
          tone: _MessageTone.warning,
        ),
      ),
      CameraDiscoveryPhase.found || CameraDiscoveryPhase.connecting => Align(
        alignment: Alignment.topCenter,
        child: SizedBox(
          width: double.infinity,
          child: FadeTransition(
            opacity: foundFade,
            child: SlideTransition(
              position: foundSlide,
              child: _DiscoveredDeviceList(
                candidates: candidates,
                selectedCandidateId: selectedCandidateId,
                connecting: phase == CameraDiscoveryPhase.connecting,
                onSelect: phase == CameraDiscoveryPhase.connecting
                    ? null
                    : onSelectCandidate,
              ),
            ),
          ),
        ),
      ),
      CameraDiscoveryPhase.connected => const Align(
        alignment: Alignment.center,
        child: _SheetMessage(
          icon: Icons.check_rounded,
          title: '实时看护已准备好',
          detail: '已加入家庭看护空间。',
          tone: _MessageTone.success,
        ),
      ),
      CameraDiscoveryPhase.connectedWithoutLivePreview => const Align(
        alignment: Alignment.center,
        child: _SheetMessage(
          icon: Icons.check_rounded,
          title: '实时画面暂时不可用',
          detail: '可稍后在看护页重试。',
          tone: _MessageTone.warning,
        ),
      ),
      CameraDiscoveryPhase.notFound => const Align(
        alignment: Alignment.center,
        child: _SheetMessage(
          icon: Icons.travel_explore_rounded,
          title: '确认摄像头已开机，并靠近手机。',
          tone: _MessageTone.warning,
        ),
      ),
      CameraDiscoveryPhase.connectionFailed => Align(
        alignment: Alignment.center,
        child: _SheetMessage(
          icon: Icons.error_outline_rounded,
          title: _connectionFailureTitle(failureReason),
          tone: _MessageTone.danger,
        ),
      ),
      CameraDiscoveryPhase.alreadyBoundToAnotherFamily => const Align(
        alignment: Alignment.center,
        child: _SheetMessage(
          icon: Icons.lock_outline_rounded,
          title: '请确认是否已被家人添加。',
          detail: '也可以重置摄像头后再试。',
          tone: _MessageTone.warning,
        ),
      ),
      CameraDiscoveryPhase.networkSetupFailed => const Align(
        alignment: Alignment.center,
        child: _SheetMessage(
          icon: Icons.wifi_rounded,
          title: '请确认家庭 Wi-Fi 可用。',
          detail: '然后重新连接摄像头。',
          tone: _MessageTone.danger,
        ),
      ),
      CameraDiscoveryPhase.cancelled => const SizedBox.shrink(),
    };
  }
}

String _connectionFailureTitle(AddCameraFailureReason? reason) {
  return switch (reason) {
    AddCameraFailureReason.connectionLost => '连接中断，请靠近摄像头后再试一次。',
    AddCameraFailureReason.bluetoothUnavailable => '蓝牙暂时不可用，请打开后再试。',
    AddCameraFailureReason.bleAdapterUnavailable => '暂时无法连接摄像头，请稍后再试。',
    AddCameraFailureReason.permissionDenied => '需要允许附近设备权限后再连接。',
    _ => '请靠近摄像头后再试一次。',
  };
}

class _DiscoveredDeviceList extends StatelessWidget {
  const _DiscoveredDeviceList({
    required this.candidates,
    required this.selectedCandidateId,
    required this.connecting,
    required this.onSelect,
  });

  final List<DiscoveredCameraCandidate> candidates;
  final String? selectedCandidateId;
  final bool connecting;
  final ValueChanged<DiscoveredCameraCandidate>? onSelect;

  @override
  Widget build(BuildContext context) {
    if (candidates.isEmpty) {
      return const SizedBox.shrink();
    }
    return ListView.separated(
      padding: const EdgeInsets.only(top: 2, bottom: 6),
      physics: candidates.length <= 2
          ? const NeverScrollableScrollPhysics()
          : const BouncingScrollPhysics(),
      itemBuilder: (context, index) {
        final candidate = candidates[index];
        return _DiscoveredDeviceTile(
          candidate: candidate,
          selected: candidate.id == selectedCandidateId,
          connecting: connecting && candidate.id == selectedCandidateId,
          onTap: onSelect == null ? null : () => onSelect!(candidate),
        );
      },
      separatorBuilder: (_, _) => const SizedBox(height: 8),
      itemCount: candidates.length,
    );
  }
}

class _DiscoveredDeviceTile extends StatefulWidget {
  const _DiscoveredDeviceTile({
    required this.candidate,
    required this.selected,
    this.connecting = false,
    this.onTap,
  });

  final DiscoveredCameraCandidate candidate;
  final bool selected;
  final bool connecting;
  final VoidCallback? onTap;

  @override
  State<_DiscoveredDeviceTile> createState() => _DiscoveredDeviceTileState();
}

class _DiscoveredDeviceTileState extends State<_DiscoveredDeviceTile>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ringController;

  @override
  void initState() {
    super.initState();
    _ringController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2200),
    )..repeat();
  }

  @override
  void dispose() {
    _ringController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final statusColor = widget.connecting
        ? AppColors.brand
        : widget.selected
        ? AppColors.success
        : widget.candidate.isConnectable
        ? AppColors.brandSage
        : AppColors.warning;
    final reduceMotion = MediaQuery.disableAnimationsOf(context);

    return Semantics(
      button: widget.onTap != null,
      selected: widget.selected,
      label: widget.candidate.displayName,
      child: InkWell(
        key: ValueKey('discoveredCamera_${widget.candidate.id}'),
        borderRadius: BorderRadius.circular(AppRadii.cardLarge),
        onTap: widget.onTap,
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppRadii.cardLarge),
            color: AppColors.surfaceElevated,
            border: Border.all(
              color: widget.selected
                  ? AppColors.brandSage.withValues(alpha: 0.5)
                  : AppColors.borderSoft,
              width: widget.selected ? 1.2 : 1,
            ),
            boxShadow: widget.selected
                ? [
                    BoxShadow(
                      color: AppColors.brandSage.withValues(alpha: 0.1),
                      blurRadius: 12,
                      offset: const Offset(0, 5),
                    ),
                  ]
                : null,
          ),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(13, 10, 13, 10),
            child: Row(
              children: [
                SizedBox(
                  width: 54,
                  height: 54,
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      if (!reduceMotion && widget.selected)
                        AnimatedBuilder(
                          animation: _ringController,
                          builder: (context, _) => CustomPaint(
                            size: const Size.square(54),
                            painter: DiscoveryIconRingPainter(
                              progress: _ringController.value,
                              active: !widget.connecting,
                            ),
                          ),
                        ),
                      CameraDeviceGlyph(
                        size: 46,
                        compact: true,
                        statusLightColor: statusColor,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        widget.candidate.displayName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: AppColors.ink,
                          fontFamily: AppTypography.systemFont,
                          fontSize: 15,
                          fontWeight: FontWeight.w900,
                          height: 1.2,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Row(
                        children: [
                          _SignalBars(
                            active: widget.candidate.signalBars,
                            color: statusColor,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              widget.connecting
                                  ? '正在建立安全连接'
                                  : _candidateStatusText(widget.candidate),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                color: AppColors.muted,
                                fontFamily: AppTypography.systemFont,
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                height: 1.2,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 6),
                if (widget.connecting)
                  const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: AppColors.brand,
                    ),
                  )
                else
                  Icon(
                    widget.selected
                        ? Icons.check_circle_rounded
                        : Icons.radio_button_unchecked_rounded,
                    size: 19,
                    color: widget.selected ? statusColor : AppColors.subtle,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

String _candidateStatusText(DiscoveredCameraCandidate candidate) {
  if (!candidate.isConnectable) {
    final reason = candidate.unavailableReason;
    return reason == null || reason.isEmpty ? '暂时无法连接' : reason;
  }
  return '${candidate.signalLabel} · 可连接';
}

class _SignalBars extends StatelessWidget {
  const _SignalBars({required this.active, required this.color});

  final int active;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(4, (index) {
        final on = index < active;
        return Container(
          width: 3,
          height: 6 + index * 3,
          margin: const EdgeInsets.only(right: 2),
          decoration: BoxDecoration(
            color: on ? color : AppColors.border,
            borderRadius: BorderRadius.circular(1),
          ),
        );
      }),
    );
  }
}

enum _MessageTone { success, warning, danger }

class _SheetMessage extends StatelessWidget {
  const _SheetMessage({
    required this.icon,
    required this.title,
    required this.tone,
    this.detail,
  });

  final IconData icon;
  final String title;
  final String? detail;
  final _MessageTone tone;

  @override
  Widget build(BuildContext context) {
    final colors = switch (tone) {
      _MessageTone.success => (
        bg: AppColors.successWash,
        fg: AppColors.success,
      ),
      _MessageTone.warning => (
        bg: AppColors.warningWash,
        fg: AppColors.warning,
      ),
      _MessageTone.danger => (bg: AppColors.dangerWash, fg: AppColors.danger),
    };
    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxHeight < 112;
        final iconSize = compact ? 38.0 : 58.0;
        final iconRadius = compact ? 14.0 : 21.0;
        final showDetail =
            !compact && detail != null && detail!.trim().isNotEmpty;
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: iconSize,
              height: iconSize,
              decoration: BoxDecoration(
                color: colors.bg,
                borderRadius: BorderRadius.circular(iconRadius),
              ),
              child: Icon(icon, color: colors.fg, size: compact ? 22 : 29),
            ),
            SizedBox(height: compact ? 8 : 14),
            Text(
              title,
              textAlign: TextAlign.center,
              maxLines: compact ? 2 : 3,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: compact ? 13 : 15,
                fontWeight: FontWeight.w900,
                height: compact ? 1.25 : 1.42,
              ),
            ),
            if (showDetail) ...[
              const SizedBox(height: 5),
              Text(
                detail!,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: AppColors.muted,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  height: 1.35,
                ),
              ),
            ],
          ],
        );
      },
    );
  }
}

class _SheetActions extends StatelessWidget {
  const _SheetActions({
    required this.phase,
    required this.permissionStatus,
    required this.selectedCandidate,
    required this.onConnect,
    required this.onRetry,
    required this.onRequestPermissions,
    required this.onOpenSettings,
    required this.onFinish,
    required this.onCancel,
    required this.onHelp,
  });

  final CameraDiscoveryPhase phase;
  final CameraDiscoveryPermissionStatus? permissionStatus;
  final DiscoveredCameraCandidate? selectedCandidate;
  final VoidCallback onConnect;
  final VoidCallback onRetry;
  final VoidCallback onRequestPermissions;
  final VoidCallback onOpenSettings;
  final VoidCallback onFinish;
  final VoidCallback onCancel;
  final VoidCallback onHelp;

  @override
  Widget build(BuildContext context) {
    return switch (phase) {
      CameraDiscoveryPhase.preparing ||
      CameraDiscoveryPhase.searching => Padding(
        padding: const EdgeInsets.only(top: 6),
        child: _HelpLink(onTap: onHelp),
      ),
      CameraDiscoveryPhase.permissionRequired => _PermissionActions(
        permissionStatus: permissionStatus,
        onRequestPermissions: onRequestPermissions,
        onOpenSettings: onOpenSettings,
        onCancel: onCancel,
      ),
      CameraDiscoveryPhase.bluetoothOff => Column(
        mainAxisSize: MainAxisSize.min,
        children: [AppSheetPrimaryButton(label: '我已打开', onTap: onRetry)],
      ),
      CameraDiscoveryPhase.found => AppSheetPrimaryButton(
        label: '连接',
        onTap: selectedCandidate?.isConnectable == true ? onConnect : null,
      ),
      CameraDiscoveryPhase.connecting => const AppSheetPrimaryButton(
        label: '正在连接',
        onTap: null,
        loading: true,
      ),
      CameraDiscoveryPhase.connected ||
      CameraDiscoveryPhase.connectedWithoutLivePreview => AppSheetPrimaryButton(
        label: '完成',
        onTap: onFinish,
      ),
      CameraDiscoveryPhase.notFound ||
      CameraDiscoveryPhase.alreadyBoundToAnotherFamily => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AppSheetPrimaryButton(label: '重新搜索', onTap: onRetry),
          const SizedBox(height: 10),
          _HelpLink(onTap: onHelp),
        ],
      ),
      CameraDiscoveryPhase.connectionFailed => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AppSheetPrimaryButton(label: '重新连接', onTap: onConnect),
          const SizedBox(height: 10),
          _HelpLink(onTap: onHelp),
        ],
      ),
      CameraDiscoveryPhase.networkSetupFailed => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AppSheetPrimaryButton(label: '重试', onTap: onConnect),
          const SizedBox(height: 10),
          _HelpLink(onTap: onHelp),
        ],
      ),
      CameraDiscoveryPhase.cancelled => const SizedBox.shrink(),
    };
  }
}

class _PermissionActions extends StatelessWidget {
  const _PermissionActions({
    required this.permissionStatus,
    required this.onRequestPermissions,
    required this.onOpenSettings,
    required this.onCancel,
  });

  final CameraDiscoveryPermissionStatus? permissionStatus;
  final VoidCallback onRequestPermissions;
  final VoidCallback onOpenSettings;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final permanentlyDenied =
        permissionStatus?.isPermanentlyDenied == true ||
        permissionStatus ==
            CameraDiscoveryPermissionStatus.localNetworkPermissionDenied;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        AppSheetPrimaryButton(
          label: permanentlyDenied ? '去系统设置' : '允许并继续',
          onTap: permanentlyDenied ? onOpenSettings : onRequestPermissions,
        ),
        const SizedBox(height: 10),
        AppSheetSecondaryButton(label: '稍后再说', onTap: onCancel),
      ],
    );
  }
}

class _HelpLink extends StatelessWidget {
  const _HelpLink({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: TextButton(
        onPressed: onTap,
        style: TextButton.styleFrom(
          foregroundColor: AppColors.muted,
          minimumSize: const Size(96, 40),
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
        child: Text(
          '连接帮助',
          style: const TextStyle(
            fontFamily: AppTypography.systemFont,
            fontSize: 13,
            fontWeight: FontWeight.w800,
          ),
        ),
      ),
    );
  }
}

void _refreshCameraAfterAdd(WidgetRef ref) {
  ref
    ..invalidate(devicesProvider)
    ..invalidate(primaryDeviceOverviewProvider)
    ..invalidate(selectedDeviceProvider)
    ..invalidate(cameraHealthProvider)
    ..invalidate(cameraRuntimeProvider)
    ..invalidate(cameraStatusProvider)
    ..invalidate(cameraMonitorStatusProvider)
    ..invalidate(cameraSnapshotProvider)
    ..invalidate(cameraEventsProvider)
    ..invalidate(liveCareStatusProvider)
    ..invalidate(profileSummaryProvider)
    ..invalidate(accountProfileProvider);
}

/// Deep-link fallback: transparent page that presents the sheet immediately.
class AddCameraRouteScreen extends StatefulWidget {
  const AddCameraRouteScreen({super.key});

  @override
  State<AddCameraRouteScreen> createState() => _AddCameraRouteScreenState();
}

class _AddCameraRouteScreenState extends State<AddCameraRouteScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      await showAddCameraSheet(context);
      if (mounted) Navigator.of(context).pop();
    });
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Colors.transparent,
      body: SizedBox.shrink(),
    );
  }
}

/// Setup flow entry: presents sheet and pops setup route when finished.
class DeviceEntrySetupScreen extends StatefulWidget {
  const DeviceEntrySetupScreen({super.key});

  @override
  State<DeviceEntrySetupScreen> createState() => _DeviceEntrySetupScreenState();
}

class _DeviceEntrySetupScreenState extends State<DeviceEntrySetupScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      await showAddCameraSheet(context);
      if (mounted) Navigator.of(context).pop();
    });
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: AppColors.appBackgroundWarm,
      body: SizedBox.shrink(),
    );
  }
}
