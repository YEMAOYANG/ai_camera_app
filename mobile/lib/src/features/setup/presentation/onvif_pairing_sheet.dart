import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/devices/application/device_repository.dart';
import 'package:warm_sight/src/features/devices/application/selected_device_controller.dart';
import 'package:warm_sight/src/features/devices/domain/device_models.dart';
import 'package:warm_sight/src/features/setup/application/camera_add_refresh.dart';
import 'package:warm_sight/src/features/setup/presentation/camera_discovery_animation.dart';
import 'package:warm_sight/src/shared/widgets/app_bottom_sheet.dart';
import 'package:warm_sight/src/shared/widgets/app_surface.dart';
import 'package:warm_sight/src/shared/widgets/app_text_field.dart';
import 'package:warm_sight/src/shared/widgets/app_toast.dart';

enum OnvifPairingOutcome { paired, rediscover }

Future<OnvifPairingOutcome?> showOnvifPairingSheet(
  BuildContext context, {
  required List<OnvifDiscoveryCandidate> candidates,
}) {
  return showAppBottomSheet<OnvifPairingOutcome>(
    context: context,
    maxHeightFactor: 0.72,
    child: OnvifPairingSheet(candidates: candidates),
  );
}

class OnvifPairingSheet extends ConsumerStatefulWidget {
  const OnvifPairingSheet({required this.candidates, super.key});

  final List<OnvifDiscoveryCandidate> candidates;

  @override
  ConsumerState<OnvifPairingSheet> createState() => _OnvifPairingSheetState();
}

class _OnvifPairingSheetState extends ConsumerState<OnvifPairingSheet> {
  final _nameController = TextEditingController();
  final _locationController = TextEditingController();

  var _selectedIndex = 0;
  var _showDetails = false;
  var _pairing = false;
  String? _nameError;
  String? _formError;

  OnvifDiscoveryCandidate get _selectedCandidate {
    return widget.candidates[_selectedIndex];
  }

  @override
  void dispose() {
    _nameController
      ..clear()
      ..dispose();
    _locationController
      ..clear()
      ..dispose();
    super.dispose();
  }

  void _openDetails() {
    final candidate = _selectedCandidate;
    _nameController.text = _candidateName(candidate);
    setState(() {
      _showDetails = true;
      _formError = null;
    });
  }

  void _returnToCandidates() {
    if (_pairing) return;
    setState(() {
      _showDetails = false;
      _nameError = null;
      _formError = null;
    });
  }

  Future<void> _pair() async {
    if (_pairing) return;
    final name = _nameController.text.trim();
    setState(() {
      _nameError = name.isEmpty ? '请输入设备名称' : null;
      _formError = null;
    });
    if (_nameError != null) return;

    setState(() => _pairing = true);
    try {
      final result = await ref
          .read(deviceRepositoryProvider)
          .pairOnvifDevice(
            discoveryToken: _selectedCandidate.discoveryToken,
            name: name,
            location: _locationController.text,
          );
      await selectDevice(ref, result.device.id);
      refreshCameraAfterAdd(ref);
      if (!mounted) return;
      showAppToast(context, '摄像头已添加');
      Navigator.of(context).pop(OnvifPairingOutcome.paired);
    } on DeviceException catch (error) {
      if (!mounted) return;
      if (_isExpiredDiscoveryToken(error.code)) {
        showAppToast(context, '设备信息已更新，正在重新搜索。');
        Navigator.of(context).pop(OnvifPairingOutcome.rediscover);
        return;
      }
      setState(() {
        _pairing = false;
        _formError = _pairingErrorMessage(error);
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _pairing = false;
        _formError = '连接失败，请确认摄像头和手机仍在同一网络。';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    final desiredHeight = _showDetails
        ? (size.height * 0.64).clamp(480.0, 560.0)
        : (size.height * 0.53).clamp(390.0, 480.0);
    return AnimatedSize(
      duration: AppMotion.duration(context, 180),
      alignment: Alignment.bottomCenter,
      curve: Curves.easeOutCubic,
      child: SizedBox(
        height: desiredHeight,
        child: AnimatedSwitcher(
          duration: AppMotion.duration(context, 180),
          child: _showDetails ? _buildDetailsStep() : _buildCandidateStep(),
        ),
      ),
    );
  }

  Widget _buildCandidateStep() {
    return AppBottomSheetBody(
      key: const ValueKey('onvif_candidate_step'),
      title: '发现待添加设备：${widget.candidates.length} 个',
      subtitle: '已在当前家庭网络中发现可添加的摄像头',
      footer: AppSheetPrimaryButton(
        key: const ValueKey('onvif_add_button'),
        label: '添加',
        onTap: _openDetails,
      ),
      child: widget.candidates.length == 1
          ? _SingleOnvifCandidate(candidate: _selectedCandidate)
          : Column(
              children: [
                for (
                  var index = 0;
                  index < widget.candidates.length;
                  index++
                ) ...[
                  _OnvifCandidateTile(
                    candidate: widget.candidates[index],
                    selected: _selectedIndex == index,
                    onTap: () => setState(() => _selectedIndex = index),
                  ),
                  if (index != widget.candidates.length - 1)
                    const SizedBox(height: 8),
                ],
              ],
            ),
    );
  }

  Widget _buildDetailsStep() {
    final candidate = _selectedCandidate;
    return AppBottomSheetBody(
      key: const ValueKey('onvif_details_step'),
      title: '添加 ${_candidateName(candidate)}',
      subtitle: '确认设备名称和所在位置，点击后自动连接。',
      footer: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AppSheetPrimaryButton(
            key: const ValueKey('onvif_pair_button'),
            label: _pairing ? '正在添加' : '一键添加',
            loading: _pairing,
            onTap: _pairing ? null : _pair,
          ),
          const SizedBox(height: 8),
          AppSheetSecondaryButton(
            label: '返回设备列表',
            onTap: _pairing ? null : _returnToCandidates,
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _PairingDeviceSummary(candidate: candidate),
          const SizedBox(height: 16),
          AppTextField(
            key: const ValueKey('onvif_name_field'),
            label: '设备名称',
            icon: Icons.videocam_outlined,
            controller: _nameController,
            hintText: '例如 儿童房摄像头',
            errorText: _nameError,
            onChanged: (_) {
              if (_nameError != null || _formError != null) {
                setState(() {
                  _nameError = null;
                  _formError = null;
                });
              }
            },
          ),
          const SizedBox(height: 13),
          AppTextField(
            key: const ValueKey('onvif_location_field'),
            label: '所在位置（选填）',
            icon: Icons.home_outlined,
            controller: _locationController,
            hintText: '例如 儿童房',
          ),
          AnimatedSwitcher(
            duration: AppMotion.duration(context, 160),
            child: _formError == null
                ? const SizedBox.shrink()
                : Padding(
                    key: ValueKey(_formError),
                    padding: const EdgeInsets.only(top: 12),
                    child: Text(
                      _formError!,
                      style: const TextStyle(
                        color: AppColors.danger,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 12.5,
                        fontWeight: FontWeight.w700,
                        height: 1.35,
                      ),
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

class _SingleOnvifCandidate extends StatelessWidget {
  const _SingleOnvifCandidate({required this.candidate});

  final OnvifDiscoveryCandidate candidate;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CameraDeviceGlyph(
              size: 94,
              statusLightColor: AppColors.success,
            ),
            const SizedBox(height: 14),
            Text(
              _candidateName(candidate),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 18,
                fontWeight: FontWeight.w900,
              ),
            ),
            const SizedBox(height: 5),
            Text(
              candidate.displayModel,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 12.5,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 12),
            _CapabilitySummary(capabilities: candidate.capabilities),
          ],
        ),
      ),
    );
  }
}

class _OnvifCandidateTile extends StatelessWidget {
  const _OnvifCandidateTile({
    required this.candidate,
    required this.selected,
    required this.onTap,
  });

  final OnvifDiscoveryCandidate candidate;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      key: ValueKey('onvif_candidate_${candidate.dedupeKey}'),
      onTap: onTap,
      color: selected ? AppColors.brandSageWash : AppColors.surfaceElevated,
      borderColor: selected
          ? AppColors.brandSage.withValues(alpha: 0.36)
          : AppColors.borderSoft,
      radius: AppRadii.cardLarge,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      child: Row(
        children: [
          const CameraDeviceGlyph(
            size: 54,
            compact: true,
            statusLightColor: AppColors.success,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _candidateName(candidate),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 15,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  candidate.displayModel,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
          Icon(
            selected
                ? Icons.check_circle_rounded
                : Icons.radio_button_unchecked_rounded,
            color: selected ? AppColors.brandSage : AppColors.subtle,
            size: 20,
          ),
        ],
      ),
    );
  }
}

class _PairingDeviceSummary extends StatelessWidget {
  const _PairingDeviceSummary({required this.candidate});

  final OnvifDiscoveryCandidate candidate;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      color: AppColors.brandSageWash.withValues(alpha: 0.72),
      borderColor: AppColors.brandSage.withValues(alpha: 0.16),
      radius: AppRadii.cardMedium,
      padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 11),
      child: Row(
        children: [
          const CameraDeviceGlyph(
            size: 44,
            compact: true,
            statusLightColor: AppColors.success,
          ),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _candidateName(candidate),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 14,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  '${candidate.displayModel} · 已发现',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 11.5,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _CapabilitySummary extends StatelessWidget {
  const _CapabilitySummary({required this.capabilities});

  final OnvifDeviceCapabilities capabilities;

  @override
  Widget build(BuildContext context) {
    final labels = <String>[
      if (capabilities.rtsp) '视频流',
      if (capabilities.audio) '音频',
      if (capabilities.ptz) '云台',
    ];
    if (labels.isEmpty) labels.add('可连接');
    return Wrap(
      alignment: WrapAlignment.center,
      spacing: 7,
      runSpacing: 7,
      children: [
        for (final label in labels)
          DecoratedBox(
            decoration: BoxDecoration(
              color: AppColors.brandSageWash,
              borderRadius: BorderRadius.circular(AppRadii.full),
              border: Border.all(
                color: AppColors.brandSage.withValues(alpha: 0.14),
              ),
            ),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
              child: Text(
                label,
                style: const TextStyle(
                  color: AppColors.brandSage,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 11,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
          ),
      ],
    );
  }
}

String _candidateName(OnvifDiscoveryCandidate candidate) {
  final name = candidate.displayName.trim();
  final model = candidate.displayModel.trim();
  final normalizedName = name.toLowerCase();
  if (name.isEmpty ||
      normalizedName == model.toLowerCase() ||
      normalizedName.contains('onvif') ||
      normalizedName.contains('rtsp')) {
    return '智能摄像机';
  }
  return name;
}

bool _isExpiredDiscoveryToken(String code) {
  return code == 'onvif_discovery_token_invalid' ||
      code == 'onvif_discovery_token_expired';
}

String _pairingErrorMessage(DeviceException error) {
  return switch (error.code) {
    'onvif_auth_failed' => '设备自动认证失败，设备凭据可能已变化。',
    'onvif_credentials_unavailable' => '当前摄像头接入方式尚未配置。',
    'onvif_rtsp_unavailable' => '已验证设备，但实时画面暂时不可用。',
    'device_already_bound' => '这台摄像头已被其他家庭添加。',
    'onvif_discovery_unavailable' => '暂时无法连接设备发现服务，请稍后再试。',
    _ => '连接失败，请确认摄像头和手机仍在同一网络。',
  };
}
