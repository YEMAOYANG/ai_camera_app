import Flutter
import UIKit

class SceneDelegate: FlutterSceneDelegate {
}

final class GuardianFlutterViewController: FlutterViewController {
  private var displayGeometry: DisplayGeometryStream?

  override func viewDidLoad() {
    super.viewDidLoad()
    displayGeometry = DisplayGeometryStream(view: view, messenger: binaryMessenger)
  }

  override func viewDidLayoutSubviews() {
    super.viewDidLayoutSubviews()
    displayGeometry?.publish()
  }

  override func viewSafeAreaInsetsDidChange() {
    super.viewSafeAreaInsetsDidChange()
    displayGeometry?.publish()
  }
}

@MainActor
private final class DisplayGeometryStream: NSObject, @preconcurrency FlutterStreamHandler {
  private struct Geometry: Equatable {
    let size: CGSize
    let barEdge: String
    let foldable: Bool
    let divisions: [CGRect]
    let systemBarBottom: CGFloat?
  }

  private weak var view: UIView?
  private var sink: FlutterEventSink?
  private var lastGeometry: Geometry?
  private var hasHinge = false

  init(view: UIView, messenger: FlutterBinaryMessenger) {
    self.view = view
    super.init()
    FlutterEventChannel(
      name: "ai_camera_app/display_geometry", binaryMessenger: messenger
    ).setStreamHandler(self)
    #if compiler(>=6.4)
    if #available(iOS 27.1, *) {
      view.registerForTraitChanges(UITraitCollection.systemTraitsAffectingVerticalBarEdge) {
        [weak self] (_: UIView, _: UITraitCollection) in
        self?.publish()
      }
      view.addInteraction(UIHingeInteraction { [weak self, weak view] _, update in
        self?.hasHinge = update.hinge != nil
        // Query again after UIKit lays out the view in the new pose.
        view?.setNeedsLayout()
        self?.publish()
      })
    }
    #endif
  }

  func onListen(withArguments arguments: Any?, eventSink events: @escaping FlutterEventSink)
    -> FlutterError? {
    sink = events
    lastGeometry = nil
    publish()
    return nil
  }

  func onCancel(withArguments arguments: Any?) -> FlutterError? {
    sink = nil
    lastGeometry = nil
    return nil
  }

  func publish() {
    guard let sink, let view, view.window != nil, !view.bounds.isEmpty else { return }
    var divisions: [CGRect] = []
    var barEdge = "none"
    var systemBarBottom: CGFloat?
    #if compiler(>=6.4)
    if #available(iOS 27.1, *) {
      divisions = view.reservedRegions(kind: .division).map(\.frame)
      let isRTL = view.effectiveUserInterfaceLayoutDirection == .rightToLeft
      switch view.traitCollection.verticalBarEdge {
      case .leading: barEdge = isRTL ? "right" : "left"
      case .trailing: barEdge = isRTL ? "left" : "right"
      default: break
      }
      if barEdge != "none", let scene = view.window?.windowScene {
        let isLeft = barEdge == "left"
        let inset = isLeft ? view.safeAreaInsets.left : view.safeAreaInsets.right
        let lane = CGRect(
          x: isLeft ? view.bounds.minX : view.bounds.maxX - inset,
          y: view.bounds.minY,
          width: inset,
          height: view.bounds.height
        )
        var reserved = view.reservedRegions(kind: .occlusion).map(\.frame)
        if let frame = scene.statusBarManager?.statusBarFrame, !frame.isEmpty {
          reserved.append(view.convert(frame, from: scene.coordinateSpace))
        }
        systemBarBottom = reserved
          .map { $0.intersection(lane) }
          .filter { !$0.isEmpty }
          .map(\.maxY)
          .max()
      }
    }
    #endif
    let geometry = Geometry(
      size: view.bounds.size,
      barEdge: barEdge,
      foldable: hasHinge || barEdge != "none" || !divisions.isEmpty,
      divisions: divisions,
      systemBarBottom: systemBarBottom
    )
    guard geometry != lastGeometry else { return }
    lastGeometry = geometry
    var event: [String: Any] = [
      "width": geometry.size.width,
      "height": geometry.size.height,
      "barEdge": geometry.barEdge,
      "foldable": geometry.foldable,
      "divisions": geometry.divisions.map { [$0.minX, $0.minY, $0.width, $0.height] },
    ]
    if let systemBarBottom = geometry.systemBarBottom {
      event["systemBarBottom"] = systemBarBottom
    }
    sink(event)
  }
}
