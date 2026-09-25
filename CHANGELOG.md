# Değişiklik günlüğü

## [Unreleased]

### Added

- LLM çağrısı öncesinde tam istem ve hedef önizlemesi; varsayılan etkileşimli onay.
- Etkileşimsiz otomasyon için açık `--onayli-gonder` seçeneği.
- Seçilmiş Git dosyalarında kişisel çıktı, yaygın sır ve kullanıcı yolu taraması; mevcut hook'u koruyan kurulum aracı.
- `baglam --kopyala` için hedef Git deposunda ignore/izlenme denetimi.

### Changed

- Örnek `llm.model` değeriyle otomatik özetleme erken ve anlaşılır hatayla durur.
- Bilinen sır kalıpları LLM'e gönderilen son istem üzerinde de temizlenir.

### Documentation

- Kodlama ajanları için `AGENTS.md` kılavuzu eklendi.
- README, mimari, yol haritası, teknik bilgi, plan ve görev belgeleri eklendi/güncellendi.
- Kişisel verilerin depoya girmemesi için `.gitignore` genişletildi.

## [0.1.0] - 2026-09-25

### Added

- Claude Code ve Codex JSONL oturumlarını, Antigravity Markdown artefaktlarını toplama.
- Okunabilir döküm, Bölüm/Cilt özetleri, elle özetleme ve `BAGLAM.md`.
- OpenAI uyumlu LLM uç noktası ve kişisel JSON ayarı.

### Known limitations

- Antigravity tam sohbet geçmişi desteklenmiyor; token hesabı yaklaşık.
