import Foundation

enum TransliterationError: Error {
    case invalidMap(String)
}

struct TransliterationAsset: Decodable {
    let algorithm: String
    let map_id: String
    let language: String
    let output_script: String
    let virama: String
    let explicit_virama: String
    let final_consonant: String
    let consonants: [String: String]
    let independent_vowels: [String: String]
    let vowel_signs: [String: String]
    let standalone: [String: String]
    let final_forms: [String: String]
    let words: [String: String]
}

final class TransliterationEngine {
    private static let maxRomanKey = 8
    private let asset: TransliterationAsset

    init(url: URL) throws {
        let data = try Data(contentsOf: url)
        asset = try JSONDecoder().decode(TransliterationAsset.self, from: data)
        guard asset.algorithm == "greedy-syllable-v1" else {
            throw TransliterationError.invalidMap("unsupported algorithm")
        }
        guard ["inherent", "virama", "final_form"].contains(asset.final_consonant) else {
            throw TransliterationError.invalidMap("invalid final_consonant")
        }
        let tables = [
            asset.consonants, asset.independent_vowels, asset.vowel_signs,
            asset.standalone, asset.final_forms, asset.words,
        ]
        guard tables.allSatisfy({ table in
            table.keys.allSatisfy { !$0.isEmpty && $0.count <= Self.maxRomanKey }
        }) else {
            throw TransliterationError.invalidMap("invalid Roman key")
        }
        if asset.final_consonant == "final_form" {
            guard asset.virama.isEmpty, asset.explicit_virama.isEmpty,
                  !asset.final_forms.isEmpty else {
                throw TransliterationError.invalidMap("invalid final-form map")
            }
        } else if asset.virama.isEmpty {
            throw TransliterationError.invalidMap("missing virama")
        }
    }

    private func longest(_ table: [String: String], _ text: String, _ offset: Int) -> String? {
        let characters = Array(text)
        let limit = min(Self.maxRomanKey, characters.count - offset)
        guard limit > 0 else { return nil }
        for length in stride(from: limit, through: 1, by: -1) {
            let candidate = String(characters[offset..<(offset + length)])
            if table[candidate] != nil { return candidate }
        }
        return nil
    }

    func transliterate(_ text: String) -> String {
        guard !text.isEmpty else { return "" }
        if let word = asset.words[text] { return word }
        let input = Array(text)
        var output = ""
        var position = 0
        while position < input.count {
            if let key = longest(asset.consonants, text, position) {
                let after = position + key.count
                let coda = asset.final_forms[key]
                let closing = asset.final_consonant == "final_form"
                    && coda != nil
                    && longest(asset.vowel_signs, text, after) == nil
                output += closing ? coda! : asset.consonants[key]!
                position = after
                if closing { continue }
                if let vowel = longest(asset.vowel_signs, text, position) {
                    output += asset.vowel_signs[vowel]!
                    position += vowel.count
                } else if !asset.explicit_virama.isEmpty
                            && String(input[position...]).hasPrefix(asset.explicit_virama) {
                    output += asset.virama
                    position += asset.explicit_virama.count
                } else if asset.final_consonant == "final_form" {
                    continue
                } else if position >= input.count && asset.final_consonant == "inherent" {
                    continue
                } else {
                    output += asset.virama
                }
                continue
            }
            if let vowel = longest(asset.independent_vowels, text, position) {
                output += asset.independent_vowels[vowel]!
                position += vowel.count
                continue
            }
            if let standalone = longest(asset.standalone, text, position) {
                output += asset.standalone[standalone]!
                position += standalone.count
                continue
            }
            output.append(input[position])
            position += 1
        }
        return output.precomposedStringWithCanonicalMapping
    }
}

struct CompositionSnapshot {
    let roman: String
    let preedit: String
    let candidates: [String]
    let selectedIndex: Int
    let candidateWindowEnabled: Bool

    var candidateWindowVisible: Bool {
        candidateWindowEnabled && !roman.isEmpty && !candidates.isEmpty
    }

    var selectedCandidate: String {
        candidates.isEmpty ? "" : candidates[selectedIndex]
    }
}

final class DesktopComposer {
    private let engine: TransliterationEngine
    private(set) var roman = ""
    private(set) var selectedIndex = 0
    private(set) var candidateWindowEnabled: Bool

    init(engine: TransliterationEngine, candidateWindowEnabled: Bool) {
        self.engine = engine
        self.candidateWindowEnabled = candidateWindowEnabled
    }

    func snapshot() -> CompositionSnapshot {
        let preedit = roman.isEmpty ? "" : engine.transliterate(roman)
        let candidates = roman.isEmpty ? [] : (preedit == roman ? [preedit] : [preedit, roman])
        let selected = min(selectedIndex, max(0, candidates.count - 1))
        return CompositionSnapshot(
            roman: roman, preedit: preedit, candidates: candidates,
            selectedIndex: selected, candidateWindowEnabled: candidateWindowEnabled
        )
    }

    func append(_ text: String) {
        guard roman.count + text.count <= 128 else { return }
        roman += text
        selectedIndex = 0
    }

    func backspace() {
        if !roman.isEmpty { roman.removeLast() }
        selectedIndex = 0
    }

    func moveSelection(_ delta: Int) {
        let count = snapshot().candidates.count
        guard count > 0 else { return }
        selectedIndex = (selectedIndex + delta % count + count) % count
    }

    func select(_ index: Int) {
        if snapshot().candidates.indices.contains(index) { selectedIndex = index }
    }

    func commit(literal: Bool = false) -> String {
        let value = literal ? roman : snapshot().selectedCandidate
        reset()
        return value
    }

    func reset() {
        roman = ""
        selectedIndex = 0
    }

    func toggleCandidateWindow() -> Bool {
        candidateWindowEnabled.toggle()
        return candidateWindowEnabled
    }
}

