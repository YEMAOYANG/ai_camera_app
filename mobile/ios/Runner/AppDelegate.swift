import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  private let nativeDatePickerChannelName = "ai_camera_app/native_date_picker"

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    registerNativeDatePickerChannel()
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
  }

  private func registerNativeDatePickerChannel() {
    guard let registrar = registrar(forPlugin: "NativeDatePickerPlugin") else {
      return
    }

    let channel = FlutterMethodChannel(
      name: nativeDatePickerChannelName,
      binaryMessenger: registrar.messenger()
    )

    channel.setMethodCallHandler { [weak self] call, result in
      guard call.method == "pickDate" else {
        result(FlutterMethodNotImplemented)
        return
      }

      guard
        let arguments = call.arguments as? [String: Any],
        let initialValue = arguments["initialDate"] as? String,
        let minValue = arguments["minDate"] as? String,
        let maxValue = arguments["maxDate"] as? String,
        let initialDate = Self.parseDate(initialValue),
        let minDate = Self.parseDate(minValue),
        let maxDate = Self.parseDate(maxValue)
      else {
        result(FlutterError(code: "invalid_arguments", message: "日期参数不正确", details: nil))
        return
      }

      let title = arguments["title"] as? String ?? "选择日期"
      let localeIdentifier = Self.normalizedLocaleIdentifier(
        arguments["locale"] as? String ?? "zh_CN"
      )

      DispatchQueue.main.async {
        self?.presentNativeDatePicker(
          title: title,
          initialDate: initialDate,
          minDate: minDate,
          maxDate: maxDate,
          localeIdentifier: localeIdentifier,
          result: result
        )
      }
    }
  }

  private func presentNativeDatePicker(
    title: String,
    initialDate: Date,
    minDate: Date,
    maxDate: Date,
    localeIdentifier: String,
    result: @escaping FlutterResult
  ) {
    guard let presenter = Self.topViewController() else {
      result(FlutterError(code: "no_presenter", message: "无法打开日期选择器", details: nil))
      return
    }

    let controller = NativeDatePickerViewController(
      titleText: title,
      initialDate: initialDate,
      minDate: minDate,
      maxDate: maxDate,
      localeIdentifier: localeIdentifier
    )
    controller.modalPresentationStyle = .overFullScreen
    controller.modalTransitionStyle = .crossDissolve
    controller.onCancel = {
      result(nil)
    }
    controller.onConfirm = { date in
      result(Self.formatDate(date))
    }
    presenter.present(controller, animated: true)
  }

  private static func topViewController(
    from rootViewController: UIViewController? = UIApplication.shared.connectedScenes
      .compactMap { $0 as? UIWindowScene }
      .flatMap { $0.windows }
      .first { $0.isKeyWindow }?
      .rootViewController
  ) -> UIViewController? {
    if let navigationController = rootViewController as? UINavigationController {
      return topViewController(from: navigationController.visibleViewController)
    }
    if let tabController = rootViewController as? UITabBarController {
      return topViewController(from: tabController.selectedViewController)
    }
    if let presented = rootViewController?.presentedViewController {
      return topViewController(from: presented)
    }
    return rootViewController
  }

  private static func parseDate(_ value: String) -> Date? {
    formatter.date(from: value)
  }

  private static func formatDate(_ date: Date) -> String {
    formatter.string(from: date)
  }

  private static func normalizedLocaleIdentifier(_ value: String) -> String {
    switch value {
    case "zh_CN", "zh-Hans-CN":
      return "zh-Hans_CN"
    default:
      return value
    }
  }

  private static let formatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = TimeZone.current
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter
  }()
}

private final class NativeDatePickerViewController: UIViewController {
  var onCancel: (() -> Void)?
  var onConfirm: ((Date) -> Void)?

  private let titleText: String
  private let initialDate: Date
  private let minDate: Date
  private let maxDate: Date
  private let localeIdentifier: String
  private var selectedDate: Date

  init(
    titleText: String,
    initialDate: Date,
    minDate: Date,
    maxDate: Date,
    localeIdentifier: String
  ) {
    self.titleText = titleText
    self.initialDate = initialDate
    self.minDate = minDate
    self.maxDate = maxDate
    self.localeIdentifier = localeIdentifier
    self.selectedDate = initialDate
    super.init(nibName: nil, bundle: nil)
  }

  required init?(coder: NSCoder) {
    fatalError("init(coder:) has not been implemented")
  }

  override func viewDidLoad() {
    super.viewDidLoad()
    if #available(iOS 13.0, *) {
      overrideUserInterfaceStyle = .light
    }
    view.backgroundColor = UIColor.black.withAlphaComponent(0.24)
    view.tintColor = UIColor(red: 0.114, green: 0.212, blue: 0.365, alpha: 1.0)

    let container = UIView()
    container.translatesAutoresizingMaskIntoConstraints = false
    container.backgroundColor = UIColor(red: 0.973, green: 0.980, blue: 0.992, alpha: 1.0)
    container.layer.cornerRadius = 28
    container.layer.maskedCorners = [.layerMinXMinYCorner, .layerMaxXMinYCorner]
    container.clipsToBounds = true
    if #available(iOS 13.0, *) {
      container.overrideUserInterfaceStyle = .light
    }
    view.addSubview(container)

    let handle = UIView()
    handle.translatesAutoresizingMaskIntoConstraints = false
    handle.backgroundColor = UIColor(red: 0.808, green: 0.839, blue: 0.882, alpha: 1.0)
    handle.layer.cornerRadius = 2
    container.addSubview(handle)

    let titleLabel = UILabel()
    titleLabel.translatesAutoresizingMaskIntoConstraints = false
    titleLabel.text = titleText
    titleLabel.textColor = UIColor(red: 0.055, green: 0.094, blue: 0.157, alpha: 1.0)
    titleLabel.font = UIFont.systemFont(ofSize: 16, weight: .bold)
    titleLabel.textAlignment = .center
    container.addSubview(titleLabel)

    let cancelButton = UIButton(type: .system)
    cancelButton.translatesAutoresizingMaskIntoConstraints = false
    cancelButton.setTitle("取消", for: .normal)
    cancelButton.setTitleColor(UIColor(red: 0.388, green: 0.459, blue: 0.553, alpha: 1.0), for: .normal)
    cancelButton.titleLabel?.font = UIFont.systemFont(ofSize: 16, weight: .semibold)
    cancelButton.addTarget(self, action: #selector(cancel), for: .touchUpInside)
    container.addSubview(cancelButton)

    let confirmButton = UIButton(type: .system)
    confirmButton.translatesAutoresizingMaskIntoConstraints = false
    confirmButton.setTitle("确定", for: .normal)
    confirmButton.setTitleColor(UIColor(red: 0.114, green: 0.212, blue: 0.365, alpha: 1.0), for: .normal)
    confirmButton.titleLabel?.font = UIFont.systemFont(ofSize: 16, weight: .bold)
    confirmButton.addTarget(self, action: #selector(confirm), for: .touchUpInside)
    container.addSubview(confirmButton)

    let picker = UIDatePicker()
    picker.translatesAutoresizingMaskIntoConstraints = false
    picker.datePickerMode = .date
    picker.calendar = Calendar(identifier: .gregorian)
    picker.locale = Locale(identifier: localeIdentifier)
    picker.minimumDate = minDate
    picker.maximumDate = maxDate
    picker.date = initialDate
    picker.tintColor = UIColor(red: 0.114, green: 0.212, blue: 0.365, alpha: 1.0)
    picker.backgroundColor = .white
    var pickerHeight: CGFloat = 216
    if #available(iOS 14.0, *) {
      picker.preferredDatePickerStyle = .inline
      pickerHeight = 360
    } else if #available(iOS 13.4, *) {
      picker.preferredDatePickerStyle = .wheels
    }
    if #available(iOS 13.0, *) {
      picker.overrideUserInterfaceStyle = .light
    }
    picker.addTarget(self, action: #selector(dateChanged(_:)), for: .valueChanged)

    let pickerBox = UIView()
    pickerBox.translatesAutoresizingMaskIntoConstraints = false
    pickerBox.backgroundColor = .white
    pickerBox.layer.cornerRadius = 22
    pickerBox.clipsToBounds = true
    if #available(iOS 13.0, *) {
      pickerBox.overrideUserInterfaceStyle = .light
    }
    container.addSubview(pickerBox)
    pickerBox.addSubview(picker)

    NSLayoutConstraint.activate([
      container.leadingAnchor.constraint(equalTo: view.leadingAnchor),
      container.trailingAnchor.constraint(equalTo: view.trailingAnchor),
      container.bottomAnchor.constraint(equalTo: view.bottomAnchor),

      handle.topAnchor.constraint(equalTo: container.topAnchor, constant: 8),
      handle.centerXAnchor.constraint(equalTo: container.centerXAnchor),
      handle.widthAnchor.constraint(equalToConstant: 38),
      handle.heightAnchor.constraint(equalToConstant: 4),

      titleLabel.topAnchor.constraint(equalTo: container.topAnchor, constant: 22),
      titleLabel.centerXAnchor.constraint(equalTo: container.centerXAnchor),

      cancelButton.centerYAnchor.constraint(equalTo: titleLabel.centerYAnchor),
      cancelButton.leadingAnchor.constraint(equalTo: container.leadingAnchor, constant: 16),
      cancelButton.heightAnchor.constraint(equalToConstant: 44),

      confirmButton.centerYAnchor.constraint(equalTo: titleLabel.centerYAnchor),
      confirmButton.trailingAnchor.constraint(equalTo: container.trailingAnchor, constant: -16),
      confirmButton.heightAnchor.constraint(equalToConstant: 44),

      pickerBox.topAnchor.constraint(equalTo: titleLabel.bottomAnchor, constant: 18),
      pickerBox.leadingAnchor.constraint(equalTo: container.leadingAnchor, constant: 16),
      pickerBox.trailingAnchor.constraint(equalTo: container.trailingAnchor, constant: -16),
      pickerBox.heightAnchor.constraint(equalToConstant: pickerHeight),
      pickerBox.bottomAnchor.constraint(equalTo: container.safeAreaLayoutGuide.bottomAnchor, constant: -14),

      picker.leadingAnchor.constraint(equalTo: pickerBox.leadingAnchor),
      picker.trailingAnchor.constraint(equalTo: pickerBox.trailingAnchor),
      picker.topAnchor.constraint(equalTo: pickerBox.topAnchor),
      picker.bottomAnchor.constraint(equalTo: pickerBox.bottomAnchor),
    ])
  }

  @objc private func dateChanged(_ picker: UIDatePicker) {
    selectedDate = picker.date
  }

  @objc private func cancel() {
    dismiss(animated: true) { [onCancel] in
      onCancel?()
    }
  }

  @objc private func confirm() {
    let date = selectedDate
    dismiss(animated: true) { [onConfirm] in
      onConfirm?(date)
    }
  }
}
