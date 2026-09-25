# Görevler

`[ ]` açık, `[x]` tamamlandı.

## P0 — Veri güvenilirliği

- [ ] Gerçek, kişisel verisi temizlenmiş Claude Code ve Codex JSONL örnekleriyle parser testleri.
- [ ] Tekrarlı `topla → dokum → ozetle` çalıştırmasında çift Bölüm oluşmadığını doğrula.
- [ ] Döküm, özet ve `durum.json` yazımlarını atomik hâle getir.
- [x] Git index'i için kişisel yol ve yaygın sır taraması; LLM önizlemesi ve ağ çağrısı öncesi onay eklendi.
- [x] Model adı boş/örnek değerken anlaşılır hata ve `--elle` yönlendirmesi göster.
- [ ] Bilinmeyen sırları ve kişisel bilgileri yakalama kapsamını gerçek, temizlenmiş örneklerle ölç.

## P1 — Kapsam ve doğruluk

- [ ] Antigravity biçimini gerçek örnekle doğrula; proje eşlemesini geliştir.
- [ ] Bulut/dışa aktarma dosyalarının `gelen/` içe aktarımını test et.
- [ ] Kullanıcı düzenlemelerinin tekrar çalıştırmada korunmasını test et.
- [ ] Kaynak turu/commit atfı ve özet doğruluğu için değerlendirme kümesi oluştur.
- [ ] `BAGLAM.md` içine görevle ilgili dosya ve kararları seç.

## P2 — Kullanım

- [ ] Platform bağımsız kurulum ve zamanlayıcı yönergeleri.
- [ ] Kaynak sürümü ve yapılandırma tanılaması için `doctor` komutu.
- [ ] Modül ayrımı ve MCP arayüzü tasarımı.

## Belge çalışması

- [x] README, mimari, yol haritası, değişiklik günlüğü, teknik bilgi, plan ve görevler yazıldı.
- [x] Kişisel veriler için `.gitignore` genişletildi.
