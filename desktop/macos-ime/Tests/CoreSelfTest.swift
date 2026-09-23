import Foundation

@main
enum CoreSelfTest {
    static func main() throws {
        guard CommandLine.arguments.count == 2 else {
            throw TransliterationError.invalidMap("repository root argument is required")
        }
        let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        let assetDirectory = root.appendingPathComponent(
            "android/ime-app/src/main/assets/nepa-translit", isDirectory: true
        )
        let cases: [(String, [(String, String)])] = [
            ("npi-Latn-Deva-v1.json", [
                ("namaste", "नमस्ते"), ("nepaal", "नेपाल"), ("raamro", "राम्रो"),
            ]),
            ("new-Latn-Newa-v1.json", [
                ("namaste", "𑐣𑐩𑐳𑑂𑐟𑐾"), ("nh", "𑐤"),
            ]),
            ("lif-Latn-Limb-v1.json", [
                ("kepa", "ᤁᤧᤐ"), ("gyan", "ᤝ"), ("tra", "ᤞ"),
            ]),
        ]
        for (asset, vectors) in cases {
            let engine = try TransliterationEngine(
                url: assetDirectory.appendingPathComponent(asset)
            )
            for (roman, expected) in vectors {
                let actual = engine.transliterate(roman)
                guard actual == expected else {
                    fatalError("\(asset): \(roman) expected \(expected), got \(actual)")
                }
            }
        }

        let engine = try TransliterationEngine(
            url: assetDirectory.appendingPathComponent("npi-Latn-Deva-v1.json")
        )
        let composer = DesktopComposer(engine: engine, candidateWindowEnabled: true)
        composer.append("namaste")
        guard composer.snapshot().candidates == ["नमस्ते", "namaste"] else {
            fatalError("candidate contract failed")
        }
        guard composer.toggleCandidateWindow() == false,
              composer.snapshot().preedit == "नमस्ते" else {
            fatalError("candidate toggle destroyed composition")
        }
        composer.moveSelection(1)
        guard composer.commit() == "namaste" else {
            fatalError("literal candidate commit failed")
        }
        print("macos_phonetic_core=ok profiles=3")
    }
}
