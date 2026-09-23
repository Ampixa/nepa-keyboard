import Cocoa
import InputMethodKit

private let notFoundRange = NSRange(location: NSNotFound, length: NSNotFound)

@objc(NepaInputController)
final class NepaInputController: IMKInputController {
    private static let settingKey = "candidateWindowEnabled"
    private let composer: DesktopComposer

    override init!(server: IMKServer!, delegate: Any!, client inputClient: Any!) {
        let profileURL = Bundle.main.url(forResource: "profile", withExtension: "json")!
        let profileData = try! Data(contentsOf: profileURL)
        let profile = try! JSONSerialization.jsonObject(with: profileData) as! [String: String]
        let assetURL = Bundle.main.url(
            forResource: profile["asset_name"]!, withExtension: nil
        )!
        let defaults = UserDefaults.standard
        let enabled = defaults.object(forKey: Self.settingKey) == nil
            ? true
            : defaults.bool(forKey: Self.settingKey)
        composer = DesktopComposer(
            engine: try! TransliterationEngine(url: assetURL),
            candidateWindowEnabled: enabled
        )
        super.init(server: server, delegate: delegate, client: inputClient)
    }

    override func recognizedEvents(_ sender: Any!) -> Int {
        Int(NSEvent.EventTypeMask.keyDown.rawValue)
    }

    override func handle(_ event: NSEvent!, client sender: Any!) -> Bool {
        guard event.type == .keyDown, let client = sender as? IMKTextInput else {
            return false
        }
        let flags = event.modifierFlags.intersection([.command, .control, .option])
        let key = event.charactersIgnoringModifiers ?? ""
        if flags.contains(.control), flags.contains(.option), key.lowercased() == "c" {
            toggleCandidateWindow(client)
            return true
        }
        if flags.contains(.command) || flags.contains(.control) || flags.contains(.option) {
            return false
        }

        let snapshot = composer.snapshot()
        switch event.keyCode {
        case 51: // Delete
            guard !snapshot.roman.isEmpty else { return false }
            composer.backspace()
            publish(client)
            return true
        case 53: // Escape: preserve exactly what the writer typed.
            guard !snapshot.roman.isEmpty else { return false }
            commit(client, literal: true)
            return true
        case 123, 126: // Left, Up
            guard !snapshot.roman.isEmpty else { return false }
            composer.moveSelection(-1)
            publish(client)
            return true
        case 124, 125, 48: // Right, Down, Tab
            guard !snapshot.roman.isEmpty else { return false }
            composer.moveSelection(1)
            publish(client)
            return true
        case 36, 76: // Return, keypad Enter
            guard !snapshot.roman.isEmpty else { return false }
            commit(client)
            return true
        case 49: // Space
            guard !snapshot.roman.isEmpty else { return false }
            commit(client, suffix: " ")
            return true
        case 18, 19: // 1, 2 select visible candidates.
            if snapshot.candidateWindowVisible {
                let index = event.keyCode == 18 ? 0 : 1
                if snapshot.candidates.indices.contains(index) {
                    composer.select(index)
                    commit(client)
                    return true
                }
            }
        default:
            break
        }

        if let character = event.characters,
           character.count == 1,
           let scalar = character.unicodeScalars.first,
           scalar.isASCII,
           (CharacterSet.alphanumerics.contains(scalar) || "_.:".contains(character)) {
            composer.append(character)
            publish(client)
            return true
        }
        if !snapshot.roman.isEmpty, let punctuation = event.characters,
           punctuation.count == 1 {
            commit(client, suffix: punctuation)
            return true
        }
        return false
    }

    override func candidates(_ sender: Any!) -> [Any]! {
        composer.snapshot().candidates
    }

    override func candidateSelected(_ candidateString: NSAttributedString!) {
        guard let index = composer.snapshot().candidates.firstIndex(
            of: candidateString.string
        ), let client = client() else { return }
        composer.select(index)
        commit(client)
    }

    override func composedString(_ sender: Any!) -> Any! {
        composer.snapshot().preedit
    }

    override func originalString(_ sender: Any!) -> NSAttributedString! {
        NSAttributedString(string: composer.snapshot().roman)
    }

    override func commitComposition(_ sender: Any!) {
        guard let client = sender as? IMKTextInput else {
            composer.reset()
            hideCandidates()
            return
        }
        commit(client)
    }

    override func deactivateServer(_ sender: Any!) {
        if let client = sender as? IMKTextInput, !composer.snapshot().roman.isEmpty {
            commit(client)
        } else {
            composer.reset()
            hideCandidates()
        }
        super.deactivateServer(sender)
    }

    override func menu() -> NSMenu! {
        let menu = NSMenu(title: "Nepa Phonetic")
        let item = NSMenuItem(
            title: "Show Suggestions Beside Cursor",
            action: #selector(toggleCandidateMenu(_:)),
            keyEquivalent: ""
        )
        item.target = self
        item.state = composer.candidateWindowEnabled ? .on : .off
        menu.addItem(item)
        return menu
    }

    @objc private func toggleCandidateMenu(_ sender: Any?) {
        guard let client = client() else { return }
        toggleCandidateWindow(client)
    }

    private func toggleCandidateWindow(_ client: IMKTextInput) {
        let enabled = composer.toggleCandidateWindow()
        UserDefaults.standard.set(enabled, forKey: Self.settingKey)
        publish(client)
    }

    private func commit(
        _ client: IMKTextInput, literal: Bool = false, suffix: String = ""
    ) {
        let value = composer.commit(literal: literal) + suffix
        client.insertText(value, replacementRange: notFoundRange)
        hideCandidates()
    }

    private func publish(_ client: IMKTextInput) {
        let snapshot = composer.snapshot()
        client.setMarkedText(
            snapshot.preedit,
            selectionRange: NSRange(location: snapshot.preedit.utf16.count, length: 0),
            replacementRange: notFoundRange
        )
        guard let appDelegate = NSApp.delegate as? AppDelegate else { return }
        appDelegate.candidatesWindow.setCandidateData(snapshot.candidates)
        if snapshot.candidateWindowVisible {
            appDelegate.candidatesWindow.update()
            appDelegate.candidatesWindow.show(kIMKLocateCandidatesBelowHint)
            if snapshot.candidates.indices.contains(snapshot.selectedIndex) {
                let candidate = snapshot.candidates[snapshot.selectedIndex]
                let identifier = appDelegate.candidatesWindow.candidateStringIdentifier(candidate)
                _ = appDelegate.candidatesWindow.selectCandidate(withIdentifier: identifier)
            }
        } else {
            appDelegate.candidatesWindow.hide()
        }
    }

    private func hideCandidates() {
        (NSApp.delegate as? AppDelegate)?.candidatesWindow.hide()
    }
}
