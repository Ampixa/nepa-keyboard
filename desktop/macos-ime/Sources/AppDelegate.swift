import Cocoa
import InputMethodKit

final class NSManualApplication: NSApplication {
    private let nepaDelegate = AppDelegate()

    override init() {
        super.init()
        delegate = nepaDelegate
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
}

@main
final class AppDelegate: NSObject, NSApplicationDelegate {
    private(set) var server: IMKServer!
    private(set) var candidatesWindow: IMKCandidates!

    func applicationDidFinishLaunching(_ notification: Notification) {
        let connectionName = Bundle.main.object(
            forInfoDictionaryKey: "InputMethodConnectionName"
        ) as! String
        server = IMKServer(
            name: connectionName,
            bundleIdentifier: Bundle.main.bundleIdentifier!
        )
        candidatesWindow = IMKCandidates(
            server: server,
            panelType: kIMKSingleRowSteppingCandidatePanel,
            styleType: kIMKMain
        )
        candidatesWindow.setDismissesAutomatically(true)
        candidatesWindow.setAttributes([
            IMKCandidatesSendServerKeyEventFirst: true,
            NSAttributedString.Key.font.rawValue: NSFont.systemFont(ofSize: 20),
        ])
    }
}
