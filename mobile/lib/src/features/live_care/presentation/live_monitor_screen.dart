import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/live_care/application/camera_repository.dart';
import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

class LiveMonitorScreen extends ConsumerStatefulWidget {
  const LiveMonitorScreen({super.key});

  @override
  ConsumerState<LiveMonitorScreen> createState() => _LiveMonitorScreenState();
}

class _LiveMonitorScreenState extends ConsumerState<LiveMonitorScreen> {
  final _renderer = RTCVideoRenderer();
  RTCPeerConnection? _peerConnection;
  WebSocket? _signalingSocket;
  var _initializing = true;
  var _connected = false;
  var _muted = false;
  String _message = '正在连接实时画面';

  @override
  void initState() {
    super.initState();
    unawaited(_enterMonitorMode());
  }

  @override
  void dispose() {
    unawaited(_leaveMonitorMode());
    super.dispose();
  }

  Future<void> _enterMonitorMode() async {
    await SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
    await SystemChrome.setPreferredOrientations([
      DeviceOrientation.landscapeLeft,
      DeviceOrientation.landscapeRight,
    ]);
    await _renderer.initialize();
    if (!mounted) return;
    await _connect();
  }

  Future<void> _leaveMonitorMode() async {
    await _disconnect();
    await _renderer.dispose();
    await SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
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

  Future<void> _reconnect() async {
    await _disconnect();
    if (!mounted) return;
    await _connect();
  }

  void _toggleMute() {
    setState(() => _muted = !_muted);
    _renderer.muted = _muted;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        children: [
          Positioned.fill(
            child: RTCVideoView(
              _renderer,
              objectFit: RTCVideoViewObjectFit.RTCVideoViewObjectFitContain,
            ),
          ),
          if (_initializing || !_connected)
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.54),
                ),
                child: Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (_initializing)
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
                      Text(
                        _message,
                        style: const TextStyle(
                          color: Colors.white,
                          fontFamily: AppTypography.systemFont,
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          Positioned(
            left: 18,
            right: 18,
            top: 12,
            child: SafeArea(
              bottom: false,
              child: Row(
                children: [
                  _MonitorIconButton(
                    icon: Icons.close,
                    onTap: () => context.go(AppRoute.live.path),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          '实时看护',
                          style: TextStyle(
                            color: Colors.white,
                            fontFamily: AppTypography.systemFont,
                            fontSize: 18,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          _connected ? '画面传输中' : _message,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.72),
                            fontFamily: AppTypography.systemFont,
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                  ),
                  StatusChip(
                    label: _connected ? '在线' : '连接中',
                    tone: _connected ? StatusTone.success : StatusTone.warning,
                  ),
                ],
              ),
            ),
          ),
          Positioned(
            left: 18,
            right: 18,
            bottom: 18,
            child: SafeArea(
              top: false,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  _MonitorActionButton(
                    icon: Icons.photo_camera_outlined,
                    label: '截图',
                    onTap: () => _showToast(context, '已保存当前画面'),
                  ),
                  const SizedBox(width: 12),
                  _MonitorActionButton(
                    icon: _muted
                        ? Icons.volume_off_outlined
                        : Icons.volume_up_outlined,
                    label: _muted ? '打开声音' : '静音',
                    onTap: _toggleMute,
                  ),
                  const SizedBox(width: 12),
                  _MonitorActionButton(
                    icon: Icons.refresh_outlined,
                    label: '重连',
                    onTap: _reconnect,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _MonitorIconButton extends StatelessWidget {
  const _MonitorIconButton({required this.icon, required this.onTap});

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white.withValues(alpha: 0.13),
      borderRadius: BorderRadius.circular(AppRadii.full),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppRadii.full),
        onTap: onTap,
        child: SizedBox(
          width: 42,
          height: 42,
          child: Icon(icon, color: Colors.white, size: 21),
        ),
      ),
    );
  }
}

class _MonitorActionButton extends StatelessWidget {
  const _MonitorActionButton({
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
      color: Colors.white.withValues(alpha: 0.14),
      borderRadius: BorderRadius.circular(18),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
          child: Row(
            children: [
              Icon(icon, color: Colors.white, size: 18),
              const SizedBox(width: 8),
              Text(
                label,
                style: const TextStyle(
                  color: Colors.white,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

void _showToast(BuildContext context, String message) {
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(content: Text(message), behavior: SnackBarBehavior.floating),
  );
}
