# Uygulama planı

## Amaç

Farklı coding ajanlarının oturumlarını güvenle taşıyan, yerelde çalışan ve kaynağa geri götüren bağlam aracı.

## 1. İçe aktarmayı sağlamlaştır

Gerçek, kişisel verisi temizlenmiş Claude/Codex kayıtlarıyla parser testleri; tekrarlı çalıştırma, büyüyen/kısalan kaynak ve yarım dosya durumları; atomik yazma; Antigravity biçimini doğrulama.

**Çıkış ölçütü:** Aynı kayıt ikinci kez işlendiğinde çift Bölüm oluşmaz; özetten kaynak tura geri gidilebilir.

## 2. Özet ve güvenlik

LLM istemi önizlemesi, sır denetimi, kaynak turu/commit atfı, manuel düzeltmelerin korunması ve model hatasında tutarlı işlem durumu.

**Çıkış ölçütü:** Kritik karar/test iddiaları izlenebilir ve başarısız çalıştırma arşivi bozmaz.

## 3. Göreve uygun bağlam

Görev, dosya ve Git değişikliklerine göre Bölüm seçimi; eski iddialar için güncel durum uyarısı; gerçek token ve yeni oturum başarısı ölçümü. İhtiyaç kanıtlanırsa MCP arayüzü.

**Çıkış ölçütü:** Mevcut yeniye-öncelik yöntemine göre daha ilgili bağlam ve daha az eski bilgi kullanımı.
