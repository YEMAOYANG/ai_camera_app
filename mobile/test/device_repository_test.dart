import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/devices/application/device_repository.dart';
import 'package:warm_sight/src/features/devices/domain/device_models.dart';

void main() {
  test('devices filters out unbound cameras from management lists', () async {
    final repository = DeviceRepository(
      apiClient: ApiClient(
        _dioFor({
          '/devices': {
            'ok': true,
            'devices': [
              _device(id: 'active', status: 'online'),
              _device(id: 'removed', status: 'unbound', unboundAt: 123),
            ],
          },
        }),
      ),
    );

    final devices = await repository.devices();

    expect(devices.map((device) => device.id), ['active']);
  });

  test('unbindDevice parses backend fallback default device', () async {
    final repository = DeviceRepository(
      apiClient: ApiClient(
        _dioFor({
          '/devices/removed/unbind': {
            'ok': true,
            'device': _device(id: 'removed', status: 'unbound', unboundAt: 123),
            'defaultDevice': _device(id: 'fallback', status: 'online'),
          },
        }),
      ),
    );

    final result = await repository.unbindDevice('removed');

    expect(result.device.id, 'removed');
    expect(result.device.status, 'unbound');
    expect(result.defaultDevice?.id, 'fallback');
  });

  test('development camera candidates are marked as mock source', () async {
    final repository = DeviceRepository(apiClient: ApiClient(_dioFor({})));

    final candidates = await repository.discoverNearbyCameraCandidates();

    expect(candidates, isNotEmpty);
    expect(
      candidates.every(
        (candidate) => candidate.source == CameraDiscoveryCandidateSource.mock,
      ),
      isTrue,
    );
  });

  test(
    'discoveryStatuses maps already-bound candidates before connect',
    () async {
      final repository = DeviceRepository(
        apiClient: ApiClient(
          _dioFor({
            '/devices/discovery-status': {
              'ok': true,
              'candidates': [
                {
                  'id': 'camera-a',
                  'bindingCode': 'BIND-A',
                  'bindingState': 'boundToAnotherFamily',
                  'isConnectable': false,
                  'disabledReason': '已被其他家庭绑定',
                },
                {
                  'id': 'camera-b',
                  'bindingCode': 'BIND-B',
                  'bindingState': 'available',
                  'isConnectable': true,
                },
              ],
            },
          }),
        ),
      );

      final enriched = await repository.discoveryStatuses(const [
        DiscoveredCameraCandidate(
          id: 'camera-a',
          displayName: '暖瞳摄像头',
          bindingCode: 'BIND-A',
          signalStrength: 80,
          status: 'ready',
        ),
        DiscoveredCameraCandidate(
          id: 'camera-b',
          displayName: '暖瞳摄像头',
          bindingCode: 'BIND-B',
          signalStrength: 70,
          status: 'ready',
        ),
      ]);

      expect(enriched.first.canSelect, isFalse);
      expect(enriched.first.isOwnedByAnotherFamily, isTrue);
      expect(enriched.first.disabledReason, '已被其他家庭绑定');
      expect(enriched.last.canSelect, isTrue);
    },
  );
}

Dio _dioFor(Map<String, Object?> responses) {
  final dio = Dio(BaseOptions(baseUrl: 'https://example.test'));
  dio.interceptors.add(
    InterceptorsWrapper(
      onRequest: (options, handler) {
        final data = responses[options.path];
        if (data == null) {
          handler.reject(
            DioException(
              requestOptions: options,
              response: Response(
                requestOptions: options,
                statusCode: 404,
                data: {'message': 'not found'},
              ),
            ),
          );
          return;
        }
        handler.resolve(Response(requestOptions: options, data: data));
      },
    ),
  );
  return dio;
}

Map<String, Object?> _device({
  required String id,
  required String status,
  int? unboundAt,
}) {
  return {
    'id': id,
    'familyId': 'family_test',
    'bindingCode': 'binding_$id',
    'name': '暖瞳摄像头',
    'wakeName': '小暖',
    'location': '儿童房',
    'status': status,
    'isDefault': id == 'fallback' || id == 'active',
    'createdAt': 1,
    'updatedAt': 2,
    'unboundAt': unboundAt,
  };
}
