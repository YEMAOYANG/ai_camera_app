import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/theme/app_system_ui.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/live_care/application/camera_repository.dart';
import 'package:guardian_parent_app/src/features/live_care/domain/camera_models.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_surface.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_toast.dart';
import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

class LiveMonitorScreen extends ConsumerStatefulWidget {
  const LiveMonitorScreen({super.key});

  @override
  ConsumerState<LiveMonitorScreen> createState() => _LiveMonitorScreenState();
}

class _LiveMonitorScreenState extends ConsumerState<LiveMonitorScreen>
    with WidgetsBindingObserver {
  final _renderer = RTCVideoRenderer();
  RTCPeerConnection? _peerConnection;
  WebSocket? _signalingSocket;
  var _initializing = true;
  var _connected = false;
  var _landscapeMode = false;
  var _ptzSpeed = 4;
  String _message = '正在连接实时画面';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_enterMonitorMode());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _applyPortraitChromeStyle();
    unawaited(_leaveMonitorMode());
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && !_landscapeMode) {
      unawaited(_restorePortraitChrome());
    }
  }

  Future<void> _enterMonitorMode() async {
    await _restorePortraitChrome();
    await _renderer.initialize();
    if (!mounted) return;
    await _connect();
  }

  Future<void> _leaveMonitorMode() async {
    await _restoreAppChrome();
    await _disconnect();
    await _renderer.dispose();
    await _restoreAppChrome();
  }

  Future<void> _restorePortraitChrome() async {
    _applyPortraitChromeStyle();
    await SystemChrome.setEnabledSystemUIMode(
      SystemUiMode.manual,
      overlays: SystemUiOverlay.values,
    );
    await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
    _applyPortraitChromeStyle();
  }

  Future<void> _restoreAppChrome() async {
    SystemChrome.setSystemUIOverlayStyle(AppSystemUi.light());
    await SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
    SystemChrome.setSystemUIOverlayStyle(AppSystemUi.light());
  }

  void _applyPortraitChromeStyle() {
    SystemChrome.setSystemUIOverlayStyle(_portraitChromeStyle);
  }

  void _restorePortraitChromeAfterFrame() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _landscapeMode) return;
      unawaited(_restorePortraitChrome());
    });
    for (final delay in const [
      Duration(milliseconds: 180),
      Duration(milliseconds: 520),
    ]) {
      Future<void>.delayed(delay, () {
        if (!mounted || _landscapeMode) return;
        unawaited(_restorePortraitChrome());
      });
    }
  }

  Future<void> _connect() async {
    setState(() {
      _initializing = true;
      _connected = false;
      _message = '正在连接实时画面';
    });
    try {
      final session = await ref
          .read(cameraRepositoryProvider)
          .createWebRtcSession();
      final socket = await WebSocket.connect(session.signalingUrl);
      _signalingSocket = socket;

      final pc = await createPeerConnection({
        'sdpSemantics': 'unified-plan',
        'bundlePolicy': 'max-bundle',
        'rtcpMuxPolicy': 'require',
        'iceServers': [
          {
            'urls': [
              'stun:stun.cloudflare.com:3478',
              'stun:stun.l.google.com:19302',
            ],
          },
        ],
      });
      _peerConnection = pc;
      pc.onTrack = (event) {
        if (event.streams.isNotEmpty) {
          _renderer.srcObject = event.streams.first;
        }
      };
      pc.onConnectionState = (state) {
        if (!mounted) return;
        setState(() {
          _connected =
              state == RTCPeerConnectionState.RTCPeerConnectionStateConnected;
          if (state == RTCPeerConnectionState.RTCPeerConnectionStateFailed ||
              state ==
                  RTCPeerConnectionState.RTCPeerConnectionStateDisconnected) {
            _message = '实时画面连接中断';
          }
        });
      };
      pc.onIceCandidate = (candidate) {
        _sendSignalingMessage({
          'type': 'webrtc/candidate',
          'value': candidate.candidate ?? '',
        });
      };
      socket.listen(
        (event) => unawaited(_handleSignalingMessage(pc, event)),
        onDone: () {
          if (!mounted || _connected) return;
          setState(() => _message = '实时画面连接已断开');
        },
        onError: (_) {
          if (!mounted) return;
          setState(() {
            _connected = false;
            _message = '实时画面连接中断';
          });
        },
      );

      await pc.addTransceiver(
        kind: RTCRtpMediaType.RTCRtpMediaTypeVideo,
        init: RTCRtpTransceiverInit(direction: TransceiverDirection.RecvOnly),
      );
      await pc.addTransceiver(
        kind: RTCRtpMediaType.RTCRtpMediaTypeAudio,
        init: RTCRtpTransceiverInit(direction: TransceiverDirection.RecvOnly),
      );

      final offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      _sendSignalingMessage({'type': 'webrtc/offer', 'value': offer.sdp ?? ''});
      if (!mounted) return;
      setState(() {
        _initializing = false;
        _message = session.message;
      });
    } catch (_) {
      await _disconnect();
      if (!mounted) return;
      setState(() {
        _initializing = false;
        _connected = false;
        _message = '实时画面暂时无法连接，请稍后再试。';
      });
    }
  }

  Future<void> _handleSignalingMessage(
    RTCPeerConnection pc,
    dynamic raw,
  ) async {
    if (raw is! String || raw.trim().isEmpty) return;
    final message = jsonDecode(raw);
    if (message is! Map) return;
    final type = '${message['type'] ?? ''}';
    final value = '${message['value'] ?? ''}';
    if (type == 'webrtc/answer' && value.isNotEmpty) {
      await pc.setRemoteDescription(RTCSessionDescription(value, 'answer'));
      return;
    }
    if (type == 'webrtc/candidate' && value.isNotEmpty) {
      await pc.addCandidate(RTCIceCandidate(value, '0', 0));
      return;
    }
    if (type == 'error' && mounted) {
      setState(() {
        _connected = false;
        _message = '实时画面暂时无法连接，请稍后再试。';
      });
    }
  }

  void _sendSignalingMessage(Map<String, String> message) {
    final socket = _signalingSocket;
    if (socket == null) return;
    socket.add(jsonEncode(message));
  }

  Future<void> _disconnect() async {
    final socket = _signalingSocket;
    _signalingSocket = null;
    await socket?.close();
    final pc = _peerConnection;
    _peerConnection = null;
    if (pc == null) return;
    await pc.close();
    await pc.dispose();
  }

  Future<void> _movePtz(String direction) async {
    try {
      await ref
          .read(cameraRepositoryProvider)
          .movePtz(direction, step: _ptzSpeed);
      ref
        ..invalidate(cameraEventsProvider)
        ..invalidate(liveCareStatusProvider);
      if (mounted) _showToast(context, '云台命令已发送');
    } on CameraException catch (error) {
      if (mounted) _showToast(context, error.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final child = _landscapeMode
        ? _buildLandscapeMonitor(context)
        : _buildPortraitMonitor(context);

    return PopScope(
      canPop: !_landscapeMode,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop && _landscapeMode) {
          unawaited(_setLandscapeMode(false));
        }
      },
      child: child,
    );
  }

  Widget _buildPortraitMonitor(BuildContext context) {
    final status = ref.watch(liveCareStatusProvider);
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: _portraitChromeStyle,
      child: Scaffold(
        backgroundColor: AppColors.appBackgroundMid,
        body: SafeArea(
          child: CustomScrollView(
            slivers: [
              SliverToBoxAdapter(
                child: _MonitorHeader(message: _headerMessage),
              ),
              SliverToBoxAdapter(
                child: _PortraitVideoPanel(
                  renderer: _renderer,
                  connected: _connected,
                  initializing: _initializing,
                  message: _message,
                  onLandscape: () => unawaited(_setLandscapeMode(true)),
                ),
              ),
              SliverToBoxAdapter(
                child: _MonitorPtzPanel(
                  status: status,
                  speed: _ptzSpeed,
                  onMove: (direction) => unawaited(_movePtz(direction)),
                  onReset: () => unawaited(_movePtz('home')),
                  onSpeedChanged: (value) {
                    setState(() => _ptzSpeed = value.clamp(1, 8).toInt());
                  },
                ),
              ),
              const SliverToBoxAdapter(child: SizedBox(height: 28)),
            ],
          ),
        ),
      ),
    );
  }

  String get _headerMessage => _connected ? '画面传输中' : _message;

  Future<void> _setLandscapeMode(bool enabled) async {
    if (enabled) {
      SystemChrome.setSystemUIOverlayStyle(_landscapeChromeStyle);
      await SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
      await SystemChrome.setPreferredOrientations([
        DeviceOrientation.landscapeLeft,
        DeviceOrientation.landscapeRight,
      ]);
    } else {
      await _restorePortraitChrome();
    }
    if (!mounted) return;
    setState(() => _landscapeMode = enabled);
    if (!enabled) _restorePortraitChromeAfterFrame();
  }

  Widget _buildLandscapeMonitor(BuildContext context) {
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: _landscapeChromeStyle,
      child: Scaffold(
        backgroundColor: Colors.black,
        body: Stack(
          children: [
            Positioned.fill(child: _VideoLayer(renderer: _renderer)),
            if (_initializing || !_connected)
              Positioned.fill(
                child: _MonitorConnectionOverlay(
                  initializing: _initializing,
                  message: _message,
                ),
              ),
            Positioned(
              left: 18,
              top: 12,
              child: SafeArea(
                bottom: false,
                child: _LandscapeExitButton(
                  onTap: () => unawaited(_setLandscapeMode(false)),
                ),
              ),
            ),
            Positioned(
              right: 18,
              top: 18,
              child: SafeArea(
                bottom: false,
                child: StatusChip(
                  label: _connected ? '在线' : '连接中',
                  tone: _connected ? StatusTone.success : StatusTone.warning,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

final _portraitChromeStyle = AppSystemUi.light(
  statusBarColor: AppColors.appBackgroundMid,
  navigationBarColor: AppColors.appBackgroundMid,
);

final _landscapeChromeStyle = AppSystemUi.dark(
  statusBarColor: Colors.black,
  navigationBarColor: Colors.black,
);

class _MonitorHeader extends StatelessWidget {
  const _MonitorHeader({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
      child: Row(
        children: [
          _MonitorHeaderButton(
            icon: Icons.chevron_left_rounded,
            onTap: () => context.go(AppRoute.live.path),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '实时画面',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 22,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  message,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
          ),
          StatusChip(
            label: message == '画面传输中' ? '在线' : '连接中',
            tone: message == '画面传输中' ? StatusTone.success : StatusTone.warning,
          ),
        ],
      ),
    );
  }
}

class _MonitorHeaderButton extends StatelessWidget {
  const _MonitorHeaderButton({required this.icon, required this.onTap});

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white.withValues(alpha: 0.86),
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: SizedBox(
          width: 44,
          height: 44,
          child: Icon(icon, color: AppColors.ink, size: 26),
        ),
      ),
    );
  }
}

class _PortraitVideoPanel extends StatelessWidget {
  const _PortraitVideoPanel({
    required this.renderer,
    required this.connected,
    required this.initializing,
    required this.message,
    required this.onLandscape,
  });

  final RTCVideoRenderer renderer;
  final bool connected;
  final bool initializing;
  final String message;
  final VoidCallback onLandscape;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 14),
      child: AppSurface(
        color: const Color(0xFF0B1220),
        borderColor: Colors.white.withValues(alpha: 0.08),
        radius: 22,
        padding: EdgeInsets.zero,
        child: AspectRatio(
          aspectRatio: 16 / 9,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(22),
            child: Stack(
              children: [
                Positioned.fill(child: _VideoLayer(renderer: renderer)),
                if (initializing || !connected)
                  Positioned.fill(
                    child: _MonitorConnectionOverlay(
                      initializing: initializing,
                      message: message,
                    ),
                  ),
                Positioned(
                  right: 12,
                  bottom: 12,
                  child: _VideoOverlayButton(
                    icon: Icons.open_in_full_rounded,
                    label: '横屏',
                    onTap: onLandscape,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _VideoOverlayButton extends StatelessWidget {
  const _VideoOverlayButton({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.black.withValues(alpha: 0.44),
      borderRadius: BorderRadius.circular(13),
      child: InkWell(
        borderRadius: BorderRadius.circular(13),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, color: Colors.white, size: 18),
              const SizedBox(width: 6),
              Text(
                label,
                style: const TextStyle(
                  color: Colors.white,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _LandscapeExitButton extends StatelessWidget {
  const _LandscapeExitButton({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.black.withValues(alpha: 0.42),
      borderRadius: BorderRadius.circular(13),
      child: InkWell(
        borderRadius: BorderRadius.circular(13),
        onTap: onTap,
        child: const Padding(
          padding: EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.chevron_left_rounded, color: Colors.white, size: 24),
              SizedBox(width: 2),
              Text(
                '退出横屏',
                style: TextStyle(
                  color: Colors.white,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 13,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _VideoLayer extends StatelessWidget {
  const _VideoLayer({required this.renderer});

  final RTCVideoRenderer renderer;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: Colors.black,
      child: RTCVideoView(
        renderer,
        objectFit: RTCVideoViewObjectFit.RTCVideoViewObjectFitContain,
      ),
    );
  }
}

class _MonitorConnectionOverlay extends StatelessWidget {
  const _MonitorConnectionOverlay({
    required this.initializing,
    required this.message,
  });

  final bool initializing;
  final String message;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(color: Colors.black.withValues(alpha: 0.54)),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (initializing)
              const SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(
                  strokeWidth: 2.2,
                  color: Colors.white,
                ),
              )
            else
              const Icon(
                Icons.videocam_off_outlined,
                color: Colors.white,
                size: 34,
              ),
            const SizedBox(height: 14),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Text(
                message,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: Colors.white,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MonitorPtzPanel extends StatelessWidget {
  const _MonitorPtzPanel({
    required this.status,
    required this.speed,
    required this.onMove,
    required this.onReset,
    required this.onSpeedChanged,
  });

  final AsyncValue<LiveCareStatus> status;
  final int speed;
  final ValueChanged<String> onMove;
  final VoidCallback onReset;
  final ValueChanged<int> onSpeedChanged;

  @override
  Widget build(BuildContext context) {
    final care = status.asData?.value;
    final supported = care?.ptzAvailable == true;
    final enabled = supported && care?.isAvailable == true;
    final description = status.isLoading
        ? '正在同步设备能力。'
        : supported
        ? '可以在实时画面中轻微调整摄像头方向。'
        : '当前设备暂不支持远程调整方向，仍可正常查看画面和接收看护提醒。';

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 0),
      child: AppSurface(
        padding: const EdgeInsets.fromLTRB(18, 18, 18, 20),
        child: Column(
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text(
                    '云台控制',
                    style: TextStyle(
                      color: AppColors.ink,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 17,
                      fontWeight: FontWeight.w900,
                      letterSpacing: 0,
                    ),
                  ),
                ),
                StatusChip(
                  label: enabled ? '可控制' : '不可用',
                  tone: enabled ? StatusTone.success : StatusTone.neutral,
                ),
              ],
            ),
            const SizedBox(height: 6),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                description,
                style: const TextStyle(
                  color: AppColors.muted,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  height: 1.35,
                  letterSpacing: 0,
                ),
              ),
            ),
            const SizedBox(height: 24),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                _ResetButton(enabled: enabled, onTap: onReset),
                _PtzPad(enabled: enabled, onMove: onMove),
                _SpeedControl(
                  speed: speed,
                  enabled: enabled,
                  onChanged: onSpeedChanged,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _ResetButton extends StatelessWidget {
  const _ResetButton({required this.enabled, required this.onTap});

  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: enabled ? 1 : 0.34,
      child: InkWell(
        borderRadius: BorderRadius.circular(AppRadii.full),
        onTap: enabled ? onTap : null,
        child: SizedBox(
          width: 58,
          child: Column(
            children: [
              DecoratedBox(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(AppRadii.full),
                  border: Border.all(color: AppColors.border),
                ),
                child: const SizedBox(
                  width: 44,
                  height: 44,
                  child: Icon(
                    Icons.restart_alt_rounded,
                    color: AppColors.muted,
                    size: 24,
                  ),
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                '复位',
                style: TextStyle(
                  color: AppColors.muted,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PtzPad extends StatelessWidget {
  const _PtzPad({required this.enabled, required this.onMove});

  final bool enabled;
  final ValueChanged<String> onMove;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: enabled ? 1 : 0.34,
      child: SizedBox(
        width: 150,
        height: 150,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.surfaceStrong,
            shape: BoxShape.circle,
            border: Border.all(color: AppColors.border),
          ),
          child: Stack(
            children: [
              Align(
                alignment: Alignment.topCenter,
                child: _PtzButton(
                  icon: Icons.keyboard_arrow_up_rounded,
                  enabled: enabled,
                  onTap: () => onMove('up'),
                ),
              ),
              Align(
                alignment: Alignment.centerLeft,
                child: _PtzButton(
                  icon: Icons.keyboard_arrow_left_rounded,
                  enabled: enabled,
                  onTap: () => onMove('left'),
                ),
              ),
              Align(
                alignment: Alignment.center,
                child: InkWell(
                  borderRadius: BorderRadius.circular(AppRadii.full),
                  onTap: enabled ? () => onMove('home') : null,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: Colors.white,
                      shape: BoxShape.circle,
                      border: Border.all(color: AppColors.borderSoft),
                    ),
                    child: const SizedBox(width: 54, height: 54),
                  ),
                ),
              ),
              Align(
                alignment: Alignment.centerRight,
                child: _PtzButton(
                  icon: Icons.keyboard_arrow_right_rounded,
                  enabled: enabled,
                  onTap: () => onMove('right'),
                ),
              ),
              Align(
                alignment: Alignment.bottomCenter,
                child: _PtzButton(
                  icon: Icons.keyboard_arrow_down_rounded,
                  enabled: enabled,
                  onTap: () => onMove('down'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PtzButton extends StatelessWidget {
  const _PtzButton({
    required this.icon,
    required this.enabled,
    required this.onTap,
  });

  final IconData icon;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(AppRadii.full),
      onTap: enabled ? onTap : null,
      child: SizedBox(
        width: 48,
        height: 48,
        child: Icon(icon, size: 34, color: AppColors.muted),
      ),
    );
  }
}

class _SpeedControl extends StatelessWidget {
  const _SpeedControl({
    required this.speed,
    required this.enabled,
    required this.onChanged,
  });

  final int speed;
  final bool enabled;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: enabled ? 1 : 0.34,
      child: SizedBox(
        width: 58,
        child: Column(
          children: [
            _StepperButton(
              icon: Icons.add_rounded,
              enabled: enabled && speed < 8,
              onTap: () => onChanged(speed + 1),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Text(
                '$speed',
                style: const TextStyle(
                  color: AppColors.ink,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 18,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
            ),
            _StepperButton(
              icon: Icons.remove_rounded,
              enabled: enabled && speed > 1,
              onTap: () => onChanged(speed - 1),
            ),
            const SizedBox(height: 8),
            const Text(
              '转速',
              style: TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 12,
                fontWeight: FontWeight.w800,
                letterSpacing: 0,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StepperButton extends StatelessWidget {
  const _StepperButton({
    required this.icon,
    required this.enabled,
    required this.onTap,
  });

  final IconData icon;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(12),
      onTap: enabled ? onTap : null,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppColors.border),
        ),
        child: SizedBox(
          width: 46,
          height: 40,
          child: Icon(icon, color: AppColors.ink, size: 24),
        ),
      ),
    );
  }
}

void _showToast(BuildContext context, String message) {
  showAppToast(context, message);
}
