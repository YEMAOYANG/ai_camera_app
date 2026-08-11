import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/devices/application/onvif_auto_discovery_coordinator.dart';
import 'package:warm_sight/src/features/devices/domain/device_models.dart';
import 'package:warm_sight/src/features/setup/presentation/camera_discovery_animation.dart';
import 'package:warm_sight/src/features/setup/presentation/onvif_pairing_sheet.dart';
import 'package:warm_sight/src/shared/widgets/app_bottom_sheet.dart';

/// Opens the product camera-add flow.
Future<bool?> showOnvifFirstAddCameraFlow(BuildContext context) async {
  final container = ProviderScope.containerOf(context, listen: false);
  final coordinator = container.read(onvifAutoDiscoveryCoordinatorProvider);

  while (context.mounted) {
    final discovery = await showAppBottomSheet<_OnvifDiscoveryOutcome>(
      context: context,
      maxHeightFactor: 0.68,
      child: _ManualOnvifDiscoverySheet(coordinator: coordinator),
    );
    if (!context.mounted || discovery == null) return null;

    final candidates = discovery.candidates;
    if (candidates.isEmpty || !coordinator.beginPresentation(candidates)) {
      continue;
    }

    OnvifPairingOutcome? outcome;
    try {
      outcome = await showOnvifPairingSheet(context, candidates: candidates);
    } finally {
      coordinator.endPresentation();
    }
    if (!context.mounted || outcome == null) return null;
    if (outcome == OnvifPairingOutcome.paired) return true;
    coordinator.allowRediscovery(candidates);
  }
  return null;
}

enum _ManualDiscoveryView { searching, notFound, error }

class _OnvifDiscoveryOutcome {
  const _OnvifDiscoveryOutcome.candidates(this.candidates);

  final List<OnvifDiscoveryCandidate> candidates;
}

class _ManualOnvifDiscoverySheet extends StatefulWidget {
  const _ManualOnvifDiscoverySheet({required this.coordinator});

  final OnvifAutoDiscoveryCoordinator coordinator;

  @override
  State<_ManualOnvifDiscoverySheet> createState() =>
      _ManualOnvifDiscoverySheetState();
}

class _ManualOnvifDiscoverySheetState
    extends State<_ManualOnvifDiscoverySheet> {
  _ManualDiscoveryView _view = _ManualDiscoveryView.searching;
  String? _message;
  var _searchGeneration = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(_search());
    });
  }

  @override
  void dispose() {
    _searchGeneration++;
    super.dispose();
  }

  Future<void> _search() async {
    final generation = ++_searchGeneration;
    if (mounted) {
      setState(() {
        _view = _ManualDiscoveryView.searching;
        _message = null;
      });
    }
    try {
      final candidates = await widget.coordinator.scanForManualPairing();
      if (!mounted || generation != _searchGeneration) return;
      if (candidates.isNotEmpty) {
        Navigator.of(
          context,
        ).pop(_OnvifDiscoveryOutcome.candidates(candidates));
        return;
      }
      setState(() {
        _view = _ManualDiscoveryView.notFound;
        _message = null;
      });
    } on DeviceException catch (error) {
      if (!mounted || generation != _searchGeneration) return;
      setState(() {
        _view = _ManualDiscoveryView.error;
        _message = _discoveryErrorMessage(error);
      });
    } catch (_) {
      if (!mounted || generation != _searchGeneration) return;
      setState(() {
        _view = _ManualDiscoveryView.error;
        _message = '暂时无法连接摄像头，请检查网络后重试。';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppBottomSheetBody(
      key: const ValueKey('onvif_manual_discovery_sheet'),
      title: _title,
      subtitle: _subtitle,
      scrollable: false,
      footer: _buildFooter(),
      child: AnimatedSwitcher(
        duration: AppMotion.duration(context, 180),
        child: _buildDiscoveryState(),
      ),
    );
  }

  String get _title {
    return switch (_view) {
      _ManualDiscoveryView.searching => '正在搜索看护摄像头',
      _ManualDiscoveryView.notFound => '没有找到摄像头',
      _ManualDiscoveryView.error => '暂时无法搜索',
    };
  }

  String get _subtitle {
    return switch (_view) {
      _ManualDiscoveryView.searching => '请确保摄像头已上电，并已连接当前家庭网络',
      _ManualDiscoveryView.notFound => '请确认摄像头已开机，并与手机连接到同一家庭网络',
      _ManualDiscoveryView.error => '网络连接不稳定，请稍后重新搜索',
    };
  }

  Widget _buildDiscoveryState() {
    final visualState = switch (_view) {
      _ManualDiscoveryView.searching => CameraDiscoveryVisualState.searching,
      _ManualDiscoveryView.notFound => CameraDiscoveryVisualState.notFound,
      _ManualDiscoveryView.error => CameraDiscoveryVisualState.failed,
    };
    return SizedBox(
      key: ValueKey('onvif_manual_${_view.name}'),
      height: 230,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CameraDiscoveryAnimation(
              key: const ValueKey('onvif_manual_discovery_animation'),
              state: visualState,
              size: 158,
              showDevice: _view != _ManualDiscoveryView.searching,
            ),
            if (_message != null) ...[
              const SizedBox(height: 10),
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 310),
                child: Text(
                  _message!,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 12.5,
                    fontWeight: FontWeight.w700,
                    height: 1.45,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget? _buildFooter() {
    return switch (_view) {
      _ManualDiscoveryView.searching => null,
      _ManualDiscoveryView.notFound || _ManualDiscoveryView.error => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AppSheetPrimaryButton(
            key: const ValueKey('onvif_manual_retry_button'),
            label: '重新搜索',
            onTap: () => unawaited(_search()),
          ),
        ],
      ),
    };
  }
}

String _discoveryErrorMessage(DeviceException error) {
  return switch (error.code) {
    'forbidden' || 'permission_denied' => '当前账号没有添加摄像头的权限。',
    'onvif_discovery_unavailable' => '暂时无法连接摄像头，请检查网络后重试。',
    _ => '暂时无法搜索摄像头，请稍后重试。',
  };
}
